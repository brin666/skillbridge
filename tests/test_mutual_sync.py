"""Tests for cross-Harness mutual sync planning."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.adapters.base import AgentAdapter
from backend.core.mutual_sync import MutualSyncPlanner
from backend.core.preflight import PreflightChecker
from backend.models.skill import Skill


class FakeAdapter(AgentAdapter):
    def __init__(self, agent_id: str, root: Path) -> None:
        super().__init__()
        self.agent_id = agent_id
        self.display_name = agent_id.title()
        self.root = root

    def _candidate_skill_paths(self):
        return [self.root]

    def supports_skill(self, skill):
        return True

    def capabilities(self):
        return ["filesystem", "shell"]


def write_skill(root: Path, description: str = "Portable skill", body: str = "") -> Skill:
    folder = root / "demo-skill"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "SKILL.md"
    path.write_text(
        f"---\nname: demo-skill\ndescription: {description}\nmetadata:\n  skillbridge-sync: allow\n---\n{body}",
        encoding="utf-8",
    )
    return Skill(
        id="demo-skill",
        name="demo-skill",
        display_name="Demo Skill",
        source={"type": "local"},
        path=str(path),
        installed_agents=[root.name],
    )


class MutualSyncPlannerTests(unittest.TestCase):
    def test_missing_skill_is_ready_for_mutual_sync(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "codex"
            target_root = base / "hermes"
            source_root.mkdir()
            target_root.mkdir()
            skill = write_skill(source_root)
            adapters = [FakeAdapter("codex", source_root), FakeAdapter("hermes", target_root)]
            planner = MutualSyncPlanner(adapters, PreflightChecker(adapters=adapters))
            plan = planner.build(["codex", "hermes"], {"codex": [skill], "hermes": []})
            self.assertEqual(plan.to_dict()["summary"]["ready"], 1)
            self.assertEqual(plan.ready_entries[0].target_agent, "hermes")

    def test_divergent_skill_versions_are_conflicts_not_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "codex"
            target_root = base / "hermes"
            source_root.mkdir()
            target_root.mkdir()
            first = write_skill(source_root, "Version one")
            second = write_skill(target_root, "Version two")
            adapters = [FakeAdapter("codex", source_root), FakeAdapter("hermes", target_root)]
            planner = MutualSyncPlanner(adapters, PreflightChecker(adapters=adapters))
            plan = planner.build(["codex", "hermes"], {"codex": [first], "hermes": [second]})
            self.assertEqual(plan.to_dict()["summary"]["conflicts"], 1)
            self.assertEqual(plan.ready_entries, [])

    def test_same_skill_in_all_selected_agents_is_marked_aligned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "codex"
            target_root = base / "hermes"
            source_root.mkdir()
            target_root.mkdir()
            first = write_skill(source_root)
            second = write_skill(target_root)
            adapters = [FakeAdapter("codex", source_root), FakeAdapter("hermes", target_root)]
            planner = MutualSyncPlanner(adapters, PreflightChecker(adapters=adapters))
            plan = planner.build(["codex", "hermes"], {"codex": [first], "hermes": [second]})
            self.assertEqual(plan.to_dict()["summary"]["alreadySynced"], 1)

    def test_referenced_support_files_are_review_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "codex"
            target_root = base / "hermes"
            source_root.mkdir()
            target_root.mkdir()
            skill = write_skill(source_root, body="Run scripts/convert.py.")
            adapters = [FakeAdapter("codex", source_root), FakeAdapter("hermes", target_root)]
            planner = MutualSyncPlanner(adapters, PreflightChecker(adapters=adapters))
            plan = planner.build(["codex", "hermes"], {"codex": [skill], "hermes": []})
            self.assertEqual(plan.to_dict()["summary"]["review"], 1)
            self.assertEqual(plan.ready_entries, [])
            self.assertEqual(plan.to_dict()["summary"]["compatibility"]["compatible"], 1)
            self.assertEqual(plan.to_dict()["items"][0]["compatibilityStatus"], "compatible")


if __name__ == "__main__":
    unittest.main()
