"""Tests for the Skill data model."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.models.skill import Skill


class SkillModelTests(unittest.TestCase):
    def test_skill_to_dict_contains_unified_fields(self) -> None:
        skill = Skill(
            id="pdf",
            name="pdf",
            display_name="PDF Tools",
            description="Create and edit PDF documents.",
            summary="创建、编辑和处理 PDF 文档。",
            category="Document",
            tags=["PDF", "Document"],
            version="1.0.0",
            source={"type": "github", "url": "https://github.com/example/pdf"},
            path="C:/skills/pdf/SKILL.md",
            installed_agents=["codex", "trae"],
            locations={"codex": True, "trae": True, "qwen": False},
            files=["SKILL.md", "README.md"],
            hash="abc123",
            status="normal",
            duplicate_group="pdf",
        )
        data = skill.to_dict()
        self.assertEqual(data["id"], "pdf")
        self.assertEqual(data["displayName"], "PDF Tools")
        self.assertTrue(data["locations"]["trae"])
        self.assertFalse(data["locations"]["qwen"])
        self.assertEqual(data["source"]["type"], "github")
        self.assertEqual(data["installedAgents"], ["codex", "trae"])
        self.assertEqual(data["installed_agents"], ["codex", "trae"])
        self.assertEqual(data["files"], ["SKILL.md", "README.md"])
        self.assertEqual(data["hash"], "abc123")
        self.assertEqual(data["duplicateGroup"], "pdf")


if __name__ == "__main__":
    unittest.main()
