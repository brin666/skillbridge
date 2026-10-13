"""Claude Code adapter."""

from __future__ import annotations

from pathlib import Path

from .base import AgentAdapter


class ClaudeAdapter(AgentAdapter):
    agent_id = "claude"
    display_name = "Claude Code"
    version_command = ("claude", "--version")

    def capabilities(self) -> list[str]:
        return ['filesystem', 'shell', 'edit']

    def _candidate_skill_paths(self) -> list[Path]:
        paths: list[Path] = []
        home = self._path_from_env("CLAUDE_CONFIG_DIR")
        if home is not None:
            paths.append(home / "skills")
        paths.append(Path.home() / ".claude" / "skills")
        paths.append(self.project_dir / ".claude" / "skills")
        return paths
