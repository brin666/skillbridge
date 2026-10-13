"""End-to-end checks for the mutual sync API workflow."""

from __future__ import annotations

import sys
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.adapters.base import AgentAdapter
from backend.api.skills import SkillsAPI
from backend.core.agent_scanner import AgentScanner
from backend.core.cache_manager import CacheManager
from backend.core.installer import Installer
from backend.core.library_manager import LibraryManager
from backend.core.preflight import PreflightChecker
from backend.core.rollback import RollbackManager
from backend.core.skill_scanner import SkillScanner
from backend.core.sync_manager import SyncManager


class FakeAdapter(AgentAdapter):
    def __init__(self, agent_id: str, root: Path | list[Path]) -> None:
        super().__init__()
        self.agent_id = agent_id
        self.display_name = agent_id.title()
        self.roots = root if isinstance(root, list) else [root]

    def _candidate_skill_paths(self):
        return self.roots

    def supports_skill(self, skill):
        return True

    def capabilities(self):
        return ["filesystem", "shell"]


class MutualSyncApiTests(unittest.TestCase):
    def test_plan_deep_searches_and_uses_the_name_declared_in_skill_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "codex-skills"
            target_root = base / "hermes-skills"
            source_root.mkdir()
            target_root.mkdir()
            misplaced = source_root / "downloaded-repository" / "nested" / "folder-slug"
            misplaced.mkdir(parents=True)
            (misplaced / "SKILL.md").write_text(
                "---\nname: actual-skill\ndescription: A portable nested skill.\n---\n",
                encoding="utf-8",
            )
            adapters = [FakeAdapter("codex", source_root), FakeAdapter("hermes", target_root)]
            api = SkillsAPI(
                agent_scanner=AgentScanner(adapters=adapters),
                skill_scanner=SkillScanner(cache_manager=CacheManager(base / "cache")),
                sync_manager=SyncManager(
                    preflight_checker=PreflightChecker(adapters=adapters),
                    installer=Installer(tmp_root=base / "tmp"),
                    rollback_manager=RollbackManager(state_root=base / "state"),
                ),
                library_manager=LibraryManager(library_root=base / "library", trash_root=base / "trash"),
            )

            plan = api.plan_mutual_sync(["codex", "hermes"])

            self.assertEqual(plan["summary"]["ready"], 1)
            item = plan["items"][0]
            self.assertEqual(item["skillId"], "actual-skill")
            self.assertEqual(item["skillDescription"], "A portable nested skill.")
            self.assertEqual(item["compatibilityStatus"], "compatible")
            self.assertFalse((target_root / "actual-skill").exists())

    def test_startup_warmup_prechecks_compatibility_without_writing_skills(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "codex-skills"
            target_root = base / "hermes-skills"
            source_root.mkdir()
            target_root.mkdir()
            source_dir = source_root / "demo-skill"
            source_dir.mkdir()
            source_md = source_dir / "SKILL.md"
            source_md.write_text(
                "---\nname: demo-skill\ndescription: A portable demo skill\nmetadata:\n  skillbridge-sync: allow\n---\n",
                encoding="utf-8",
            )

            adapters = [FakeAdapter("codex", source_root), FakeAdapter("hermes", target_root)]
            cache = CacheManager(base / "cache")
            api = SkillsAPI(
                agent_scanner=AgentScanner(adapters=adapters),
                skill_scanner=SkillScanner(cache_manager=cache),
                sync_manager=SyncManager(
                    preflight_checker=PreflightChecker(adapters=adapters, cache_manager=cache),
                    installer=Installer(tmp_root=base / "tmp"),
                    rollback_manager=RollbackManager(state_root=base / "state"),
                    cache_manager=cache,
                ),
                library_manager=LibraryManager(library_root=base / "library", trash_root=base / "trash"),
            )

            api.start_compatibility_warmup()
            status = api.get_compatibility_warmup_status()
            for _ in range(100):
                if status["status"] != "warming":
                    break
                time.sleep(0.01)
                status = api.get_compatibility_warmup_status()

            self.assertEqual(status["status"], "ready")
            self.assertGreater(status["checkedPairs"], 0)
            checker_cache = api.preflight_checker.compatibility_checker._cache
            warmed_cache_size = len(checker_cache)
            self.assertGreater(warmed_cache_size, 0)

            with patch.object(
                api,
                "_build_mutual_sync_plan",
                side_effect=AssertionError("default selection should reuse the startup plan"),
            ):
                plan = api.plan_mutual_sync(["codex", "hermes"])
            self.assertEqual(plan["summary"]["ready"], 1)
            self.assertEqual(len(checker_cache), warmed_cache_size)
            self.assertFalse((target_root / "demo-skill").exists())

    def test_plan_stales_when_new_conflict_appears_after_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "codex-skills"
            target_root = base / "hermes-skills"
            source_root.mkdir()
            target_root.mkdir()
            source_dir = source_root / "demo-skill"
            source_dir.mkdir()
            (source_dir / "SKILL.md").write_text(
                "---\nname: demo-skill\ndescription: A portable demo skill\nmetadata:\n  skillbridge-sync: allow\n---\nUse only the provided instructions.\n",
                encoding="utf-8",
            )
            (source_dir / "metadata.json").write_text(
                '{"repository":"https://github.com/example/demo-skill"}',
                encoding="utf-8",
            )

            adapters = [FakeAdapter("codex", source_root), FakeAdapter("hermes", target_root)]
            cache = CacheManager(base / "cache")
            preflight = PreflightChecker(adapters=adapters, cache_manager=cache)
            sync_manager = SyncManager(
                preflight_checker=preflight,
                installer=Installer(tmp_root=base / "tmp"),
                rollback_manager=RollbackManager(state_root=base / "state"),
                cache_manager=cache,
            )
            api = SkillsAPI(
                agent_scanner=AgentScanner(adapters=adapters),
                skill_scanner=SkillScanner(cache_manager=cache),
                sync_manager=sync_manager,
                library_manager=LibraryManager(library_root=base / "library", trash_root=base / "trash"),
            )

            plan = api.plan_mutual_sync(["codex", "hermes"])
            self.assertEqual(plan["summary"]["ready"], 1)
            self.assertEqual(plan["items"][0]["targetAgent"], "hermes")

            source_conflict = source_root / "conflict-skill"
            target_conflict = target_root / "conflict-skill"
            for skill_dir, description in (
                (source_conflict, "Source conflict version"),
                (target_conflict, "Target conflict version"),
            ):
                skill_dir.mkdir()
                (skill_dir / "SKILL.md").write_text(
                    f"---\nname: conflict-skill\ndescription: {description}\n---\n",
                    encoding="utf-8",
                )
            stale = api.start_mutual_sync(["codex", "hermes"], plan["planId"])
            self.assertEqual(stale["code"], "PLAN_STALE")
            self.assertFalse((target_root / "demo-skill").exists())

            shutil.rmtree(source_conflict)
            shutil.rmtree(target_conflict)
            plan = api.plan_mutual_sync(["codex", "hermes"])
            result = api.start_mutual_sync(["codex", "hermes"], plan["planId"])
            self.assertEqual(len(result["tasks"]), 1)
            transaction_id = result["tasks"][0]["transaction_id"]
            self.assertTrue(transaction_id)
            for _ in range(100):
                transaction = api.get_sync_transaction(transaction_id)
                if transaction and transaction["status"] in {"success", "failed"}:
                    break
                time.sleep(0.02)
            self.assertEqual(transaction["status"], "success")
            self.assertTrue((target_root / "demo-skill" / "SKILL.md").is_file())
            self.assertFalse((target_root / "demo-skill" / "scripts").exists())

    def test_different_versions_in_two_roots_of_one_harness_are_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root_a = base / "codex-primary"
            root_b = base / "codex-extra"
            target_root = base / "hermes"
            for root in (root_a, root_b, target_root):
                root.mkdir()
            for root, description in ((root_a, "Version A"), (root_b, "Version B")):
                skill_dir = root / "demo-skill"
                skill_dir.mkdir()
                (skill_dir / "SKILL.md").write_text(
                    f"---\nname: demo-skill\ndescription: {description}\n---\n",
                    encoding="utf-8",
                )

            adapters = [FakeAdapter("codex", [root_a, root_b]), FakeAdapter("hermes", target_root)]
            cache = CacheManager(base / "cache")
            api = SkillsAPI(
                agent_scanner=AgentScanner(adapters=adapters),
                skill_scanner=SkillScanner(cache_manager=cache),
                sync_manager=SyncManager(
                    preflight_checker=PreflightChecker(adapters=adapters, cache_manager=cache),
                    installer=Installer(tmp_root=base / "tmp"),
                    rollback_manager=RollbackManager(state_root=base / "state"),
                    cache_manager=cache,
                ),
                library_manager=LibraryManager(library_root=base / "library", trash_root=base / "trash"),
            )

            plan = api.plan_mutual_sync(["codex", "hermes"])

            self.assertEqual(plan["summary"]["conflicts"], 1)
            self.assertEqual(plan["summary"]["ready"], 0)

    def test_requires_two_detected_installed_harnesses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "one"
            root.mkdir()
            api = SkillsAPI(agent_scanner=AgentScanner(adapters=[FakeAdapter("codex", root)]))
            with self.assertRaises(ValueError):
                api.plan_mutual_sync(["codex"])


if __name__ == "__main__":
    unittest.main()
