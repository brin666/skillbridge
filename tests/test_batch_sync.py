"""Tests for batch sync."""

from __future__ import annotations

import sys
import tempfile
import time
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
    def __init__(self, agent_id: str, root: Path | None):
        super().__init__()
        self.agent_id = agent_id
        self.display_name = agent_id
        self.root = root

    def _candidate_skill_paths(self):
        return [self.root] if self.root is not None else []

    def supports_skill(self, skill):
        return True

    def capabilities(self):
        return ["filesystem", "shell"]


def make_skill(root: Path, name: str = "pdf") -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: PDF tools\nmetadata:\n  skillbridge-sync: allow\n---\n",
        encoding="utf-8",
    )
    (skill_dir / "metadata.json").write_text(
        '{"repository": "https://github.com/example/pdf"}',
        encoding="utf-8",
    )
    (skill_dir / "scripts").mkdir(exist_ok=True)
    return skill_dir


def wait_for_status(manager: SyncManager, tx_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        tx = manager.get_transaction(tx_id)
        if tx and tx["status"] in ("success", "failed"):
            return tx
        time.sleep(0.02)
    raise AssertionError(f"Transaction {tx_id} did not finish")


class BatchSyncTests(unittest.TestCase):
    def test_batch_sync_multiple_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_a = base / "trae"
            target_b = base / "qwen"
            target_a.mkdir()
            target_b.mkdir()
            source_dir = make_skill(source_root)
            cache = CacheManager(base / "cache")
            adapters = [FakeAdapter("trae", target_a), FakeAdapter("qwen", target_b)]
            checker = PreflightChecker(adapters=adapters, cache_manager=cache)
            manager = SyncManager(
                preflight_checker=checker,
                installer=Installer(tmp_root=base / "tmp"),
                rollback_manager=RollbackManager(state_root=base),
                cache_manager=cache,
            )
            skill = Skill(
                id="pdf",
                name="pdf",
                path=str(source_dir / "SKILL.md"),
                hash=cache.compute_skill_hash(source_dir),
            )
            result = manager.start_batch_sync(skill, ["trae", "qwen"], {})
            self.assertEqual(len(result["tasks"]), 2)
            for task in result["tasks"]:
                tx = wait_for_status(manager, task["transaction_id"])
                self.assertEqual(tx["status"], "success")
            self.assertTrue((target_a / "pdf" / "SKILL.md").is_file())
            self.assertTrue((target_b / "pdf" / "SKILL.md").is_file())

    def test_one_target_failure_does_not_affect_others(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            good_root = base / "trae"
            good_root.mkdir()
            source_dir = make_skill(source_root)
            cache = CacheManager(base / "cache")
            adapters = [FakeAdapter("trae", good_root), FakeAdapter("qwen", None)]
            checker = PreflightChecker(adapters=adapters, cache_manager=cache)
            manager = SyncManager(
                preflight_checker=checker,
                installer=Installer(tmp_root=base / "tmp"),
                rollback_manager=RollbackManager(state_root=base),
                cache_manager=cache,
            )
            skill = Skill(
                id="pdf",
                name="pdf",
                path=str(source_dir / "SKILL.md"),
                hash=cache.compute_skill_hash(source_dir),
            )
            result = manager.start_batch_sync(skill, ["trae", "qwen"], {})
            statuses = {}
            for task in result["tasks"]:
                if task.get("status") == "started":
                    statuses[task["target"]] = wait_for_status(manager, task["transaction_id"])["status"]
                else:
                    statuses[task["target"]] = task.get("status", "failed")
            self.assertEqual(statuses["trae"], "success")
            self.assertEqual(statuses["qwen"], "failed")
            self.assertTrue((good_root / "pdf" / "SKILL.md").is_file())

    def test_conflict_requires_force_replace_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_root = base / "target"
            source_dir = make_skill(source_root)
            target_dir = make_skill(target_root)
            (target_dir / "SKILL.md").write_text(
                "---\nname: pdf\ndescription: target old\n---\n",
                encoding="utf-8",
            )
            cache = CacheManager(base / "cache")
            adapter = FakeAdapter("trae", target_root)
            checker = PreflightChecker(adapters=[adapter], cache_manager=cache)
            manager = SyncManager(
                preflight_checker=checker,
                installer=Installer(tmp_root=base / "tmp"),
                rollback_manager=RollbackManager(state_root=base),
                cache_manager=cache,
            )
            skill = Skill(
                id="pdf",
                name="pdf",
                path=str(source_dir / "SKILL.md"),
                hash=cache.compute_skill_hash(source_dir),
            )

            no_replace = manager.sync(skill, "trae", {"confirm_warning": True})
            self.assertEqual(no_replace["status"], "conflict")
            self.assertTrue((target_root / "pdf" / "SKILL.md").is_file())

            replaced = manager.sync(
                skill,
                "trae",
                {"confirm_warning": True, "force_replace": True},
            )
            self.assertEqual(replaced["status"], "success")
            self.assertIn("PDF tools", (target_root / "pdf" / "SKILL.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
