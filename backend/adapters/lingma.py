"""Lingma / Qoder CN adapter.

This covers both 通义灵码 (Tongyi Lingma) and the Qoder CN client. The exact
local Skill directories may differ between versions, so several common roots
are checked.
"""

from __future__ import annotations

from pathlib import Path

from .base import AgentAdapter


class LingmaAdapter(AgentAdapter):
    agent_id = "lingma"
    display_name = "通义灵码 / Qoder CN"

    def capabilities(self) -> list[str]:
        return ['filesystem', 'shell']

    def _candidate_skill_paths(self) -> list[Path]:
        paths: list[Path] = []
        home = self._path_from_env("LINGMA_HOME", "QODER_HOME")
        if home is not None:
            paths.append(home / "skills")
        paths.append(Path.home() / ".lingma" / "skills")
        paths.append(Path.home() / ".qoder" / "skills")
        paths.append(Path.home() / ".tongyi-lingma" / "skills")
        paths.append(self.project_dir / ".lingma" / "skills")
        paths.append(self.project_dir / ".qoder" / "skills")
        return paths
