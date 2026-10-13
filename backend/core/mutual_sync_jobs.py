"""Atomic persistence for observable, idempotent mutual-sync batches."""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path


class MutualSyncJobStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    @staticmethod
    def valid_id(job_id: str) -> bool:
        return bool(re.fullmatch(r"[0-9a-f]{32}", job_id))

    def save(self, job: dict) -> None:
        if not self.valid_id(job["id"]):
            raise ValueError("Invalid sync request id")
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.directory / f".{job['id']}.{uuid.uuid4().hex}.tmp"
        try:
            temporary.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
            os.replace(temporary, self.directory / f"{job['id']}.json")
        finally:
            temporary.unlink(missing_ok=True)

    def load(self) -> list[dict]:
        jobs = []
        for path in self.directory.glob("*.json"):
            if not self.valid_id(path.stem):
                continue
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
                if (job.get("id") == path.stem and isinstance(job.get("plan"), dict)
                        and isinstance(job.get("tasks"), list)
                        and job.get("status") in {"running", "success", "failed"}):
                    jobs.append(job)
            except (OSError, ValueError, AttributeError):
                continue
        return sorted(jobs, key=lambda job: job.get("startedAt", 0))

    def remove(self, job_id: str) -> None:
        if self.valid_id(job_id):
            (self.directory / f"{job_id}.json").unlink(missing_ok=True)
