"""Environment summary model used by the future /api/environment endpoint."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EnvironmentSummary:
    """A high-level snapshot of the local AI Skill environment."""

    health: int = 0
    agent_count: int = 0
    skill_count: int = 0
    unsynced_count: int = 0
    issue_count: int = 0
    agents: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "health": self.health,
            "agentCount": self.agent_count,
            "skillCount": self.skill_count,
            "unsyncedCount": self.unsynced_count,
            "issueCount": self.issue_count,
            "agents": [a.to_dict() for a in self.agents],
        }

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"EnvironmentSummary(health={self.health}, agents={self.agent_count}, "
            f"skills={self.skill_count}, unsynced={self.unsynced_count}, issues={self.issue_count})"
        )
