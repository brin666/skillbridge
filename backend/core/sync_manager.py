"""Safe Sync Manager.

Flow:

    Preflight
    -> Temporary Install
    -> Validation
    -> Atomic Commit
    -> Rollback on failure
"""

from __future__ import annotations

import hashlib
import os
import shutil
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from ..adapters.base import AgentAdapter
from ..models.skill import Skill
from ..skill_files import find_skill_md
from ..models.sync import SyncStep, SyncTransaction
from .cache_manager import CacheManager
from .hash_utils import compute_skill_md_hash
from .installer import Installer
from .preflight import PreflightChecker
from .rollback import RollbackManager
from .sync_history import SyncHistoryManager


class SyncError(RuntimeError):
    """Raised when a sync step fails and should be rolled back."""


class SyncManager:
    """Coordinates a full Safe Sync transaction."""

    def __init__(
        self,
        preflight_checker: PreflightChecker | None = None,
        installer: Installer | None = None,
        rollback_manager: RollbackManager | None = None,
        cache_manager: CacheManager | None = None,
        history: SyncHistoryManager | None = None,
    ) -> None:
        self.preflight = preflight_checker or PreflightChecker()
        self.installer = installer or Installer()
        self.rollback = rollback_manager or RollbackManager()
        self.cache = cache_manager or CacheManager()
        self.history = history or SyncHistoryManager(
            history_dir=self.rollback.state_root / "history" / "sync"
        )
        self._live_transactions: dict[str, dict] = {}
        self._live_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def sync(
        self,
        skill: Skill,
        target_agent: str | AgentAdapter,
        options: dict | None = None,
    ) -> dict:
        """Run a sync synchronously and return the final result."""
        adapter = self._resolve_adapter(target_agent)
        if adapter is None:
            return {"status": "failed", "reason": "Target Agent is not supported"}
        tx = self._new_transaction(skill, adapter.agent_id)
        options, hash_error = self._bind_expected_skill_md_hash(skill, options)
        if hash_error:
            return self._finish_failed(tx, message="Unable to pin source version", error=hash_error)
        return self._execute_sync(tx, skill, adapter, options)

    def start_sync(
        self,
        skill: Skill,
        target_agent: str | AgentAdapter,
        options: dict | None = None,
    ) -> dict:
        """Start a sync in the background and return a transaction id.

        A quick Preflight is run synchronously so WARN/BLOCK can be returned
        before any background work starts.
        """
        options, hash_error = self._bind_expected_skill_md_hash(skill, options)
        if hash_error:
            status = "stale" if "changed after analysis" in hash_error else "failed"
            return {"status": status, "reason": hash_error}
        confirm_warning = bool(options.get("confirm_warning"))
        adapter = self._resolve_adapter(target_agent)
        if adapter is None:
            return {"status": "failed", "reason": "Target Agent is not supported"}

        preflight = self.preflight.check(
            skill,
            adapter,
            target_inventory_checked=bool(options.get("target_inventory_checked")),
        )
        if preflight.status == "block":
            return {
                "status": "failed",
                "reason": "Preflight blocked",
                "errors": preflight.errors,
                "checks": [c.to_dict() for c in preflight.checks],
            }
        if preflight.status == "warn" and not confirm_warning:
            return {
                "status": "warning_required",
                "warnings": preflight.warnings,
                "checks": [c.to_dict() for c in preflight.checks],
            }

        tx = self._new_transaction(skill, adapter.agent_id)
        thread = threading.Thread(
            target=self._run_async,
            args=(tx, skill, adapter, options),
            daemon=True,
        )
        thread.start()
        return {
            "status": "started",
            "transaction_id": tx.id,
            "target": adapter.agent_id,
        }

    @staticmethod
    def _bind_expected_skill_md_hash(
        skill: Skill,
        options: dict | None,
    ) -> tuple[dict, str | None]:
        """Pin the reviewed SKILL.md version across preflight and staging."""
        bound_options = dict(options or {})
        expected_hash = str(bound_options.get("expected_skill_md_hash") or "")
        current_hash = compute_skill_md_hash(skill.path)
        if not current_hash:
            if not expected_hash:
                # Let Preflight report a missing/unreadable source through the
                # normal transaction path, preserving its audit record.
                return bound_options, None
            return bound_options, "Source SKILL.md not found"
        if expected_hash and current_hash != expected_hash:
            return bound_options, "Source SKILL.md changed after analysis"
        bound_options["expected_skill_md_hash"] = expected_hash or current_hash
        return bound_options, None

    def start_batch_sync(
        self,
        skill: Skill,
        targets: list[str],
        options: dict | None = None,
    ) -> dict:
        """Start one independent transaction per target Agent."""
        options = options or {}
        tasks = []
        for target in targets:
            result = self.start_sync(skill, target, options)
            if result.get("status") == "started":
                tasks.append(
                    {
                        "target": target,
                        "transaction_id": result["transaction_id"],
                        "status": "started",
                    }
                )
            elif result.get("status") == "warning_required":
                tasks.append(
                    {
                        "target": target,
                        "status": "warning_required",
                        "warnings": result.get("warnings", []),
                    }
                )
            else:
                tasks.append(
                    {
                        "target": target,
                        "status": "failed",
                        "error": result.get("reason", "failed"),
                    }
                )
        return {"tasks": tasks}

    def get_transaction(self, transaction_id: str) -> dict | None:
        # Polling must not depend on a history file staying readable while a
        # worker is alive, or on its final disk write succeeding.
        with self._live_lock:
            live = self._live_transactions.get(transaction_id)
            if live:
                return deepcopy(live)
        tx = self.history.get(transaction_id)
        return tx.to_dict() if tx else None

    def list_history(self, limit: int = 50) -> list[dict]:
        return [tx.to_dict() for tx in self.history.list(limit=limit)]

    # ------------------------------------------------------------------
    # Async runner
    # ------------------------------------------------------------------
    def _run_async(
        self,
        tx: SyncTransaction,
        skill: Skill,
        adapter: AgentAdapter,
        options: dict,
    ) -> None:
        try:
            self._execute_sync(tx, skill, adapter, options)
        except Exception as exc:
            # Errors before the staging/rollback block must still finish the
            # transaction, rather than leave a permanently running record.
            try:
                self._finish_failed(tx, message="Sync failed", error=str(exc))
            except OSError:
                # _update publishes the failed result before trying disk.
                pass

    # ------------------------------------------------------------------
    # Sync execution
    # ------------------------------------------------------------------
    def _execute_sync(
        self,
        tx: SyncTransaction,
        skill: Skill,
        adapter: AgentAdapter,
        options: dict,
    ) -> dict:
        confirm_warning = bool(options.get("confirm_warning"))
        force_replace = bool(options.get("force_replace"))

        self._update(tx, status="running", progress=5, message="Starting sync")
        expected_hash = str(options.get("expected_skill_md_hash") or "")
        if expected_hash and compute_skill_md_hash(skill.path) != expected_hash:
            return self._finish_failed(
                tx,
                message="Sync analysis expired",
                error="Source SKILL.md changed after analysis",
            )
        self._set_step(tx, "preflight", "running", "Running Preflight")
        preflight = self.preflight.check(
            skill,
            adapter,
            target_inventory_checked=bool(options.get("target_inventory_checked")),
        )
        self._set_step(tx, "preflight", "success", "Preflight completed")

        if preflight.status == "block":
            self._finish_failed(
                tx,
                message="Preflight blocked",
                error="; ".join(preflight.errors),
            )
            return {
                "status": "failed",
                "reason": "Preflight blocked",
                "errors": preflight.errors,
                "checks": [c.to_dict() for c in preflight.checks],
                "transaction_id": tx.id,
            }

        if preflight.status == "warn" and not confirm_warning:
            self._finish_failed(
                tx,
                message="Warning confirmation required",
                error="; ".join(preflight.warnings),
            )
            return {
                "status": "warning_required",
                "warnings": preflight.warnings,
                "checks": [c.to_dict() for c in preflight.checks],
                "transaction_id": tx.id,
            }

        source_dir = self._source_dir(skill)
        if not source_dir.is_dir():
            return self._finish_failed(tx, message="Source Skill directory not found", error="Source Skill directory not found")

        roots = adapter.get_skill_paths()
        if not roots:
            return self._finish_failed(tx, message="Target Agent Skill directory not found", error="Target Agent Skill directory not found")
        target_dir = Path(roots[0]) / skill.id
        target_skill_path = target_dir / "SKILL.md"
        if target_dir.is_symlink() or target_skill_path.is_symlink():
            return self._finish_failed(
                tx,
                message="Unsafe target path",
                error="Target Skill path is a symbolic link; refusing to sync through it",
            )

        # Fast conflict check before doing any file work.
        conflict = self._conflict_status(
            target_dir,
            skill,
            adapter,
            target_inventory_checked=bool(options.get("target_inventory_checked")),
        )
        if conflict:
            handled = self._handle_conflict(tx, conflict, target_dir, force_replace)
            if handled["status"] != "proceed":
                return handled

        temp_path = self.installer.prepare_temp_path(skill.id)
        target_dir_existed = target_dir.exists()
        target_skill_existed = target_skill_path.is_file()
        backup_skill_md = temp_path.with_name(f"{temp_path.name}.SKILL.md.bak")
        install_attempted = False
        rollback_tx_id = self.rollback.begin(
            source=str(source_dir),
            target=str(target_dir),
            tmp=str(temp_path),
            target_existed=target_dir_existed,
        )
        staged_hash = ""

        try:
            self._update(tx, status="running", progress=35, message="Copying files...")
            self._set_step(tx, "copy", "running", "Copying files to temporary directory")
            self.installer.copy_skill_md_to_temp(source_dir, temp_path)
            self._set_step(tx, "copy", "success", "Files copied")

            self._update(tx, status="running", progress=65, message="Validating temporary copy...")
            self._set_step(tx, "validation", "running", "Validating temporary copy")
            validation = self._validate_temp(source_dir, temp_path, expected_hash=expected_hash)
            if not validation["ok"]:
                raise SyncError(validation["error"])
            staged_hash = validation["hash"]
            self._set_step(tx, "validation", "success", "Temporary copy is valid")

            self._update(tx, status="running", progress=85, message="Committing to target...")
            self._set_step(tx, "commit", "running", "Committing to target Agent")

            conflict = self._conflict_status(target_dir, skill, adapter)
            if conflict:
                if conflict["status"] == "already_installed":
                    self.rollback.cleanup_tmp(rollback_tx_id)
                    self.rollback.commit(rollback_tx_id)
                    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    self._update(tx, status="success", progress=100, message="Skill already installed", end_time=now)
                    return {"status": "already_installed", "message": "Skill already installed", "transaction_id": tx.id}
                if conflict["status"] == "nested_conflict":
                    raise SyncError(conflict["message"])
                if not force_replace:
                    raise SyncError("Existing Skill differs")

            if target_skill_path.is_file() and force_replace:
                shutil.copy2(target_skill_path, backup_skill_md)

            install_attempted = True
            self.installer.install_skill_md_bytes(validation["payload"], target_dir, tx.id)
            shutil.rmtree(temp_path, ignore_errors=True)

            self.rollback.commit(rollback_tx_id)
            self._set_step(tx, "commit", "success", "Committed")
            self._finish_success(tx, adapter.agent_id)
            if backup_skill_md.exists():
                try:
                    backup_skill_md.unlink()
                except OSError:
                    pass
            return {
                "status": "success",
                "message": "Skill synced",
                "target": adapter.agent_id,
                "transaction_id": tx.id,
            }
        except Exception as exc:
            if target_dir_existed:
                if backup_skill_md.is_file():
                    target_dir.mkdir(parents=True, exist_ok=True)
                    restore_path = target_dir / f".SKILL.md.skillbridge-restore-{tx.id}.tmp"
                    try:
                        shutil.copy2(backup_skill_md, restore_path)
                        os.replace(restore_path, target_skill_path)
                    finally:
                        if restore_path.exists():
                            restore_path.unlink()
                elif install_attempted and not target_skill_existed and target_skill_path.is_file():
                    if staged_hash and compute_skill_md_hash(target_skill_path) == staged_hash:
                        target_skill_path.unlink()
            elif install_attempted and not target_skill_existed and target_skill_path.is_file():
                if staged_hash and compute_skill_md_hash(target_skill_path) == staged_hash:
                    target_skill_path.unlink()
            if not target_dir_existed:
                try:
                    target_dir.rmdir()
                except OSError:
                    pass
            if backup_skill_md.exists():
                try:
                    backup_skill_md.unlink()
                except OSError:
                    pass
            self.rollback.rollback(rollback_tx_id)
            self._set_step(tx, "rollback", "success", "Rolled back")
            self._finish_failed(tx, message="Sync failed", error=str(exc))
            return {"status": "failed", "reason": str(exc), "transaction_id": tx.id}

    # ------------------------------------------------------------------
    # Conflict helpers
    # ------------------------------------------------------------------
    def _conflict_status(
        self,
        target_dir: Path,
        skill: Skill,
        adapter: AgentAdapter | None = None,
        *,
        target_inventory_checked: bool = False,
    ) -> dict | None:
        target_md = find_skill_md(target_dir)
        if target_md is None:
            if adapter is not None and not target_inventory_checked:
                nested_matches = self.preflight.find_target_skill_dirs(skill, adapter)
                if nested_matches:
                    source_hash = compute_skill_md_hash(self._source_dir(skill))
                    match_hashes = {
                        compute_skill_md_hash(path) for path in nested_matches
                    }
                    match_hashes.discard("")
                    if match_hashes == {source_hash}:
                        return {
                            "status": "already_installed",
                            "message": "Skill already installed in a nested target directory",
                            "target": str(nested_matches[0]),
                        }
                    return {
                        "status": "nested_conflict",
                        "message": "A Skill with the same declared name already exists in a nested target directory; automatic replacement is disabled",
                        "target": str(nested_matches[0]),
                    }
            return None
        existing_hash = compute_skill_md_hash(target_md)
        source_hash = compute_skill_md_hash(self._source_dir(skill))
        if existing_hash and source_hash and existing_hash == source_hash:
            return {"status": "already_installed", "message": "Skill already installed"}
        return {"status": "conflict", "message": "Existing Skill differs"}

    def _handle_conflict(
        self,
        tx: SyncTransaction,
        conflict: dict,
        target_dir: Path,
        force_replace: bool,
    ) -> dict:
        if conflict["status"] == "already_installed":
            self._finish_failed(tx, message="Skill already installed", error="Skill already installed")
            return {
                "status": "already_installed",
                "message": conflict.get("message", "Skill already installed"),
                "target": conflict.get("target", str(target_dir)),
                "transaction_id": tx.id,
            }

        if conflict["status"] == "nested_conflict":
            self._finish_failed(
                tx,
                message="Nested Skill conflict",
                error=conflict["message"],
            )
            return {
                "status": "conflict",
                "message": conflict["message"],
                "target": conflict.get("target", str(target_dir)),
                "transaction_id": tx.id,
            }

        if not force_replace:
            self._finish_failed(
                tx,
                message="Conflict detected",
                error="Existing Skill differs; force_replace is required to overwrite",
            )
            return {
                "status": "conflict",
                "message": "Existing Skill differs",
                "target": str(target_dir),
                "transaction_id": tx.id,
            }

        # force_replace path continues to the normal staging flow, so just return None here.
        return {"status": "proceed"}

    # ------------------------------------------------------------------
    # Transaction persistence helpers
    # ------------------------------------------------------------------
    def _new_transaction(self, skill: Skill, target_agent: str) -> SyncTransaction:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        tx_id = (
            "sync_"
            + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_")
            + uuid.uuid4().hex[:4]
        )
        tx = SyncTransaction(
            id=tx_id,
            skill=skill.id,
            source_agent=skill.installed_agents[0] if skill.installed_agents else "",
            target_agent=target_agent,
            start_time=now,
            status="pending",
            progress=0,
            message="Pending",
            steps=[
                SyncStep(name="preflight"),
                SyncStep(name="copy"),
                SyncStep(name="validation"),
                SyncStep(name="commit"),
                SyncStep(name="rollback"),
            ],
        )
        self.history.create(tx)
        self._publish_transaction(tx)
        return tx

    def _publish_transaction(self, tx: SyncTransaction) -> None:
        with self._live_lock:
            self._live_transactions[tx.id] = deepcopy(tx.to_dict())
            if len(self._live_transactions) > 256:
                finished = [key for key, value in self._live_transactions.items()
                            if value["status"] not in {"pending", "running"}]
                for key in finished[:len(self._live_transactions) - 256]:
                    self._live_transactions.pop(key, None)

    def _update(self, tx: SyncTransaction, **changes) -> None:
        for key, value in changes.items():
            if hasattr(tx, key):
                setattr(tx, key, value)
        self._publish_transaction(tx)
        self.history.update(tx)

    def _set_step(self, tx: SyncTransaction, name: str, status: str, message: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for step in tx.steps:
            if step.name == name:
                step.status = status
                step.message = message
                if status == "running" and not step.started_at:
                    step.started_at = now
                if status in ("success", "failed", "skipped"):
                    step.ended_at = now
                break
        self._publish_transaction(tx)
        self.history.update(tx)

    def _finish_success(self, tx: SyncTransaction, target_agent: str) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._update(
            tx,
            status="success",
            progress=100,
            message=f"Synced to {target_agent}",
            end_time=now,
        )

    def _finish_failed(self, tx: SyncTransaction, message: str, error: str) -> dict:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._update(
            tx,
            status="failed",
            progress=100,
            message=message,
            error=error,
            end_time=now,
        )
        return {"status": "failed", "reason": error, "message": message, "transaction_id": tx.id}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _resolve_adapter(self, target_agent: str | AgentAdapter) -> AgentAdapter | None:
        if isinstance(target_agent, AgentAdapter):
            return target_agent
        for adapter in self.preflight.adapters:
            if adapter.agent_id == target_agent:
                return adapter
        return None

    @staticmethod
    def _source_dir(skill: Skill) -> Path:
        path = Path(skill.path).resolve()
        if path.is_file() or path.name.lower() == "skill.md":
            return path.parent
        return path

    def _validate_temp(
        self,
        source_dir: Path,
        temp_dir: Path,
        expected_hash: str = "",
    ) -> dict:
        if not (temp_dir / "SKILL.md").is_file():
            return {"ok": False, "error": "Temporary SKILL.md not found"}
        staged_files = [p.name for p in temp_dir.iterdir() if p.is_file()]
        if staged_files != ["SKILL.md"] or any(p.is_dir() for p in temp_dir.iterdir()):
            return {"ok": False, "error": "Sync payload must contain only SKILL.md"}
        source_hash = compute_skill_md_hash(source_dir)
        try:
            staged_bytes = (temp_dir / "SKILL.md").read_bytes()
        except OSError:
            return {"ok": False, "error": "Temporary SKILL.md could not be read"}
        temp_hash = hashlib.sha256(staged_bytes).hexdigest()
        if expected_hash and temp_hash != expected_hash:
            return {"ok": False, "error": "Staged SKILL.md differs from the reviewed version"}
        if not temp_hash or temp_hash != source_hash:
            return {"ok": False, "error": "Temporary SKILL.md hash mismatch"}
        return {"ok": True, "hash": temp_hash, "payload": staged_bytes}
