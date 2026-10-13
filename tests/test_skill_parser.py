"""Tests for SKILL.md parsing."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core.skill_parser import SkillParser


class SkillParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _make_skill(self, name: str, content: str) -> Path:
        skill_dir = self.root / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
        return skill_dir

    def test_parse_frontmatter_and_body(self) -> None:
        skill_dir = self._make_skill(
            "pdf",
            """---
name: pdf
description: Create and edit PDF documents.
tags: [PDF, Document]
---
# PDF Tools

This skill helps you work with PDFs.
""",
        )
        parsed = SkillParser().parse(skill_dir)
        self.assertEqual(parsed["name"], "pdf")
        self.assertEqual(parsed["description"], "Create and edit PDF documents.")
        self.assertEqual(parsed["tags"], ["PDF", "Document"])
        self.assertEqual(parsed["title"], "PDF Tools")
        self.assertIn("work with PDFs", parsed["main_purpose"])

    def test_missing_frontmatter_is_tolerated(self) -> None:
        skill_dir = self._make_skill(
            "plain",
            """# Plain Skill

Some useful description.
""",
        )
        parsed = SkillParser().parse(skill_dir)
        self.assertEqual(parsed["name"], "plain")
        self.assertEqual(parsed["description"], "")
        self.assertEqual(parsed["title"], "Plain Skill")

    def test_empty_description(self) -> None:
        skill_dir = self._make_skill(
            "empty-desc",
            """---
name: empty-desc
description:
---
# Empty Description Skill
""",
        )
        parsed = SkillParser().parse(skill_dir)
        self.assertEqual(parsed["name"], "empty-desc")
        self.assertEqual(parsed["description"], "")

    def test_main_purpose_keeps_complete_sentences_beyond_old_limit(self) -> None:
        first_sentence = "This skill supports a clearly documented capability."
        second_sentence = "It also preserves the complete next sentence instead of cutting its last word."
        long_prefix = " ".join(["Context"] * 25)
        skill_dir = self._make_skill(
            "long-purpose",
            f"# Long Purpose\n\n{long_prefix}. {first_sentence} {second_sentence}\n",
        )

        parsed = SkillParser().parse(skill_dir)

        self.assertIn(first_sentence, parsed["main_purpose"])
        self.assertIn(second_sentence, parsed["main_purpose"])

    def test_main_purpose_skips_author_credit_paragraph(self) -> None:
        skill_dir = self._make_skill(
            "credited",
            "# Credited Skill\n\nAuthor / Author: Example Person\n\n"
            "Create an editorial poster from a supplied photo.\n",
        )

        parsed = SkillParser().parse(skill_dir)

        self.assertEqual(parsed["main_purpose"], "Create an editorial poster from a supplied photo.")


if __name__ == "__main__":
    unittest.main()
