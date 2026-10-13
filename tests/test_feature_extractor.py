"""Tests for complete, source-backed Skill capability extraction."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core.summary.feature_extractor import FeatureExtractor
from backend.core.summary.manager import SummaryManager


class FeatureExtractorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.extractor = FeatureExtractor()

    def test_collects_all_items_from_explicit_capability_section(self) -> None:
        parsed = {
            "description": "",
            "main_purpose": "",
            "body": """## Capabilities
This Skill can create reports for a project.

- Create project reports.
- Export reports as PDF.

### Limitations
- This skill cannot export spreadsheets.

## Requirements
- Install the reporting CLI.
""",
        }

        features = self.extractor.extract(parsed)

        self.assertIn("This Skill can create reports for a project", features)
        self.assertIn("Create project reports", features)
        self.assertIn("Export reports as PDF", features)
        self.assertFalse(any("cannot" in feature or "Install" in feature for feature in features))

    def test_lists_functions_from_when_to_use_and_skips_negative_scenarios(self) -> None:
        parsed = {
            "description": "",
            "main_purpose": "",
            "body": """## When to use
- Generate a new image.
- Edit an existing image.

## When not to use
- Edit an existing SVG icon.
""",
        }

        self.assertEqual(
            self.extractor.extract(parsed),
            ["Generate a new image", "Edit an existing image"],
        )

    def test_skips_a_mixed_heading_that_includes_non_use_cases(self) -> None:
        parsed = {
            "description": "",
            "main_purpose": "Create and edit images.",
            "body": """## When to use / When not to use
- Generate a new image.
- Do not use for SVG editing.
""",
        }

        self.assertEqual(self.extractor.extract(parsed), ["Create and edit images"])

    def test_does_not_mistake_workflow_instructions_for_features(self) -> None:
        parsed = {
            "description": "",
            "main_purpose": "Generate a concise overview.",
            "body": "## Workflow\n- Check the input.\n- Choose a mode.\n- Return the result.\n",
        }

        self.assertEqual(self.extractor.extract(parsed), ["Generate a concise overview"])

    def test_removes_negative_clause_from_a_mixed_description(self) -> None:
        parsed = {
            "description": "Use this skill for browser testing; do not use for unrelated design work.",
            "main_purpose": "",
            "body": "",
        }

        self.assertEqual(self.extractor.extract(parsed), ["Use this skill for browser testing"])

    def test_prefers_user_facing_description_over_agent_only_intro(self) -> None:
        parsed = {
            "description": (
                "Use when a task may benefit from a bounded subagent for implementation, large-codebase discovery "
                "at task start, independent review, requested or pre-commit code simplification, or expert work "
                "on complex decisions, modeling, automation, or repeated failures. Do not use for simple questions."
            ),
            "main_purpose": (
                "The main agent decomposes the user's task, decides what to delegate, and accepts the result. "
                "On activation, send one brief commentary update in the user's language."
            ),
            "body": "",
        }

        result = SummaryManager().analyze(parsed)

        self.assertEqual(
            result["summaries"]["zh-CN"],
            "主 Agent 拆解任务、判断委派内容并整合子 Agent 的结果",
        )
        self.assertIn(
            "适用于需要子 Agent 参与实现、大型代码库探索、独立审查、代码简化或复杂问题分析的任务",
            result["features"]["zh-CN"],
        )
        self.assertIn("主 Agent 拆解任务、判断委派内容并整合子 Agent 的结果", result["features"]["zh-CN"])
        self.assertFalse(any("activation" in item or "规模本身不需要" in item for item in result["features"]["zh-CN"]))

    def test_skips_usage_preamble_and_keyword_inventory(self) -> None:
        parsed = {
            "description": "",
            "main_purpose": "",
            "body": """## When to use
Use when the user asks to:
- Generate a product requirements document.
- Import an existing PRD.
- Keywords: PRD, product documentation.
""",
        }

        self.assertEqual(
            self.extractor.extract(parsed),
            ["Generate a product requirements document", "Import an existing PRD"],
        )

    def test_joins_wrapped_list_items_and_skips_usage_preamble(self) -> None:
        parsed = {
            "description": "",
            "main_purpose": "",
            "body": """## When to Use
Use this whenever you want to

- Create a theme that matches a custom brand palette and applies it consistently
  to the CLI, TUI, and desktop app.
- Update the active skin and preview the change live.
""",
        }

        self.assertEqual(
            self.extractor.extract(parsed),
            [
                "Create a theme that matches a custom brand palette and applies it consistently to the CLI, TUI, and desktop app",
                "Update the active skin and preview the change live",
            ],
        )

    def test_keeps_positive_capability_but_drops_contrastive_restriction(self) -> None:
        parsed = {
            "description": "",
            "main_purpose": (
                "Drawixx may render that tree on an editable canvas, but canvas coordinates "
                "and other whiteboard state are never authoring data."
            ),
            "body": "",
        }

        self.assertEqual(
            self.extractor.extract(parsed),
            ["Drawixx may render that tree on an editable canvas"],
        )

    def test_returns_no_features_when_no_capability_is_documented(self) -> None:
        self.assertEqual(
            self.extractor.extract({"description": "", "main_purpose": "", "body": "## Notes\nNo details here."}),
            [],
        )

    def test_does_not_treat_author_credit_as_a_feature(self) -> None:
        self.assertEqual(
            self.extractor.extract(
                {
                    "description": "Author / Author: Example Person",
                    "main_purpose": "Author / Author: Example Person",
                    "body": "# Skill Title\n",
                }
            ),
            [],
        )

    def test_uses_capabilities_from_explicitly_linked_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "skill"
            references = skill_dir / "references"
            references.mkdir(parents=True)
            (references / "guide.md").write_text(
                "## Features\n- Generate a storyboard.\n- Export an image sequence.\n",
                encoding="utf-8",
            )
            (Path(tmp) / "outside.md").write_text(
                "## Features\n- Read data outside the Skill folder.\n",
                encoding="utf-8",
            )

            documents = SummaryManager._read_referenced_markdown(
                skill_dir,
                "See [the guide](references/guide.md) and ../outside.md.",
            )
            features = self.extractor.extract(
                {"description": "", "main_purpose": "", "body": ""}, documents
            )

            self.assertEqual(features, ["Generate a storyboard", "Export an image sequence"])


if __name__ == "__main__":
    unittest.main()
