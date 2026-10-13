"""Skill metadata cache.

Cache location: ``~/.skillbridge/cache/skills.json``.

Each cache entry stores:
- hash
- summary
- source
- last_scan_time

When a Skill's content hash has not changed, callers can reuse the cached
summary/source instead of recomputing them.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .hash_utils import compute_skill_hash

CACHE_VERSION = 1


class CacheManager:
    """Reads and writes SkillBridge cache entries."""

    def __init__(self, cache_dir: str | Path | None = None) -> None:
        self.cache_dir = Path(cache_dir or Path.home() / ".skillbridge" / "cache")
        self.cache_file = self.cache_dir / "skills.json"
        self._data = self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get(self, skill_id: str) -> dict | None:
        entry = self._data.get("skills", {}).get(skill_id)
        if entry is None:
            return None
        return dict(entry)

    def set(self, skill_id: str, data: dict) -> None:
        skills = self._data.setdefault("skills", {})
        skills[skill_id] = data
        self._save()

    def remove(self, skill_id: str) -> None:
        self._data.setdefault("skills", {}).pop(skill_id, None)
        self._save()

    def all(self) -> dict[str, dict]:
        return {k: dict(v) for k, v in self._data.get("skills", {}).items()}

    def compute_skill_hash(self, skill_dir: str | Path) -> str:
        """Compute a content hash for all files under a Skill directory."""
        return compute_skill_hash(skill_dir)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _load(self) -> dict:
        if not self.cache_file.is_file():
            return {"version": CACHE_VERSION, "skills": {}}
        try:
            data = json.loads(self.cache_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": CACHE_VERSION, "skills": {}}
        if not isinstance(data, dict):
            return {"version": CACHE_VERSION, "skills": {}}
        data.setdefault("skills", {})
        return data

    def _save(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # Write atomically to avoid a partially-written cache file.
        tmp_file = self.cache_file.with_suffix(".json.tmp")
        tmp_file.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp_file, self.cache_file)

    @staticmethod
    def _is_ignored(path: Path) -> bool:
        return any(part in {".git", "__pycache__", ".venv", "node_modules"} for part in path.parts)

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
