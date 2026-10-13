"""Tests for rule-based summary generation."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core.summary_manager import SummaryManager


class SummaryManagerTests(unittest.TestCase):
    def test_description_generates_chinese_style_summary(self) -> None:
        summary = SummaryManager().generate(
            {"description": "Create and edit PDF documents."}
        )
        self.assertIn("PDF", summary)
        self.assertIn("创建", summary)

    def test_chinese_description_is_kept(self) -> None:
        summary = SummaryManager().generate(
            {"description": "用于测试中文概述。"}
        )
        self.assertEqual(summary, "用于测试中文概述。")

    def test_readme_fallback_when_description_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "README.md").write_text(
                "# PDF Tools\n\nThis skill edits PDF files.\n",
                encoding="utf-8",
            )
            summary = SummaryManager().generate({"description": ""}, skill_dir)
            self.assertTrue(summary)
            self.assertIn("PDF", summary)

    def test_missing_description_does_not_invent_a_summary_from_tags(self) -> None:
        summary = SummaryManager().generate(
            {"description": "", "tags": ["PDF", "Document"], "title": "", "body": ""}
        )
        self.assertEqual(summary, "未知")


if __name__ == "__main__":
    unittest.main()
