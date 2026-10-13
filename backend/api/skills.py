"""Skills API.

Phase 2 provides in-process query helpers and is used by the localhost API
server. Phase 4A adds safe local management operations.
"""

from __future__ import annotations

import threading
import time
import uuid
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from ..core.agent_scanner import AgentScanner
from ..core.cache_manager import CacheManager
from ..core.library_manager import LibraryManager
from ..core.hash_utils import compute_skill_md_hash
from ..core.mutual_sync import MutualSyncPlan, MutualSyncPlanner
from ..core.mutual_sync_jobs import MutualSyncJobStore
from ..core.preflight import PreflightChecker
from ..core.skill_manager import SkillManager
from ..core.skill_scanner import SkillScanner
from ..core.sync_manager import SyncManager
from ..models.skill import Skill
from ..skill_files import find_skill_md


class SkillsAPI:
    """Holds the current scanned Agent/Skill state for API queries."""

    def __init__(
        self,
        agent_scanner: AgentScanner | None = None,
        skill_scanner: SkillScanner | None = None,
        skill_manager: SkillManager | None = None,
        sync_manager: SyncManager | None = None,
        library_manager: LibraryManager | None = None,
    ) -> None:
        self.agent_scanner = agent_scanner or AgentScanner()
        self.skill_scanner = skill_scanner or SkillScanner(
            cache_manager=CacheManager()
        )
        self.skill_manager = skill_manager or SkillManager()
        self.preflight_checker = PreflightChecker(adapters=self.agent_scanner.adapters)
        self.sync_manager = sync_manager or SyncManager(
            preflight_checker=self.preflight_checker,
            cache_manager=self.skill_scanner.cache_manager or CacheManager(),
        )
        self.preflight_checker = self.sync_manager.preflight
        self.library_manager = library_manager or LibraryManager()
        self._mutual_sync_plans: dict[str, tuple[float, MutualSyncPlan]] = {}
        self._mutual_sync_plan_lock = threading.Lock()
        self._mutual_sync_jobs: dict[str, dict] = {}
        self._mutual_sync_job_lock = threading.RLock()
        self._mutual_sync_start_lock = threading.Lock()
        self._mutual_sync_job_store = MutualSyncJobStore(self.sync_manager.history.history_dir.parent / "mutual")
        self._missing_sync_status: dict[tuple[str, str], float] = {}
        self._sync_status_retry_seconds = 30.0
        self._restore_mutual_sync_jobs()
        self._compatibility_warmup_lock = threading.Lock()
        self._compatibility_warmup_status = {
            "status": "idle",
            "checkedPairs": 0,
            "error": None,
        }
        self._compatibility_warmup_plan: MutualSyncPlan | None = None
        self._compatibility_warmup_enabled = False
        self._compatibility_warmup_rerun_requested = False
        self._agents: list = []
        self._skills: list = []
        self.rescan()

    def rescan(self) -> dict:
        """Rescan Agents and Skills, then return a summary dict."""
        agents = self.agent_scanner.scan()
        skills = self.skill_scanner.scan_agents(agents)
        self._agents = agents
        self._skills = skills
        if self._compatibility_warmup_enabled:
            self.start_compatibility_warmup(force=True)
        return {
            "agents": len([a for a in agents if a.installed]),
            "skills": len(skills),
            "agentList": [a.to_dict() for a in agents],
            "skillList": [s.to_dict() for s in skills],
        }

    def start_compatibility_warmup(self, force: bool = False) -> dict:
        """Warm static compatibility checks in the background without writing Skills."""
        with self._compatibility_warmup_lock:
            self._compatibility_warmup_enabled = True
            status = self._compatibility_warmup_status["status"]
            if status == "warming":
                if force:
                    self._compatibility_warmup_rerun_requested = True
                    self._compatibility_warmup_plan = None
                return dict(self._compatibility_warmup_status)
            if status == "ready" and not force:
                return dict(self._compatibility_warmup_status)

            self._compatibility_warmup_plan = None
            self._compatibility_warmup_status = {
                "status": "warming",
                "checkedPairs": 0,
                "error": None,
            }
            threading.Thread(
                target=self._run_compatibility_warmup,
                name="skillbridge-compatibility-warmup",
                daemon=True,
            ).start()
            return dict(self._compatibility_warmup_status)

    def get_compatibility_warmup_status(self) -> dict:
        with self._compatibility_warmup_lock:
            return dict(self._compatibility_warmup_status)

    def _run_compatibility_warmup(self) -> None:
        while True:
            error = None
            checked_pairs = 0
            plan = None
            try:
                installed = [agent.id for agent in self._agents if agent.installed]
                if len(installed) >= 2:
                    plan = self._build_mutual_sync_plan(installed)
                    checked_pairs = sum(1 for entry in plan.entries if entry.checks)
            except Exception as exc:  # surfaced in the local UI; analysis can still run live
                error = str(exc)

            with self._compatibility_warmup_lock:
                if self._compatibility_warmup_rerun_requested:
                    self._compatibility_warmup_rerun_requested = False
                    continue
                self._compatibility_warmup_status = {
                    "status": "failed" if error else "ready",
                    "checkedPairs": checked_pairs,
                    "error": error,
                }
                self._compatibility_warmup_plan = plan if error is None else None
                return

    def list_skills(self) -> list[dict]:
        library = self.library_manager.get_library_skill
        return [
            self._with_library_info(s.to_dict(), library(s.id))
            for s in self._skills
        ]

    def get_skill(self, skill_id: str) -> dict | None:
        skill = self._find_skill(skill_id)
        if skill is None:
            return None
        library_skill = self.library_manager.get_library_skill(skill.id)
        return self._with_library_info(skill.to_dict(), library_skill)

    def list_agents(self) -> list[dict]:
        return [a.to_dict() for a in self._agents]

    # ------------------------------------------------------------------
    # Phase 4A management operations
    # ------------------------------------------------------------------
    def open_folder(self, skill_id: str) -> dict:
        skill = self._require_skill(skill_id)
        return self.skill_manager.open_folder(skill.path)

    def open_file(self, skill_id: str) -> dict:
        skill = self._require_skill(skill_id)
        return self.skill_manager.open_file(skill.path)

    def disable_skill(self, skill_id: str) -> dict:
        skill = self._require_skill(skill_id)
        result = self.skill_manager.disable(skill.path, skill.id)
        self.rescan()
        return result

    def enable_skill(self, skill_id: str) -> dict:
        skill = self._require_skill(skill_id)
        result = self.skill_manager.enable(skill.path, skill.id)
        self.rescan()
        return result

    def uninstall_skill(self, skill_id: str) -> dict:
        skill = self._require_skill(skill_id)
        paths = self._installed_dirs(skill)
        result = self.skill_manager.uninstall(paths, skill.id)
        cache = self.skill_scanner.cache_manager
        if cache is not None:
            cache.remove(skill.id)
        self.rescan()
        return result

    def preflight_skill(self, skill_id: str, target_agent: str) -> dict:
        skill = self._require_skill(skill_id)
        return self.preflight_checker.check(skill, target_agent).to_dict()

    def sync_skill(
        self,
        skill_id: str,
        target_agent: str,
        confirm_warning: bool = False,
        force_replace: bool = False,
    ) -> dict:
        skill = self._require_skill(skill_id)
        result = self.sync_manager.start_sync(
            skill,
            target_agent,
            {
                "confirm_warning": confirm_warning,
                "force_replace": force_replace,
            },
        )
        return result

    def batch_sync_skill(
        self,
        skill_id: str,
        targets: list[str],
        confirm_warning: bool = False,
        force_replace: bool = False,
    ) -> dict:
        skill = self._require_skill(skill_id)
        return self.sync_manager.start_batch_sync(
            skill,
            targets,
            {
                "confirm_warning": confirm_warning,
                "force_replace": force_replace,
            },
        )

    def plan_mutual_sync(self, agent_ids: list[str]) -> dict:
        selected = list(dict.fromkeys(str(agent_id) for agent_id in agent_ids if str(agent_id)))
        with self._compatibility_warmup_lock:
            warm_plan = self._compatibility_warmup_plan
            warmup_ready = self._compatibility_warmup_status["status"] == "ready"
            if warmup_ready and warm_plan and set(selected) == set(warm_plan.agents):
                plan = deepcopy(warm_plan)
                plan.agents = selected
            else:
                plan = None
        if plan is None:
            plan = self._build_mutual_sync_plan(selected)
        self._remember_mutual_sync_plan(plan)
        return plan.to_dict()

    def start_mutual_sync(
        self, agent_ids: list[str], plan_id: str | None = None, *, background: bool = False,
        request_id: str | None = None,
    ) -> dict:
        # Two tabs/retries can submit the same request before its response is
        # received. Serialize acceptance, not execution, and return the same job.
        with self._mutual_sync_start_lock:
            if background and request_id:
                if not self._mutual_sync_job_store.valid_id(request_id):
                    return {"code": "SYNC_REQUEST_INVALID", "message": "Invalid sync request id"}
                existing = self.get_mutual_sync_job(request_id)
                if existing:
                    if existing["plan"].get("planId") != plan_id or set(existing["plan"]["agents"]) != set(agent_ids):
                        return {"code": "SYNC_REQUEST_MISMATCH", "message": "This request id belongs to a different sync batch"}
                    return existing
            return self._accept_mutual_sync(agent_ids, plan_id, background=background, request_id=request_id)

    def _accept_mutual_sync(
        self, agent_ids: list[str], plan_id: str | None, *, background: bool,
        request_id: str | None,
    ) -> dict:
        if not plan_id:
            return {
                "code": "PLAN_REQUIRED",
                "message": "Analyze the selected Harnesses before starting sync",
            }
        with self._mutual_sync_plan_lock:
            cached = self._mutual_sync_plans.pop(plan_id, None)
        if cached is None or time.monotonic() - cached[0] > 600:
            return {
                "code": "PLAN_STALE",
                "message": "This analysis expired; analyze the selected Harnesses again",
            }

        reviewed_plan = cached[1]
        selected = list(dict.fromkeys(str(agent_id) for agent_id in agent_ids if str(agent_id)))
        if set(selected) != set(reviewed_plan.agents):
            return {
                "code": "PLAN_STALE",
                "message": "The selected Harnesses changed; analyze them again",
            }
        if background:
            job_id = request_id or uuid.uuid4().hex
            job = {
                "id": job_id,
                "status": "running",
                "phase": "validating",
                "startedAt": time.time(),
                "plan": reviewed_plan.to_dict(),
                "tasks": [
                    {
                        "skillId": entry.skill_id, "skillName": entry.skill_name,
                        "sourceAgent": entry.source_agent, "target": entry.target_agent,
                        "status": "queued", "progress": 0,
                    }
                    for entry in reviewed_plan.ready_entries
                ],
                "error": None,
            }
            with self._mutual_sync_job_lock:
                # Retain recent results for a reopened panel; never evict live jobs.
                finished = [key for key, value in self._mutual_sync_jobs.items() if value["status"] != "running"]
                for key in finished[:-31]:
                    self._mutual_sync_job_store.remove(key)
                    del self._mutual_sync_jobs[key]
                # Save before launching any write, so a lost response or a
                # restart still has the plan/transaction association.
                self._mutual_sync_job_store.save(job)
                self._mutual_sync_jobs[job_id] = job
            initial = deepcopy(job)
            threading.Thread(
                target=self._run_mutual_sync_job,
                args=(job_id, selected, reviewed_plan), daemon=True,
                name=f"skillbridge-sync-{job_id[:8]}",
            ).start()
            return initial
        return self._execute_mutual_sync(selected, reviewed_plan)

    def get_mutual_sync_job(self, job_id: str) -> dict | None:
        with self._mutual_sync_job_lock:
            job = self._mutual_sync_jobs.get(job_id)
            return deepcopy(job) if job else None

    def _update_mutual_sync_job(self, job_id: str, **changes: Any) -> None:
        with self._mutual_sync_job_lock:
            job = self._mutual_sync_jobs[job_id]
            if any(job.get(key) != value for key, value in changes.items()):
                job.update(changes)
                self._mutual_sync_job_store.save(job)

    def _restore_mutual_sync_jobs(self) -> None:
        for job in self._mutual_sync_job_store.load():
            if job["status"] == "running":
                # Never silently restart writes after process interruption.
                # Reconcile durable terminal transactions; all other outcomes
                # are explicitly interrupted, not claimed successful.
                for task in job["tasks"]:
                    if task["status"] in {"queued", "started", "pending", "running"}:
                        tx = self.sync_manager.get_transaction(task.get("transaction_id", ""))
                        if tx and tx["status"] not in {"pending", "running"}:
                            task.update(status=tx["status"], progress=tx["progress"], message=tx.get("error") or tx.get("message"))
                        else:
                            task.update(status="interrupted", message="The local service restarted; this result could not be confirmed")
                successful = all(task["status"] in {"success", "already_installed"} for task in job["tasks"])
                job.update(status="success" if successful and job["tasks"] else "failed", phase="finished", endedAt=time.time())
                if job["status"] == "failed":
                    job.update(code="SYNC_INTERRUPTED", error="The local service restarted. Completed items were preserved; analyze again before retrying.")
                self._mutual_sync_job_store.save(job)
            self._mutual_sync_jobs[job["id"]] = job

    def _refresh_mutual_sync_tasks(self, job_id: str, tasks: list[dict]) -> int:
        active = 0
        for task in tasks:
            if task["status"] not in {"started", "pending", "running"}:
                continue
            transaction_id = task.get("transaction_id")
            transaction = self.sync_manager.get_transaction(transaction_id) if transaction_id else None
            if transaction:
                self._missing_sync_status.pop((job_id, transaction_id), None)
                task.update(
                    status=transaction["status"], progress=transaction["progress"],
                    message=transaction.get("error") or transaction.get("message", ""),
                    steps=transaction.get("steps", []),
                )
            else:
                missing_since = self._missing_sync_status.setdefault((job_id, transaction_id or ""), time.monotonic())
                if time.monotonic() - missing_since >= self._sync_status_retry_seconds:
                    task.update(status="unknown", message="Sync status could not be recovered; the result is unknown. Check the target before retrying.")
                    self._missing_sync_status.pop((job_id, transaction_id or ""), None)
            if task["status"] in {"started", "pending", "running"}:
                active += 1
        self._update_mutual_sync_job(job_id, tasks=deepcopy(tasks))
        return active

    def _run_mutual_sync_job(self, job_id: str, selected: list[str], reviewed_plan: MutualSyncPlan) -> None:
        try:
            result = self._execute_mutual_sync(selected, reviewed_plan, job_id=job_id)
            if result.get("code"):
                self._update_mutual_sync_job(
                    job_id, status="failed", phase="finished", code=result["code"],
                    error=result["message"], endedAt=time.time(), tasks=[],
                )
                return
            tasks = result["tasks"]
            while self._refresh_mutual_sync_tasks(job_id, tasks):
                time.sleep(0.15)
            self._update_mutual_sync_job(job_id, phase="refreshing")
            # Scan once per batch, so the Hub sees the new Harness copies.
            self.rescan()
            failed = any(task["status"] not in {"success", "already_installed"} for task in tasks)
            self._update_mutual_sync_job(
                job_id, status="failed" if failed else "success", phase="finished",
                endedAt=time.time(),
                **({"code": "SYNC_STATUS_LOST", "error": "Some sync results could not be confirmed. Check the targets before retrying."}
                   if any(task["status"] == "unknown" for task in tasks) else {}),
            )
        except Exception as exc:
            self._update_mutual_sync_job(
                job_id, status="failed", phase="finished", error=str(exc), endedAt=time.time(),
            )

    def _execute_mutual_sync(
        self, selected: list[str], reviewed_plan: MutualSyncPlan, *, job_id: str | None = None,
    ) -> dict:
        try:
            plan = self._build_mutual_sync_plan(selected)
        except ValueError:
            with self._compatibility_warmup_lock:
                self._compatibility_warmup_plan = None
            return {
                "code": "PLAN_STALE",
                "message": "The installed Harnesses changed; analyze them again",
            }
        if (
            plan.inventory_hash != reviewed_plan.inventory_hash
            or self._plan_signature(plan) != self._plan_signature(reviewed_plan)
        ):
            with self._compatibility_warmup_lock:
                self._compatibility_warmup_plan = None
            return {
                "code": "PLAN_STALE",
                "message": "Skills changed after analysis; analyze again to review the updated sync list",
            }
        plan.plan_id = reviewed_plan.plan_id

        tasks: list[dict] = [
            {
                "skillId": entry.skill_id, "skillName": entry.skill_name,
                "sourceAgent": entry.source_agent, "target": entry.target_agent,
                "status": "queued", "progress": 0,
            }
            for entry in plan.ready_entries
        ]
        if job_id:
            self._update_mutual_sync_job(job_id, phase="syncing", plan=plan.to_dict())
        for index, entry in enumerate(plan.ready_entries):
            if entry.source_skill is None:
                continue
            if job_id:
                # Keep disk writes and target scans bounded rather than launching
                # hundreds of simultaneous transactions.
                while self._refresh_mutual_sync_tasks(job_id, tasks) >= 3:
                    time.sleep(0.15)
                if any(task["status"] == "unknown" for task in tasks):
                    for task in tasks[index:]:
                        task.update(status="skipped", message="Not started because an earlier sync result is unknown")
                    self._update_mutual_sync_job(job_id, tasks=deepcopy(tasks))
                    break
            try:
                result = self.sync_manager.start_sync(
                    entry.source_skill,
                    entry.target_agent,
                    {
                        "expected_skill_md_hash": entry.source_hash,
                        "target_inventory_checked": True,
                    },
                )
            except Exception as exc:
                if not job_id:
                    raise
                result = {"status": "failed", "reason": str(exc)}
            tasks[index].update(
                {
                    "transaction_id": result.get("transaction_id"),
                    "status": result.get("status", "failed"),
                    "message": result.get("reason") or result.get("message", ""),
                }
            )
            if job_id:
                self._refresh_mutual_sync_tasks(job_id, tasks)
        return {"plan": plan.to_dict(), "tasks": tasks}

    def _remember_mutual_sync_plan(self, plan: MutualSyncPlan) -> None:
        now = time.monotonic()
        with self._mutual_sync_plan_lock:
            expired = [key for key, (created, _) in self._mutual_sync_plans.items() if now - created > 600]
            for key in expired:
                self._mutual_sync_plans.pop(key, None)
            if len(self._mutual_sync_plans) >= 64:
                oldest = min(self._mutual_sync_plans, key=lambda key: self._mutual_sync_plans[key][0])
                self._mutual_sync_plans.pop(oldest, None)
            plan.plan_id = uuid.uuid4().hex
            self._mutual_sync_plans[plan.plan_id] = (now, plan)

    @staticmethod
    def _plan_signature(plan: MutualSyncPlan) -> set[tuple[str, str, str, str, str, str]]:
        return {
            (
                entry.skill_id.casefold(),
                entry.source_agent,
                entry.target_agent,
                entry.status,
                entry.source_hash,
                json.dumps([check.to_dict() for check in entry.checks], sort_keys=True, separators=(",", ":")),
            )
            for entry in plan.entries
        }

    def get_sync_transaction(self, transaction_id: str) -> dict | None:
        return self.sync_manager.get_transaction(transaction_id)

    def list_sync_history(self) -> list[dict]:
        return self.sync_manager.list_history()

    # ------------------------------------------------------------------
    # Library API
    # ------------------------------------------------------------------
    def list_library(self) -> list[dict]:
        return [s.to_dict() for s in self.library_manager.list_library_skills(self._agents)]

    def get_library_skill(self, skill_id: str) -> dict | None:
        skill = self.library_manager.get_library_skill(skill_id, self._agents)
        return skill.to_dict() if skill else None

    def import_library_skill(self, skill_id: str, source_agent: str) -> dict:
        skill = self._require_skill(skill_id)
        source_skill = self._skill_for_agent(skill, source_agent)
        return self.library_manager.import_skill(source_skill, source_agent)

    def remove_library_skill(self, skill_id: str) -> dict:
        return self.library_manager.remove_from_library(skill_id)

    def deploy_library_skill(
        self,
        skill_id: str,
        targets: list[str],
        confirm_warning: bool = False,
        force_replace: bool = False,
    ) -> dict:
        library_skill = self.library_manager.get_library_skill(skill_id)
        if library_skill is None:
            raise KeyError(f"Library Skill not found: {skill_id}")
        skill = Skill(
            id=library_skill.id,
            name=library_skill.name,
            display_name=library_skill.display_name,
            summary=library_skill.summary,
            category=library_skill.category,
            tags=library_skill.tags,
            source=library_skill.source,
            path=str(Path(library_skill.library_path) / "SKILL.md"),
            hash=library_skill.hash,
        )
        return self.sync_manager.start_batch_sync(
            skill,
            targets,
            {
                "confirm_warning": confirm_warning,
                "force_replace": force_replace,
            },
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _build_mutual_sync_plan(self, agent_ids: list[str]) -> MutualSyncPlan:
        selected = list(dict.fromkeys(str(agent_id) for agent_id in agent_ids if str(agent_id)))
        if len(selected) < 2:
            raise ValueError("Select at least two installed Harnesses")

        agent_by_id = {agent.id: agent for agent in self._agents}
        adapter_by_id = {adapter.agent_id: adapter for adapter in self.agent_scanner.adapters}
        unknown = [agent_id for agent_id in selected if agent_id not in agent_by_id or not agent_by_id[agent_id].installed]
        if unknown:
            raise ValueError("Harness is not installed: " + ", ".join(unknown))

        skills_by_agent: dict[str, list[Skill]] = {}
        for agent_id in selected:
            adapter = adapter_by_id.get(agent_id)
            if adapter is None:
                raise ValueError("Harness is not supported: " + agent_id)
            skills: list[Skill] = []
            for root in adapter.get_skill_paths():
                for skill_dir in adapter._iter_skill_dirs(Path(root)):
                    discovered_path = find_skill_md(skill_dir)
                    if discovered_path is None:
                        continue
                    path = discovered_path.resolve()
                    parsed = self.skill_scanner.parser.parse(path)
                    name = str(parsed.get("name") or skill_dir.name).strip()
                    skill_id = name.casefold()
                    skill = Skill(
                        id=skill_id,
                        name=name,
                        display_name=str(parsed.get("display_name") or name),
                        description=str(parsed.get("description") or ""),
                        version=parsed.get("version"),
                        source=self.skill_scanner.source_detector.detect(path.parent),
                        path=str(path),
                        installed_agents=[agent_id],
                        locations={agent_id: True},
                        installed_locations={agent_id: {"path": str(path.parent), "enabled": True}},
                        hash=compute_skill_md_hash(path),
                    )
                    skills.append(skill)
            skills_by_agent[agent_id] = skills

        planner = MutualSyncPlanner(self.agent_scanner.adapters, self.preflight_checker)
        return planner.build(selected, skills_by_agent)

    def _find_skill(self, skill_id: str) -> Skill | None:
        for skill in self._skills:
            if skill.id == skill_id or skill.name == skill_id:
                return skill
        return None

    def _require_skill(self, skill_id: str) -> Skill:
        skill = self._find_skill(skill_id)
        if skill is None:
            raise KeyError(f"Skill not found: {skill_id}")
        return skill

    @staticmethod
    def _with_library_info(data: dict, library_skill) -> dict:
        data = dict(data)
        if library_skill is None:
            data["inLibrary"] = False
            data["libraryHash"] = None
            data["libraryPath"] = None
            data["libraryDeployments"] = {}
        else:
            data["inLibrary"] = True
            data["libraryHash"] = library_skill.hash
            data["libraryPath"] = library_skill.library_path
            data["libraryDeployments"] = {
                agent: state.to_dict()
                for agent, state in library_skill.deployments.items()
            }
        return data

    def _skill_for_agent(self, skill: Skill, source_agent: str) -> Skill:
        if source_agent and source_agent in skill.installed_locations:
            info = skill.installed_locations[source_agent]
            path = info.get("path", "")
            if path:
                skill_md = find_skill_md(path) or find_skill_md(Path(path))
                return Skill(
                    id=skill.id,
                    name=skill.name,
                    display_name=skill.display_name,
                    description=skill.description,
                    summary=skill.summary,
                    category=skill.category,
                    tags=skill.tags,
                    version=skill.version,
                    source=skill.source,
                    path=str(skill_md or (Path(path) / "SKILL.md")),
                    hash=skill.hash,
                    installed_agents=[source_agent],
                    locations={source_agent: True},
                    installed_locations={source_agent: dict(info)},
                    files=list(skill.files),
                    status=skill.status,
                    enabled=skill.enabled,
                )
        return skill

    @staticmethod
    def _installed_dirs(skill: Skill) -> list[str]:
        paths: list[str] = []
        for info in skill.installed_locations.values():
            path = info.get("path")
            if path and path not in paths:
                paths.append(path)
        # Fallback for older data.
        fallback = skill.path
        if fallback and fallback not in paths:
            paths.append(fallback)
        return paths


# Convenience module-level helpers for scripts/tests.
_default_api: SkillsAPI | None = None


def _get_api() -> SkillsAPI:
    global _default_api
    if _default_api is None:
        _default_api = SkillsAPI()
    return _default_api


def list_skills() -> list[dict]:
    return _get_api().list_skills()


def get_skill(skill_id: str) -> dict | None:
    return _get_api().get_skill(skill_id)


def rescan() -> dict[str, Any]:
    return _get_api().rescan()
