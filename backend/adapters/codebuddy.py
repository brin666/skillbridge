"""CodeBuddy adapter."""

from __future__ import annotations

from pathlib import Path

from .base import AgentAdapter


class CodeBuddyAdapter(AgentAdapter):
    agent_id = "codebuddy"
    display_name = "CodeBuddy"
    version_command = ("codebuddy", "--version")

    def capabilities(self) -> list[str]:
        return ['filesystem', 'shell', 'patch']

    def _candidate_skill_paths(self) -> list[Path]:
        paths: list[Path] = []
        home = self._path_from_env("CODEBUDDY_HOME")
        if home is not None:
            paths.append(home / "skills")
        paths.append(Path.home() / ".codebuddy" / "skills")
        paths.append(self.project_dir / ".codebuddy" / "skills")
        return paths
