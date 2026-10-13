"""Local Skill management operations.

Phase 4A implements safe local-only operations:
- open folder / SKILL.md
- enable / disable (move between ``skills`` and ``skills_disabled``)
- uninstall (move into trash)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..skill_files import find_skill_md

from .trash_manager import TrashManager

DISABLED_SUFFIX = "_disabled"


class SkillManager:
    """Performs validated local Skill management actions."""

    def __init__(self, trash_manager: TrashManager | None = None) -> None:
        self.trash = trash_manager or TrashManager()

    # ------------------------------------------------------------------
    # Public operations
    # ------------------------------------------------------------------
    def open_folder(self, skill_path: str | Path) -> dict:
        skill_dir = self._resolve_skill_dir(skill_path)
        self._validate_skill_dir(skill_dir)
        self._open_path(skill_dir)
        return {"success": True, "message": str(skill_dir)}

    def open_file(self, skill_path: str | Path) -> dict:
        skill_dir = self._resolve_skill_dir(skill_path)
        self._validate_skill_dir(skill_dir)
        skill_md = find_skill_md(skill_dir)
        if skill_md is None:
            raise FileNotFoundError("SKILL.md not found")
        self._open_path(skill_md)
        return {"success": True, "message": str(skill_md)}

    def disable(self, skill_path: str | Path, skill_id: str) -> dict:
        skill_dir = self._resolve_skill_dir(skill_path)
        self._validate_skill_dir(skill_dir)
        if not skill_dir.is_dir():
            raise FileNotFoundError(f"Skill directory not found: {skill_dir}")

        disabled_dir = self._disabled_dir_for(skill_dir)
        if disabled_dir.exists():
            raise FileExistsError(f"Disabled Skill already exists: {disabled_dir}")

        disabled_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(skill_dir), str(disabled_dir))
        return {"success": True, "path": str(disabled_dir), "enabled": False}

    def enable(self, skill_path: str | Path, skill_id: str) -> dict:
        skill_dir = self._resolve_skill_dir(skill_path)
        self._validate_skill_dir(skill_dir)

        # If the path is already a disabled location, move it back to active.
        if self._is_disabled_location(skill_dir):
            disabled_dir = skill_dir
            active_dir = self._active_dir_for_disabled(disabled_dir)
            if active_dir.exists():
                raise FileExistsError(f"Active Skill already exists: {active_dir}")
            active_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(disabled_dir), str(active_dir))
            return {"success": True, "path": str(active_dir), "enabled": True}

        # Otherwise locate the disabled sibling and restore it.
        active_dir = skill_dir
        disabled_dir = self._disabled_dir_for(active_dir)
        if not disabled_dir.is_dir():
            raise FileNotFoundError(f"Disabled Skill not found: {disabled_dir}")
        if active_dir.exists():
            raise FileExistsError(f"Active Skill already exists: {active_dir}")
        active_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(disabled_dir), str(active_dir))
        return {"success": True, "path": str(active_dir), "enabled": True}

    def uninstall(self, skill_paths: list[str | Path], skill_id: str) -> dict:
        moved: list[str] = []
        for raw_path in skill_paths:
            path = Path(raw_path).resolve()
            if not path.is_dir():
                continue
            self._validate_skill_dir(path)
            destination = self.trash.trash(path, skill_id)
            moved.append(str(destination))
        if not moved:
            raise FileNotFoundError("No installed Skill directories found to uninstall")
        return {"success": True, "message": "Skill moved to trash", "trashPaths": moved}

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------
    def _resolve_skill_dir(self, skill_path: str | Path) -> Path:
        path = Path(skill_path).resolve()
        if path.is_file() or (path.suffix and path.name.lower() == "skill.md"):
            path = path.parent
        return path

    def _validate_skill_dir(self, skill_dir: Path) -> None:
        if not skill_dir.is_absolute():
            raise ValueError("Skill path must be absolute")
        if skill_dir == skill_dir.anchor:
            raise ValueError("Skill path cannot be a filesystem root")
        try:
            skill_dir.resolve().relative_to(self.trash.trash_root.resolve())
        except ValueError:
            return
        raise ValueError("Skill path is inside the trash directory")

    def _disabled_dir_for(self, active_skill_dir: Path) -> Path:
        active_root = active_skill_dir.parent
        disabled_root = active_root.parent / f"{active_root.name}{DISABLED_SUFFIX}"
        return disabled_root / active_skill_dir.name

    def _is_disabled_location(self, skill_dir: Path) -> bool:
        return skill_dir.parent.name.endswith(DISABLED_SUFFIX)

    def _active_dir_for_disabled(self, disabled_skill_dir: Path) -> Path:
        disabled_root = disabled_skill_dir.parent
        active_root = disabled_root.parent / disabled_root.name[: -len(DISABLED_SUFFIX)]
        return active_root / disabled_skill_dir.name

    @staticmethod
    def _open_path(path: Path) -> None:
        target = str(path)
        if sys.platform == "win32":
            os.startfile(target)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])
