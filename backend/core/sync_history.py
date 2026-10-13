"""Sync history persistence.

Stores one JSON file per sync transaction under
``~/.skillbridge/history/sync/``.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..models.sync import SyncStep, SyncTransaction

DEFAULT_HISTORY_DIR = Path.home() / ".skillbridge" / "history" / "sync"


class SyncHistoryManager:
    """Reads and writes sync transaction history."""

    def __init__(self, history_dir: str | Path | None = None) -> None:
        self.history_dir = Path(history_dir or DEFAULT_HISTORY_DIR)
        self._lock = threading.RLock()

    def create(self, transaction: SyncTransaction) -> Path:
        self.history_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(transaction.id)
        temporary = self.history_dir / f".{transaction.id}.{uuid.uuid4().hex}.tmp"
        with self._lock:
            try:
                temporary.write_text(
                    json.dumps(transaction.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8",
                )
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        return path

    def update(self, transaction: SyncTransaction) -> None:
        self.create(transaction)

    def get(self, transaction_id: str) -> SyncTransaction | None:
        path = self._path(transaction_id)
        if not path.is_file():
            return None
        try:
            with self._lock:
                data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return self._from_dict(data)

    def list(self, limit: int = 50) -> list[SyncTransaction]:
        if not self.history_dir.is_dir():
            return []
        entries = []
        for path in self.history_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                entries.append(self._from_dict(data))
            except (OSError, json.JSONDecodeError):
                continue
        entries.sort(key=lambda tx: tx.start_time, reverse=True)
        return entries[:limit]

    # ------------------------------------------------------------------
    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _path(self, transaction_id: str) -> Path:
        return self.history_dir / f"{transaction_id}.json"

    @staticmethod
    def _from_dict(data: dict) -> SyncTransaction:
        return SyncTransaction(
            id=str(data.get("id", "")),
            skill=str(data.get("skill", "")),
            target_agent=str(data.get("targetAgent", "")),
            source_agent=str(data.get("sourceAgent", "")),
            start_time=str(data.get("startTime", "")),
            end_time=str(data.get("endTime", "")),
            status=str(data.get("status", "pending")),
            progress=int(data.get("progress", 0)),
            message=str(data.get("message", "")),
            steps=[
                SyncStep(
                    name=str(step.get("name", "")),
                    status=str(step.get("status", "pending")),
                    message=str(step.get("message", "")),
                    started_at=str(step.get("startedAt", "")),
                    ended_at=str(step.get("endedAt", "")),
                )
                for step in data.get("steps", [])
            ],
            error=str(data.get("error", "")),
        )
