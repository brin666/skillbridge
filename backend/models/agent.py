"""Agent data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .skill import Skill


@dataclass
class Agent:
    """A detected AI agent and its local skill installation state."""

    id: str
    name: str
    installed: bool = False
    version: str | None = None
    skill_count: int = 0
    skill_paths: list[str] = field(default_factory=list)
    skills: list[Skill] = field(default_factory=list)

    def to_dict(self, include_skills: bool = False) -> dict:
        data = {
            "id": self.id,
            "name": self.name,
            "installed": self.installed,
            "version": self.version,
            "skillCount": self.skill_count,
            "skillPaths": list(self.skill_paths),
        }
        if include_skills:
            data["skills"] = [s.to_dict() for s in self.skills]
        return data

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"Agent(id={self.id!r}, installed={self.installed}, skill_count={self.skill_count})"
