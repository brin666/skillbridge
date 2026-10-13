"""Qwen Code adapter."""

from __future__ import annotations

from pathlib import Path

from .base import AgentAdapter


class QwenAdapter(AgentAdapter):
    agent_id = "qwen"
    display_name = "Qwen Code"
    version_command = ("qwen-code", "--version")

    def capabilities(self) -> list[str]:
        return ['filesystem', 'shell']

    def _candidate_skill_paths(self) -> list[Path]:
        paths: list[Path] = []
        home = self._path_from_env("QWEN_CODE_HOME")
        if home is not None:
            paths.append(home / "skills")
        paths.append(Path.home() / ".qwen" / "skills")
        paths.append(Path.home() / ".qwen-code" / "skills")
        paths.append(self.project_dir / ".qwen" / "skills")
        paths.append(self.project_dir / ".qwen-code" / "skills")
        return paths
