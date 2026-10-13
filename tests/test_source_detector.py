"""Tests for Skill source detection."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core.source_detector import SourceDetector


class SourceDetectorTests(unittest.TestCase):
    def test_detects_github_from_metadata_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "metadata.json").write_text(
                '{"repository": "https://github.com/example/pdf-skill"}',
                encoding="utf-8",
            )
            source = SourceDetector().detect(skill_dir)
            self.assertEqual(source["type"], "github")
            self.assertEqual(source["url"], "https://github.com/example/pdf-skill")

    def test_detects_github_from_readme(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "README.md").write_text(
                "See https://github.com/example/pdf-skill for details.",
                encoding="utf-8",
            )
            source = SourceDetector().detect(skill_dir)
            self.assertEqual(source["type"], "github")
            self.assertEqual(source["url"], "https://github.com/example/pdf-skill")

    def test_detects_github_from_git_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "pdf"
            (skill_dir / ".git").mkdir(parents=True)
            (skill_dir / ".git" / "config").write_text(
                '[remote "origin"]\n\turl = git@github.com:example/pdf-skill.git\n',
                encoding="utf-8",
            )
            source = SourceDetector().detect(skill_dir)
            self.assertEqual(source["type"], "github")
            self.assertEqual(source["url"], "https://github.com/example/pdf-skill")

    def test_ignores_unrelated_parent_repository_remote(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "project"
            skill_dir = repo / "skills" / "my-local-skill"
            (repo / ".git").mkdir(parents=True)
            skill_dir.mkdir(parents=True)
            (repo / ".git" / "config").write_text(
                '[remote "origin"]\n\turl = https://github.com/example/unrelated-project.git\n',
                encoding="utf-8",
            )

            source = SourceDetector().detect(skill_dir)

            self.assertEqual(source["type"], "unknown")

    def test_unknown_when_no_source_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = SourceDetector().detect(Path(tmp))
            self.assertEqual(source["type"], "unknown")


if __name__ == "__main__":
    unittest.main()
