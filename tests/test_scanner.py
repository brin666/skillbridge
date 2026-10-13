"""Tests for Phase 1 Agent Scanner."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.adapters.base import AgentAdapter
from backend.core.agent_scanner import AgentScanner


class FakeAdapter(AgentAdapter):
    """A deterministic adapter used in tests."""

    agent_id = "fake"
    display_name = "Fake Agent"

    def __init__(self, root: Path, installed: bool = True):
        super().__init__()
        self.root = root
        self._installed = installed

    def _candidate_skill_paths(self) -> list[Path]:
        return [self.root]

    def detect(self) -> bool:
        return self._installed or bool(self._existing_skill_paths())


def make_skill_dir(root: Path, name: str) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} description\n---\n",
        encoding="utf-8",
    )
    return skill_dir


class AgentScannerTests(unittest.TestCase):
    def test_scanner_detects_agent_and_scans_skill_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "codex-skills"
            make_skill_dir(root, "pdf")
            make_skill_dir(root, "slides")

            scanner = AgentScanner(adapters=[FakeAdapter(root)])
            agents = scanner.scan(include_skills=True)

            self.assertEqual(len(agents), 1)
            agent = agents[0]
            self.assertTrue(agent.installed)
            self.assertEqual(agent.skill_count, 2)
            self.assertEqual(len(agent.skill_paths), 1)
            self.assertEqual(agent.skill_paths[0], str(root.resolve()))
            self.assertEqual({s.id for s in agent.skills}, {"pdf", "slides"})

    def test_scanner_marks_missing_agent_as_not_installed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "missing"

            scanner = AgentScanner(adapters=[FakeAdapter(root, installed=False)])
            agents = scanner.scan()

            self.assertEqual(len(agents), 1)
            self.assertFalse(agents[0].installed)
            self.assertEqual(agents[0].skill_count, 0)

    def test_scan_environment_counts_unique_skill_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root_a = Path(tmp) / "a"
            root_b = Path(tmp) / "b"
            make_skill_dir(root_a, "pdf")
            make_skill_dir(root_b, "pdf")
            make_skill_dir(root_b, "doc")

            scanner = AgentScanner(
                adapters=[
                    FakeAdapter(root_a),
                    FakeAdapter(root_b),
                ]
            )
            env = scanner.scan_environment()

            self.assertEqual(env.agent_count, 2)
            self.assertEqual(env.skill_count, 2)  # pdf deduplicated across agents
            self.assertEqual(env.to_dict()["agents"][0]["id"], "fake")

    def test_agent_to_dict_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "codex-skills"
            make_skill_dir(root, "pdf")

            scanner = AgentScanner(adapters=[FakeAdapter(root)])
            agent = scanner.scan()[0]
            data = agent.to_dict()

            self.assertEqual(
                set(data),
                {"id", "name", "installed", "version", "skillCount", "skillPaths"},
            )
            self.assertEqual(data["id"], "fake")
            self.assertEqual(data["skillCount"], 1)
            self.assertEqual(data["skillPaths"], [str(root.resolve())])


if __name__ == "__main__":
    unittest.main()
