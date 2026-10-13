"""Safe trash manager for Skill uninstall.

Uninstall moves a Skill directory to ``~/.skillbridge/trash/<date>/<skill>/``
instead of deleting it immediately. Metadata is stored next to the trashed
directory so a future restore API can bring it back.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_TRASH_ROOT = Path.home() / ".skillbridge" / "trash"


class TrashManager:
    """Moves Skill directories into a local trash area."""

    def __init__(self, trash_root: str | Path | None = None) -> None:
        self.trash_root = Path(trash_root or DEFAULT_TRASH_ROOT)

    def trash(self, skill_dir: str | Path, skill_id: str) -> Path:
        """Move ``skill_dir`` into trash and write a metadata file.

        Returns the trashed destination path.
        """
        source = Path(skill_dir).resolve()
        if not source.is_dir():
            raise FileNotFoundError(f"Skill directory not found: {source}")

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        destination = self.trash_root / date_str / self._safe_name(skill_id)
        destination = self._unique_path(destination)

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))

        metadata = {
            "skillId": skill_id,
            "originalPath": str(source),
            "trashedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "trashPath": str(destination),
        }
        (destination / "_meta.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return destination

    # ------------------------------------------------------------------
    def _safe_name(self, value: str) -> str:
        cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in value.strip())
        return cleaned.strip(".-") or "skill"

    def _unique_path(self, path: Path) -> Path:
        if not path.exists():
            return path
        index = 1
        while True:
            candidate = path.with_name(f"{path.name}-{index}")
            if not candidate.exists():
                return candidate
            index += 1
