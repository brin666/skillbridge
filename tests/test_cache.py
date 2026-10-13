"""Tests for the Skill cache system."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core.cache_manager import CacheManager
from backend.core.skill_scanner import SkillScanner


def write_skill(skill_dir: Path, description: str) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: pdf\ndescription: {description}\n---\n",
        encoding="utf-8",
    )


class CacheManagerTests(unittest.TestCase):
    def test_first_scan_creates_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "cache"
            skill_root = Path(tmp) / "skills"
            write_skill(skill_root / "pdf", "PDF tools")

            cache = CacheManager(cache_dir)
            scanner = SkillScanner(cache_manager=cache)
            skills = scanner.scan_skill_paths([skill_root], agent_id="codex")

            self.assertEqual(len(skills), 1)
            self.assertTrue((cache_dir / "skills.json").is_file())
            entry = cache.get("pdf")
            self.assertIsNotNone(entry)
            self.assertEqual(entry["hash"], skills[0].hash)
            self.assertTrue(entry["summary"])

    def test_hash_unchanged_reads_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "cache"
            skill_root = Path(tmp) / "skills"
            skill_dir = skill_root / "pdf"
            write_skill(skill_dir, "PDF tools")

            cache = CacheManager(cache_dir)
            scanner = SkillScanner(cache_manager=cache)
            scanner.scan_skill_paths([skill_root], agent_id="codex")

            # The localized summary cache is authoritative for the current locale.
            entry = cache.get("pdf")
            entry["summaries"]["zh-CN"] = "缓存摘要"
            cache.set("pdf", entry)

            skills = scanner.scan_skill_paths([skill_root], agent_id="codex")
            self.assertEqual(skills[0].summary, "缓存摘要")

    def test_file_change_triggers_reparse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "cache"
            skill_root = Path(tmp) / "skills"
            skill_dir = skill_root / "pdf"
            write_skill(skill_dir, "Old description")

            cache = CacheManager(cache_dir)
            scanner = SkillScanner(cache_manager=cache)
            scanner.scan_skill_paths([skill_root], agent_id="codex")
            old_hash = cache.get("pdf")["hash"]

            write_skill(skill_dir, "New description")
            skills = scanner.scan_skill_paths([skill_root], agent_id="codex")
            new_hash = cache.get("pdf")["hash"]

            self.assertNotEqual(old_hash, new_hash)
            self.assertNotEqual(skills[0].summary, "")
            self.assertIn("新", skills[0].summary)


if __name__ == "__main__":
    unittest.main()
