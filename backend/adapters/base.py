"""Base adapter contract for SkillBridge.

Every supported AI Agent gets its own adapter. The scanner never embeds
agent-specific path logic; it only works against this interface.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from ..skill_files import find_skill_md, iter_skill_dirs
from ..models.skill import Skill


class AgentAdapter:
    """Base class for all Agent adapters.

    Subclasses should set ``agent_id`` and ``display_name`` and override at
    least :meth:`_candidate_skill_paths`.
    """

    agent_id = "base"
    display_name = "Base Agent"
    version_command: tuple[str, ...] | None = None

    def __init__(self, project_dir: Path | str | None = None) -> None:
        self.project_dir = Path(project_dir or Path.cwd()).resolve()
        self._version_checked = False
        self._version_value: str | None = None

    # ------------------------------------------------------------------
    # Required public contract
    # ------------------------------------------------------------------
    def detect(self) -> bool:
        """Return True if this Agent appears to be installed locally."""
        if self._existing_skill_paths():
            return True
        return self.get_version() is not None

    def get_name(self) -> str:
        """Return the human readable Agent name."""
        return self.display_name

    def get_skill_paths(self) -> list[str]:
        """Return absolute paths of existing Skill root directories."""
        return [str(p) for p in self._existing_skill_paths()]

    def scan_skills(self) -> list[Skill]:
        """Return a basic Skill list for this Agent.

        Phase 1 only detects Skill directories that contain a ``SKILL.md``.
        Full frontmatter parsing and merging are implemented in Phase 2.
        """
        skills: list[Skill] = []
        seen: set[str] = set()
        for root in self._existing_skill_paths():
            for skill_dir in self._iter_skill_dirs(root):
                skill_md = find_skill_md(skill_dir)
                if skill_md is None:
                    continue
                skill_id = skill_dir.name.strip().lower()
                if not skill_id or skill_id in seen:
                    continue
                seen.add(skill_id)
                skills.append(
                    Skill(
                        id=skill_id,
                        name=skill_dir.name,
                        display_name=skill_dir.name,
                        path=str(skill_md),
                        locations={self.agent_id: True},
                    )
                )
        return skills

    def supports_skill(self, skill: Skill) -> bool | str:
        """Whether this Agent can install the given Skill.

        Returns ``True``, ``False``, or ``"unknown"``.
        The default is conservative: the unified ``SKILL.md`` layout is
        supported by every adapter.
        """
        return bool(skill and skill.path)

    def capabilities(self) -> list[str]:
        """Return the Agent's capability names.

        Used by Preflight to warn when a Skill requires capabilities the
        target Agent does not advertise.
        """
        return ["filesystem", "shell"]

    def supports_allowed_tools(self) -> bool | str:
        """Whether this Harness honors the experimental ``allowed-tools`` field.

        Return ``True`` or ``False`` only when this behavior has been verified
        for the Harness. The conservative default is unknown.
        """
        return "unknown"

    def install_skill(self, skill: Skill) -> None:
        """Install a Skill into this Agent (Safe Sync is Phase 7)."""
        raise NotImplementedError("Skill installation is not available in Phase 1.")

    def remove_skill(self, skill: Skill) -> None:
        """Remove a Skill from this Agent (management is Phase 8)."""
        raise NotImplementedError("Skill removal is not available in Phase 1.")

    # ------------------------------------------------------------------
    # Helpers for subclasses
    # ------------------------------------------------------------------
    def _candidate_skill_paths(self) -> list[Path]:
        """Return all candidate Skill root paths for this Agent.

        Subclasses should override this. Paths do not need to exist yet.
        """
        return []

    def _existing_skill_paths(self) -> list[Path]:
        seen: set[str] = set()
        result: list[Path] = []
        for path in self._candidate_skill_paths():
            try:
                resolved = path.expanduser().resolve()
            except OSError:
                continue
            key = os.path.normcase(str(resolved))
            if key in seen or not resolved.is_dir():
                continue
            seen.add(key)
            result.append(resolved)
        return result

    def _path_from_env(self, *env_names: str, fallback: str | None = None) -> Path | None:
        for name in env_names:
            value = os.environ.get(name)
            if value:
                return Path(value)
        if fallback:
            return Path(fallback).expanduser()
        return None

    def get_version(self) -> str | None:
        """Return a detected version string, or None.

        Subclasses may override this. The default implementation tries the
        optional ``version_command`` via PATH and returns the first line.
        """
        if self._version_checked:
            return self._version_value
        self._version_checked = True
        if not self.version_command:
            return None
        import shutil
        import subprocess

        executable = shutil.which(self.version_command[0])
        if not executable:
            return None
        try:
            proc = subprocess.run(
                (executable, *self.version_command[1:]),
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        first_line = (proc.stdout or proc.stderr).strip().splitlines()
        self._version_value = first_line[0].strip() if first_line else None
        return self._version_value

    def refresh_version_cache(self) -> None:
        """Allow the scanner to recheck the version once on the next scan."""
        self._version_checked = False
        self._version_value = None

    def _iter_skill_dirs(self, root: Path) -> Iterable[Path]:
        """Yield Skills found recursively beneath the configured Harness root."""
        yield from iter_skill_dirs(root)
