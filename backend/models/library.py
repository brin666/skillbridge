"""Central Skill Library data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DeploymentState:
    """Deployment status of a Library Skill on one Agent."""

    installed: bool = False
    same_hash: bool = False
    path: str = ""
    status: str = "not_deployed"  # same | diverged | not_deployed | disabled | unknown

    def to_dict(self) -> dict:
        return {
            "installed": self.installed,
            "sameHash": self.same_hash,
            "path": self.path,
            "status": self.status,
        }


@dataclass
class LibrarySkill:
    """A Skill managed by SkillBridge Library."""

    id: str = ""
    name: str = ""
    display_name: str = ""
    summary: str = ""
    category: str = ""
    tags: list[str] = field(default_factory=list)
    library_path: str = ""
    hash: str = ""
    source: dict[str, Any] = field(default_factory=dict)
    imported_from: dict[str, str] = field(default_factory=dict)
    imported_at: str = ""
    deployments: dict[str, DeploymentState] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "displayName": self.display_name,
            "summary": self.summary,
            "category": self.category,
            "tags": list(self.tags),
            "libraryPath": self.library_path,
            "hash": self.hash,
            "source": dict(self.source),
            "importedFrom": dict(self.imported_from),
            "importedAt": self.imported_at,
            "deployments": {
                agent: state.to_dict() for agent, state in self.deployments.items()
            },
        }


@dataclass
class LibraryEntry:
    """Minimal index entry used by ``library/index.json``."""

    id: str = ""
    hash: str = ""
    source: dict[str, Any] = field(default_factory=dict)
    imported_from: dict[str, str] = field(default_factory=dict)
    imported_at: str = ""
    library_path: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "hash": self.hash,
            "source": dict(self.source),
            "importedFrom": dict(self.imported_from),
            "importedAt": self.imported_at,
            "libraryPath": self.library_path,
        }
