"""Hermes adapter."""

from __future__ import annotations

from pathlib import Path

from .base import AgentAdapter


class HermesAdapter(AgentAdapter):
    agent_id = "hermes"
    display_name = "Hermes"
    version_command = ("hermes", "--version")

    def capabilities(self) -> list[str]:
        return ['filesystem', 'shell']

    def _candidate_skill_paths(self) -> list[Path]:
        paths: list[Path] = []
        home = self._path_from_env("HERMES_HOME")
        if home is not None:
            paths.append(home / "skills")
        paths.append(Path.home() / ".hermes" / "skills")
        paths.append(Path.home() / ".agents" / "skills")
        paths.append(self.project_dir / ".hermes" / "skills")
        paths.append(self.project_dir / ".agents" / "skills")
        return paths
