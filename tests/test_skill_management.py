"""Tests for Phase 4A basic Skill management."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.api.skills import SkillsAPI
from backend.core.agent_scanner import AgentScanner
from backend.core.cache_manager import CacheManager
from backend.core.skill_manager import SkillManager
from backend.core.skill_scanner import SkillScanner
from backend.core.trash_manager import TrashManager
from backend.models.agent import Agent


class FakeAgentScanner(AgentScanner):
    def __init__(self, skill_paths: list[str]):
        super().__init__(adapters=[])
        self._skill_paths = skill_paths

    def scan(self, include_skills: bool = False):
        return [
            Agent(
                id="codex",
                name="Codex",
                installed=True,
                skill_count=0,
                skill_paths=self._skill_paths,
            )
        ]


def write_skill(root: Path, name: str = "pdf") -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: PDF management skill\n---\n",
        encoding="utf-8",
    )
    return skill_dir


class SkillManagementTests(unittest.TestCase):
    def _make_api(self, tmp: Path, root: Path) -> tuple[SkillsAPI, Path]:
        cache_dir = tmp / "cache"
        trash_root = tmp / "trash"
        agent_scanner = FakeAgentScanner([str(root)])
        skill_scanner = SkillScanner(cache_manager=CacheManager(cache_dir))
        skill_manager = SkillManager(trash_manager=TrashManager(trash_root))
        api = SkillsAPI(
            agent_scanner=agent_scanner,
            skill_scanner=skill_scanner,
            skill_manager=skill_manager,
        )
        return api, cache_dir

    def test_open_missing_folder_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = SkillManager()
            with self.assertRaises(FileNotFoundError):
                manager.open_folder(Path(tmp) / "does-not-exist")

    def test_disable_moves_to_disabled_and_changes_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "skills"
            write_skill(root)
            api, cache_dir = self._make_api(base, root)

            skill = api.get_skill("pdf")
            self.assertIsNotNone(skill)
            self.assertEqual(skill["status"], "enabled")
            self.assertTrue(skill["enabled"])

            result = api.disable_skill("pdf")
            self.assertTrue(result["success"])
            self.assertFalse((root / "pdf").exists())
            self.assertTrue((base / "skills_disabled" / "pdf" / "SKILL.md").exists())

            disabled = api.get_skill("pdf")
            self.assertIsNotNone(disabled)
            self.assertEqual(disabled["status"], "disabled")
            self.assertFalse(disabled["enabled"])
            self.assertTrue(CacheManager(cache_dir).get("pdf") is not None)

    def test_enable_restores_active_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "skills"
            write_skill(root)
            api, _ = self._make_api(base, root)

            api.disable_skill("pdf")
            result = api.enable_skill("pdf")
            self.assertTrue(result["success"])
            self.assertTrue((root / "pdf" / "SKILL.md").exists())
            self.assertFalse((base / "skills_disabled" / "pdf").exists())

            enabled = api.get_skill("pdf")
            self.assertEqual(enabled["status"], "enabled")
            self.assertTrue(enabled["enabled"])

    def test_uninstall_moves_skill_to_trash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "skills"
            write_skill(root)
            api, cache_dir = self._make_api(base, root)

            result = api.uninstall_skill("pdf")
            self.assertTrue(result["success"])
            self.assertEqual(result["message"], "Skill moved to trash")
            self.assertFalse((root / "pdf").exists())
            self.assertTrue((base / "trash").exists())
            self.assertTrue(any((base / "trash").rglob("_meta.json")))
            self.assertIsNone(api.get_skill("pdf"))
            self.assertIsNone(CacheManager(cache_dir).get("pdf"))


if __name__ == "__main__":
    unittest.main()
