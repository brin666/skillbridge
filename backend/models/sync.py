"""Sync transaction data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SyncStep:
    """A single step inside a sync transaction."""

    name: str  # preflight | copy | validation | commit | rollback
    status: str = "pending"  # pending | running | success | failed | skipped
    message: str = ""
    started_at: str = ""
    ended_at: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "startedAt": self.started_at,
            "endedAt": self.ended_at,
        }


@dataclass
class SyncTransaction:
    """A persisted sync transaction record."""

    id: str
    skill: str
    target_agent: str
    source_agent: str = ""
    start_time: str = ""
    end_time: str = ""
    status: str = "pending"  # pending | running | success | failed | rollback | warning_required
    progress: int = 0
    message: str = ""
    steps: list[SyncStep] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "skill": self.skill,
            "sourceAgent": self.source_agent,
            "targetAgent": self.target_agent,
            "startTime": self.start_time,
            "endTime": self.end_time,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "steps": [s.to_dict() for s in self.steps],
            "error": self.error,
        }


@dataclass
class SyncResult:
    """API-facing sync result."""

    status: str
    transaction_id: str = ""
    message: str = ""
    target: str = ""
    reason: str = ""
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        data: dict[str, Any] = {
            "status": self.status,
            "transaction_id": self.transaction_id,
            "message": self.message,
            "target": self.target,
            "reason": self.reason,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "checks": list(self.checks),
        }
        return data
