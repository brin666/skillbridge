"""Tests for Skill Scanner."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core.skill_scanner import SkillScanner
from backend.models.agent import Agent


def make_skill(root: Path, name: str, description: str = "Test description.") -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n",
        encoding="utf-8",
    )
    return skill_dir


class SkillScannerTests(unittest.TestCase):
    def test_scans_skill_dirs_and_ignores_invalid_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_skill(root, "pdf", "Create and edit PDF documents.")
            make_skill(root, "doc", "Document tools.")
            invalid = root / "not-a-skill"
            invalid.mkdir()

            scanner = SkillScanner()
            skills = scanner.scan_skill_paths([root], agent_id="codex")

            self.assertEqual(len(skills), 2)
            ids = {s.id for s in skills}
            self.assertEqual(ids, {"pdf", "doc"})
            for skill in skills:
                self.assertEqual(skill.installed_agents, ["codex"])
                self.assertTrue(skill.hash)
                self.assertIn("SKILL.md", skill.files)
                self.assertTrue(skill.path.endswith("SKILL.md"))

    def test_recursively_finds_nested_skill_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "category" / "collection" / "nested-skill"
            nested.mkdir(parents=True)
            (nested / "SKILL.md").write_text(
                "---\nname: nested-skill\ndescription: Nested skill.\n---\n",
                encoding="utf-8",
            )
            generated = root / "node_modules" / "example" / "SKILL.md"
            generated.parent.mkdir(parents=True)
            generated.write_text(
                "---\nname: generated-skill\ndescription: Not a user skill.\n---\n",
                encoding="utf-8",
            )

            skills = SkillScanner().scan_skill_paths([root], agent_id="codex")

            self.assertEqual([skill.id for skill in skills], ["nested-skill"])
            self.assertEqual(Path(skills[0].path), nested / "SKILL.md")

    def test_finds_root_and_case_insensitive_skill_markdown_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root_skill = base / "root-skill"
            root_skill.mkdir()
            (root_skill / "SKILL.md").write_text(
                "---\nname: root-skill\ndescription: Root skill.\n---\n",
                encoding="utf-8",
            )
            collection = base / "collection"
            lower_skill = collection / "nested" / "lower-skill"
            lower_skill.mkdir(parents=True)
            (lower_skill / "skill.md").write_text(
                "---\nname: lower-skill\ndescription: Lowercase filename.\n---\n",
                encoding="utf-8",
            )

            skills = SkillScanner().scan_skill_paths([root_skill, collection], agent_id="codex")

            self.assertEqual({skill.id for skill in skills}, {"root-skill", "lower-skill"})
            lower = next(skill for skill in skills if skill.id == "lower-skill")
            self.assertEqual(Path(lower.path), lower_skill / "skill.md")

    def test_skill_document_marks_bundle_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = make_skill(root, "parent-skill")
            nested_example = parent / "references" / "example"
            nested_example.mkdir(parents=True)
            (nested_example / "SKILL.md").write_text(
                "---\nname: example-skill\ndescription: Embedded example.\n---\n",
                encoding="utf-8",
            )

            skills = SkillScanner().scan_skill_paths([root], agent_id="codex")

            self.assertEqual([skill.id for skill in skills], ["parent-skill"])

    def test_nested_disabled_skill_is_hidden_from_active_scan_and_kept_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skills"
            disabled = root / "group_disabled" / "demo"
            disabled.mkdir(parents=True)
            (disabled / "SKILL.md").write_text(
                "---\nname: demo\ndescription: Disabled nested skill.\n---\n",
                encoding="utf-8",
            )

            scanner = SkillScanner()
            active = scanner.scan_skill_paths([root], agent_id="codex")
            with_disabled = scanner.scan_skill_paths([root], agent_id="codex", include_disabled=True)

            self.assertEqual(active, [])
            self.assertEqual(len(with_disabled), 1)
            self.assertFalse(with_disabled[0].enabled)
            self.assertEqual(with_disabled[0].status, "disabled")

    def test_collects_scripts_and_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = make_skill(root, "browser", "Browser helper.")
            (skill_dir / "scripts").mkdir()
            (skill_dir / "scripts" / "run.py").write_text("print('hi')\n", encoding="utf-8")
            (skill_dir / "references").mkdir()
            (skill_dir / "references" / "notes.md").write_text("note", encoding="utf-8")

            scanner = SkillScanner()
            skills = scanner.scan_skill_paths([root], agent_id="trae")
            self.assertEqual(len(skills), 1)
            files = skills[0].files
            self.assertIn("scripts/run.py", files)
            self.assertIn("references/notes.md", files)

    def test_merge_skills_from_multiple_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root_a = Path(tmp) / "a"
            root_b = Path(tmp) / "b"
            make_skill(root_a, "pdf", "PDF tools")
            make_skill(root_b, "pdf", "PDF tools")
            make_skill(root_b, "doc", "Document tools")

            scanner = SkillScanner()
            skills = scanner.scan_agents(
                [
                    Agent(id="codex", name="Codex", installed=True, skill_paths=[str(root_a)]),
                    Agent(id="trae", name="TRAE", installed=True, skill_paths=[str(root_b)]),
                ]
            )
            by_id = {s.id: s for s in skills}
            self.assertEqual(set(by_id), {"pdf", "doc"})
            self.assertEqual(by_id["pdf"].installed_agents, ["codex", "trae"])
            self.assertEqual(by_id["pdf"].locations, {"codex": True, "trae": True})
            self.assertEqual(by_id["pdf"].duplicate_group, "pdf")


if __name__ == "__main__":
    unittest.main()
