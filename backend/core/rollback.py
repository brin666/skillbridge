"""Rollback manager for Safe Sync transactions."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_STATE_ROOT = Path.home() / ".skillbridge"


class RollbackManager:
    """Tracks sync transactions and cleans up temporary/partial files."""

    def __init__(self, state_root: str | Path | None = None) -> None:
        self.state_root = Path(state_root or DEFAULT_STATE_ROOT)
        self.transactions_dir = self.state_root / "transactions"
        self.tmp_root = self.state_root / "tmp"

    def begin(
        self,
        source: str | Path,
        target: str | Path,
        tmp: str | Path,
        target_existed: bool = False,
    ) -> str:
        """Create a sync transaction and return its id."""
        transaction_id = (
            "sync_"
            + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_")
            + uuid.uuid4().hex[:6]
        )
        record = {
            "id": transaction_id,
            "source": str(source),
            "target": str(target),
            "tmp": str(tmp),
            "targetExisted": target_existed,
            "status": "running",
            "createdAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self.transactions_dir.mkdir(parents=True, exist_ok=True)
        self._write(transaction_id, record)
        return transaction_id

    def commit(self, transaction_id: str) -> None:
        record = self._read(transaction_id)
        if record is None:
            return
        record["status"] = "committed"
        record["committedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._write(transaction_id, record)

    def rollback(self, transaction_id: str) -> None:
        record = self._read(transaction_id)
        if record is None:
            return

        tmp = Path(record.get("tmp", "")).resolve()
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)

        # Target files are restored by SyncManager at file granularity. Do not
        # recursively delete the target directory: it may contain unrelated
        # files or concurrent user changes.

        record["status"] = "rolled_back"
        record["rolledBackAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._write(transaction_id, record)

    def cleanup_tmp(self, transaction_id: str) -> None:
        record = self._read(transaction_id)
        if record is None:
            return
        tmp = Path(record.get("tmp", "")).resolve()
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)

    # ------------------------------------------------------------------
    def _path(self, transaction_id: str) -> Path:
        return self.transactions_dir / f"{transaction_id}.json"

    def _write(self, transaction_id: str, record: dict) -> None:
        self._path(transaction_id).write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _read(self, transaction_id: str) -> dict | None:
        path = self._path(transaction_id)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except (OSError, json.JSONDecodeError):
            return None
