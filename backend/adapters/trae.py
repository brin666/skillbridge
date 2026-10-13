"""TRAE adapter."""

from __future__ import annotations

from pathlib import Path

from .base import AgentAdapter


class TraeAdapter(AgentAdapter):
    agent_id = "trae"
    display_name = "TRAE"

    def capabilities(self) -> list[str]:
        return ['filesystem', 'shell', 'patch']

    def _candidate_skill_paths(self) -> list[Path]:
        paths: list[Path] = []
        home = self._path_from_env("TRAE_HOME")
        if home is not None:
            paths.append(home / "skills")
        paths.append(Path.home() / ".trae" / "skills")
        paths.append(Path.home() / ".trae-cn" / "skills")
        paths.append(self.project_dir / ".trae" / "skills")
        return paths
