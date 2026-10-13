"""Tests for sync history persistence."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.adapters.base import AgentAdapter
from backend.core.cache_manager import CacheManager
from backend.core.installer import Installer
from backend.core.preflight import PreflightChecker
from backend.core.rollback import RollbackManager
from backend.core.sync_manager import SyncManager
from backend.models.skill import Skill


class FakeAdapter(AgentAdapter):
    agent_id = "trae"
    display_name = "TRAE"

    def __init__(self, root: Path):
        super().__init__()
        self.root = root

    def _candidate_skill_paths(self):
        return [self.root]

    def supports_skill(self, skill):
        return True

    def capabilities(self):
        return ["filesystem", "shell"]


def make_skill(root: Path, name: str = "pdf", clean: bool = True) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: PDF tools\nmetadata:\n  skillbridge-sync: allow\n---\n" if clean else f"---\nname: {name}\ndescription: PDF tools\n---\n",
        encoding="utf-8",
    )
    if clean:
        (skill_dir / "metadata.json").write_text(
            '{"repository": "https://github.com/example/pdf"}',
            encoding="utf-8",
        )
        (skill_dir / "scripts").mkdir(exist_ok=True)
    return skill_dir


def make_manager(base: Path, source_root: Path, target_root: Path) -> SyncManager:
    cache = CacheManager(base / "cache")
    adapter = FakeAdapter(target_root)
    checker = PreflightChecker(adapters=[adapter], cache_manager=cache)
    installer = Installer(tmp_root=base / "tmp")
    rollback = RollbackManager(state_root=base)
    return SyncManager(
        preflight_checker=checker,
        installer=installer,
        rollback_manager=rollback,
        cache_manager=cache,
    )


class SyncHistoryTests(unittest.TestCase):
    def test_successful_sync_saves_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_root = base / "target"
            target_root.mkdir()
            source_dir = make_skill(source_root)
            cache = CacheManager(base / "cache")
            skill = Skill(
                id="pdf",
                name="pdf",
                path=str(source_dir / "SKILL.md"),
                hash=cache.compute_skill_hash(source_dir),
            )
            manager = make_manager(base, source_root, target_root)
            result = manager.sync(skill, "trae", {})
            self.assertEqual(result["status"], "success")
            tx = manager.get_transaction(result["transaction_id"])
            self.assertIsNotNone(tx)
            self.assertEqual(tx["status"], "success")
            self.assertEqual(tx["skill"], "pdf")
            self.assertEqual(tx["targetAgent"], "trae")
            self.assertTrue(any(step["name"] == "commit" and step["status"] == "success" for step in tx["steps"]))

    def test_failed_sync_saves_failed_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_root = base / "target"
            source_root.mkdir()
            target_root.mkdir()
            skill = Skill(id="pdf", name="pdf", path=str(source_root / "pdf" / "SKILL.md"))
            manager = make_manager(base, source_root, target_root)
            result = manager.sync(skill, "trae", {})
            self.assertEqual(result["status"], "failed")
            tx = manager.get_transaction(result["transaction_id"])
            self.assertIsNotNone(tx)
            self.assertEqual(tx["status"], "failed")

    def test_rollback_status_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_root = base / "target"
            target_root.mkdir()
            source_dir = make_skill(source_root)
            cache = CacheManager(base / "cache")
            skill = Skill(
                id="pdf",
                name="pdf",
                path=str(source_dir / "SKILL.md"),
                hash=cache.compute_skill_hash(source_dir),
            )
            manager = make_manager(base, source_root, target_root)
            installer = manager.installer

            def boom(source, temp_path):
                raise RuntimeError("copy boom")

            installer.copy_skill_md_to_temp = boom  # type: ignore[method-assign]
            result = manager.sync(skill, "trae", {})
            self.assertEqual(result["status"], "failed")
            tx = manager.get_transaction(result["transaction_id"])
            self.assertEqual(tx["status"], "failed")
            self.assertTrue(any(step["name"] == "rollback" and step["status"] == "success" for step in tx["steps"]))


if __name__ == "__main__":
    unittest.main()
