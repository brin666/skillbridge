"""Unified Skill data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Skill:
    """A single Skill discovered from one or more Agent installations."""

    id: str = ""
    name: str = ""
    display_name: str = ""
    description: str = ""
    summary: str = ""
    summaries: dict[str, str] = field(default_factory=dict)
    features: dict[str, list[str]] = field(default_factory=dict)
    category: str = ""
    tags: list[str] = field(default_factory=list)
    version: str | None = None
    source: dict[str, Any] = field(default_factory=dict)
    path: str = ""
    installed_agents: list[str] = field(default_factory=list)
    locations: dict[str, bool] = field(default_factory=dict)
    installed_locations: dict[str, dict[str, Any]] = field(default_factory=dict)
    files: list[str] = field(default_factory=list)
    hash: str = ""
    status: str = "enabled"
    enabled: bool = True
    last_modified: str = ""
    duplicate_group: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "displayName": self.display_name,
            "description": self.description,
            "summary": self.summary,
            "summaries": dict(self.summaries),
            "features": {language: list(items) for language, items in self.features.items()},
            "category": self.category,
            "tags": list(self.tags),
            "version": self.version,
            "source": dict(self.source),
            "path": self.path,
            "installedAgents": list(self.installed_agents),
            "installed_agents": list(self.installed_agents),
            "locations": dict(self.locations),
            "installedLocations": dict(self.installed_locations),
            "installed_locations": dict(self.installed_locations),
            "files": list(self.files),
            "hash": self.hash,
            "status": self.status,
            "enabled": self.enabled,
            "lastModified": self.last_modified,
            "duplicateGroup": self.duplicate_group,
            "duplicate_group": self.duplicate_group,
        }

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"Skill(id={self.id!r}, name={self.name!r}, path={self.path!r})"
