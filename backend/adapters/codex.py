"""Codex adapter."""

from __future__ import annotations

from pathlib import Path

from .base import AgentAdapter


class CodexAdapter(AgentAdapter):
    agent_id = "codex"
    display_name = "Codex"
    version_command = ("codex", "--version")

    def capabilities(self) -> list[str]:
        return ['filesystem', 'shell', 'patch']

    def _candidate_skill_paths(self) -> list[Path]:
        paths: list[Path] = []
        home = self._path_from_env("CODEX_HOME", fallback="~/.codex")
        if home is not None:
            paths.append(home / "skills")
        paths.append(Path.home() / ".codex" / "skills")
        paths.append(self.project_dir / ".codex" / "skills")
        return paths
