"""DeepSeek Harness (DSH) adapter.

DeepSeek Harness (``dsh``) is commonly installed and launched through
``npx @deepseek-ai/dsh web`` and therefore may not provide a global
``dsh`` executable on PATH. Detection intentionally uses multiple signals
instead of relying on a single :func:`shutil.which("dsh")` check:

A. a ``dsh`` executable found on PATH
B. the ``DSH_HOME`` environment variable pointing at a valid DSH Home
C. the default DSH Home ``~/.dsh``
D. reliable DSH signatures inside that Home (``profiles/``,
   ``cordis.patch.yml``, settings/sessions/storages, ...)

An empty ``~/.dsh`` is **not** a hit — a bare directory is not enough to
claim DSH is installed.

DSH is still iterating quickly, so nothing in this adapter pins a specific
version: :meth:`get_version` returns ``None`` when a version cannot be
detected, and that never means "not installed".
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from ..models.skill import Skill
from .base import AgentAdapter

#: File/directory names that mark a directory as a real DSH Home.
#: ``profiles/``, ``cordis.patch.yml``, ``settings.yaml``, ``sessions/`` and
#: ``storages/`` are created by DSH itself; ``workspace.json`` is a storage
#: file DSH writes once a workspace is registered.
DSH_HOME_SIGNATURES: tuple[str, ...] = (
    "profiles",
    "cordis.patch.yml",
    "settings.yaml",
    "sessions",
    "storages",
    "workspace.json",
)

#: Skill root DSH scans by default (``~/.agents/skills``).
DEFAULT_AGENTS_SKILL_ROOT = "~/.agents/skills"


def resolve_dsh_home(configured: str | Path | None = None) -> Path:
    """Resolve the DSH Home directory.

    Precedence: explicit configuration -> ``DSH_HOME`` -> ``~/.dsh``.
    """
    if configured:
        return Path(configured).expanduser()
    env_home = os.environ.get("DSH_HOME")
    if env_home:
        return Path(env_home).expanduser()
    return Path.home() / ".dsh"


def is_valid_dsh_home(home: str | Path) -> bool:
    """Return True when ``home`` carries reliable DSH signatures.

    A nonexistent or empty directory is never a valid DSH Home, so a bare
    ``~/.dsh`` does not cause a false positive.
    """
    path = Path(home).expanduser()
    if not path.is_dir():
        return False
    return any((path / signature).exists() for signature in DSH_HOME_SIGNATURES)


class DSHAdapter(AgentAdapter):
    """Adapter for DeepSeek Harness (``dsh``)."""

    agent_id = "dsh"
    display_name = "DeepSeek Harness"
    version_command = ("dsh", "--version")

    def __init__(
        self,
        project_dir: str | Path | None = None,
        dsh_home: str | Path | None = None,
    ) -> None:
        super().__init__(project_dir)
        self._configured_home = Path(dsh_home).expanduser() if dsh_home else None

    # ------------------------------------------------------------------
    # Required public contract
    # ------------------------------------------------------------------
    def detect(self) -> bool:
        """Detect DSH through multiple independent signals.

        Skill roots are intentionally NOT part of detection: a fresh DSH
        install has no skills yet and must still be recognized.
        """
        # Signal A: a dsh executable on PATH.
        if shutil.which("dsh"):
            return True
        # Signals B/C/D: a valid DSH Home — either via DSH_HOME or the
        # default ~/.dsh — carrying real DSH signatures.
        return is_valid_dsh_home(resolve_dsh_home(self._configured_home))

    def get_name(self) -> str:
        return self.display_name

    def get_skill_paths(self) -> list[str]:
        return super().get_skill_paths()

    def scan_skills(self) -> list[Skill]:
        return super().scan_skills()

    def supports_skill(self, skill: Skill) -> bool | str:
        return super().supports_skill(skill)

    def capabilities(self) -> list[str]:
        return ["filesystem", "shell", "patch"]

    # ------------------------------------------------------------------
    # Skill roots
    # ------------------------------------------------------------------
    def _candidate_skill_paths(self) -> list[Path]:
        paths: list[Path] = []
        # DSH scans ~/.agents/skills by default.
        paths.append(Path(DEFAULT_AGENTS_SKILL_ROOT).expanduser())
        # Do NOT assume ~/.dsh/skills — DSH has no such default. Extra skill
        # roots can be appended here dynamically once they are resolvable
        # from DSH configuration.
        return paths
