"""Stage Skill directories and atomically install portable SKILL.md payloads."""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

from ..skill_files import find_skill_md

DEFAULT_TMP_ROOT = Path.home() / ".skillbridge" / "tmp"


class Installer:
    """Safe local Skill copy/move operations."""

    def __init__(self, tmp_root: str | Path | None = None) -> None:
        self.tmp_root = Path(tmp_root or DEFAULT_TMP_ROOT)

    def prepare_temp_path(self, skill_id: str) -> Path:
        """Return a unique temporary directory path for staging."""
        safe_id = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in skill_id)
        safe_id = safe_id.strip(".-") or "skill"
        return self.tmp_root / f"{safe_id}-{uuid.uuid4().hex[:8]}"

    def copy_skill_to_temp(self, source_dir: str | Path, temp_path: str | Path) -> Path:
        """Copy a full Skill directory into the temporary staging area."""
        source = Path(source_dir).resolve()
        destination = Path(temp_path).resolve()
        if not source.is_dir():
            raise FileNotFoundError(f"Source Skill directory not found: {source}")
        if destination.exists():
            raise FileExistsError(f"Temporary path already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            source,
            destination,
            symlinks=True,
            copy_function=shutil.copy2,
        )
        return destination

    def copy_skill_md_to_temp(self, source_dir: str | Path, temp_path: str | Path) -> Path:
        """Stage only SKILL.md, leaving support files untouched."""
        source = Path(source_dir).resolve()
        destination = Path(temp_path).resolve()
        source_md = find_skill_md(source)
        if source_md is None:
            raise FileNotFoundError(f"Source SKILL.md not found in: {source}")
        if destination.exists():
            raise FileExistsError(f"Temporary path already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.mkdir()
        shutil.copy2(source_md, destination / "SKILL.md")
        return destination

    def copy_skill_to_target(self, source_dir: str | Path, target_dir: str | Path) -> Path:
        """Copy a full Skill directory directly to a target location.

        This is used only for non-atomic fallback paths; normal sync uses
        :meth:`move_skill_to_target` for the final commit.
        """
        source = Path(source_dir).resolve()
        destination = Path(target_dir).resolve()
        if destination.exists():
            raise FileExistsError(f"Target Skill already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not source.is_dir():
            raise FileNotFoundError(f"Source Skill directory not found: {source}")
        shutil.copytree(
            source,
            destination,
            symlinks=True,
            copy_function=shutil.copy2,
        )
        return destination

    def install_skill_md(self, temp_dir: str | Path, target_dir: str | Path, transaction_id: str) -> Path:
        """Atomically replace only the target SKILL.md, preserving its siblings."""
        source = Path(temp_dir).resolve() / "SKILL.md"
        if not source.is_file():
            raise FileNotFoundError(f"Staged SKILL.md not found: {source}")
        return self.install_skill_md_bytes(source.read_bytes(), target_dir, transaction_id)

    def install_skill_md_bytes(
        self,
        payload: bytes,
        target_dir: str | Path,
        transaction_id: str,
    ) -> Path:
        """Atomically install the exact payload already validated in memory."""
        destination = Path(target_dir).resolve()
        destination.mkdir(parents=True, exist_ok=True)
        temp_file = destination / f".SKILL.md.skillbridge-{transaction_id}.tmp"
        target_file = destination / "SKILL.md"
        try:
            with temp_file.open("xb") as stream:
                stream.write(payload)
            os.replace(temp_file, target_file)
        finally:
            if temp_file.exists():
                temp_file.unlink()
        return target_file

    def move_skill_to_target(self, temp_dir: str | Path, target_dir: str | Path) -> Path:
        """Atomically move a verified temp Skill into the target location."""
        source = Path(temp_dir).resolve()
        destination = Path(target_dir).resolve()
        if destination.exists():
            raise FileExistsError(f"Target Skill already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        return destination
