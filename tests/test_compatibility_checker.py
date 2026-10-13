"""Tests for the fast static SKILL.md compatibility checker."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.adapters.base import AgentAdapter
from backend.core.compatibility_checker import CompatibilityChecker
from backend.models.preflight import PreflightResult
from backend.models.skill import Skill


class FakeAdapter(AgentAdapter):
    agent_id = "codex"
    display_name = "Codex"

    def supports_skill(self, skill):
        return True


class CompatibilityCheckerTests(unittest.TestCase):
    def make_skill(self, root: Path, body: str = "") -> Skill:
        skill_dir = root / "portable-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: portable-skill\ndescription: A portable test skill\n---\n{body}",
            encoding="utf-8",
        )
        return Skill(id="portable-skill", name="portable-skill", path=str(skill_dir / "SKILL.md"))

    def test_minimal_skill_is_portable_and_does_not_need_extra_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(Path(tmp))
            checks = CompatibilityChecker().check(skill, FakeAdapter())
            self.assertTrue(checks)
            self.assertTrue(all(check.status == "pass" for check in checks))

    def test_missing_description_blocks_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(Path(tmp))
            Path(skill.path).write_text("---\nname: portable-skill\n---\n", encoding="utf-8")
            checks = CompatibilityChecker().check(skill, FakeAdapter())
            format_check = next(check for check in checks if check.name == "skill-format")
            self.assertEqual(format_check.status, "block")
            self.assertIn("description", format_check.message)

    def test_nonexclusive_harness_mention_does_not_make_other_harness_incompatible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(Path(tmp))
            Path(skill.path).write_text(
                "---\nname: portable-skill\ndescription: Test\ncompatibility: Designed for Claude Code\nallowed-tools: Bash\n---\n",
                encoding="utf-8",
            )
            checks = CompatibilityChecker().check(skill, FakeAdapter())
            statuses = {check.name: check.status for check in checks}
            self.assertEqual(statuses["compatibility-notes"], "pass")
            self.assertEqual(statuses["allowed-tools"], "warn")
            notes = next(check for check in checks if check.name == "compatibility-notes")
            self.assertIn("does not state that other Harnesses are incompatible", notes.message)

    def test_folder_name_mismatch_uses_declared_skill_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            misplaced = root / "downloaded-repository-name"
            misplaced.mkdir()
            path = misplaced / "SKILL.md"
            path.write_text(
                "---\nname: actual-skill-name\ndescription: A valid skill document.\n---\n",
                encoding="utf-8",
            )
            skill = Skill(id="actual-skill-name", name="actual-skill-name", path=str(path))

            checks = CompatibilityChecker().check(skill, FakeAdapter())

            format_check = next(check for check in checks if check.name == "skill-format")
            location_check = next(check for check in checks if check.name == "skill-location")
            self.assertEqual(format_check.status, "pass")
            self.assertEqual(location_check.status, "pass")
            self.assertIn("using the SKILL.md name", location_check.message)

    def test_explicit_harness_exclusion_in_skill_body_is_called_incompatible(self) -> None:
        class ClaudeAdapter(FakeAdapter):
            agent_id = "claude"
            display_name = "Claude Code"

        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(Path(tmp), "This skill works only with Codex.")

            checks = CompatibilityChecker().check(skill, ClaudeAdapter())

            result = next(check for check in checks if check.name == "skill-content-compatibility")
            self.assertEqual(result.status, "block")
            self.assertIn("only with Codex", result.details["evidence"])

    def test_environment_conditional_harness_limits_need_review_not_incompatible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(Path(tmp), "Codex won't run outside a git directory.")

            result = next(
                check
                for check in CompatibilityChecker().check(skill, FakeAdapter())
                if check.name == "skill-content-compatibility"
            )

            self.assertEqual(result.status, "warn")

    def test_common_for_only_and_use_only_phrases_are_exclusive(self) -> None:
        class ClaudeAdapter(FakeAdapter):
            agent_id = "claude"
            display_name = "Claude Code"

        for body in ("This Skill is for Codex only.", "Use this Skill only in Codex."):
            with self.subTest(body=body), tempfile.TemporaryDirectory() as tmp:
                skill = self.make_skill(Path(tmp), body)
                checks = CompatibilityChecker().check(skill, ClaudeAdapter())
                result = next(check for check in checks if check.name == "skill-content-compatibility")
                self.assertEqual(result.status, "block")

    def test_only_scoped_to_commands_or_examples_is_not_harness_exclusivity(self) -> None:
        cases = (
            ("Use only local inspection commands such as Hermes version/profile/config.", "codex"),
            ("Write only the instructions needed for another Codex instance to perform the task.", "claude"),
        )
        for body, target_id in cases:
            with self.subTest(body=body), tempfile.TemporaryDirectory() as tmp:
                skill = self.make_skill(Path(tmp), body)
                target = FakeAdapter() if target_id == "codex" else type(
                    "ClaudeAdapter", (FakeAdapter,), {"agent_id": "claude", "display_name": "Claude Code"}
                )()
                result = next(
                    check
                    for check in CompatibilityChecker().check(skill, target)
                    if check.name == "skill-content-compatibility"
                )
                self.assertEqual(result.status, "pass")

    def test_unrelated_negation_does_not_taint_harness_mentions(self) -> None:
        class ClaudeAdapter(FakeAdapter):
            agent_id = "claude"
            display_name = "Claude Code"

        bodies = (
            "Claude may use python instead of python3; without a python symlink, its bash command self-corrects.",
            "You are running in CLI/API mode, not the Claude Design hosted web UI.",
        )
        for body in bodies:
            with self.subTest(body=body), tempfile.TemporaryDirectory() as tmp:
                skill = self.make_skill(Path(tmp), body)
                result = next(
                    check
                    for check in CompatibilityChecker().check(skill, ClaudeAdapter())
                    if check.name == "skill-content-compatibility"
                )
                self.assertEqual(result.status, "pass")

    def test_cannot_run_without_target_harness_is_not_misread_as_its_exclusion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(Path(tmp), "This Skill cannot run without Codex.")
            result = next(
                check
                for check in CompatibilityChecker().check(skill, FakeAdapter())
                if check.name == "skill-content-compatibility"
            )
            self.assertEqual(result.status, "pass")

    def test_nonexclusive_harness_mention_in_skill_body_is_not_a_failure(self) -> None:
        class ClaudeAdapter(FakeAdapter):
            agent_id = "claude"
            display_name = "Claude Code"

        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(Path(tmp), "Originally designed for Codex, this uses portable Markdown instructions.")

            checks = CompatibilityChecker().check(skill, ClaudeAdapter())

            result = next(check for check in checks if check.name == "skill-content-compatibility")
            self.assertEqual(result.status, "pass")

    def test_double_negative_marks_required_harness_as_supported(self) -> None:
        class ClaudeAdapter(FakeAdapter):
            agent_id = "claude"
            display_name = "Claude Code"

        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(Path(tmp), "This skill cannot run without Codex.")
            checker = CompatibilityChecker()

            codex = next(check for check in checker.check(skill, FakeAdapter()) if check.name == "skill-content-compatibility")
            claude = next(check for check in checker.check(skill, ClaudeAdapter()) if check.name == "skill-content-compatibility")

            self.assertEqual(codex.status, "pass")
            self.assertEqual(claude.status, "block")

    def test_compatibility_note_matching_target_passes(self) -> None:
        class ClaudeAdapter(FakeAdapter):
            agent_id = "claude"
            display_name = "Claude Code"

        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(Path(tmp))
            Path(skill.path).write_text(
                "---\nname: portable-skill\ndescription: Test\ncompatibility: Designed for Claude Code\n---\n",
                encoding="utf-8",
            )
            checks = CompatibilityChecker().check(skill, ClaudeAdapter())
            note = next(check for check in checks if check.name == "compatibility-notes")
            self.assertEqual(note.status, "pass")
            self.assertIn("explicitly includes Claude Code", note.message)

    def test_negated_target_compatibility_is_never_reported_as_pass(self) -> None:
        class ClaudeAdapter(FakeAdapter):
            agent_id = "claude"
            display_name = "Claude Code"

        for compatibility, expected_status in (
            ("Not compatible with Codex", "block"),
            ("No Codex support", "block"),
            ("Avoid Codex", "warn"),
            ("Codex isn't supported", "block"),
            ("Codex never works", "block"),
            ("Codex is never supported", "block"),
            ("Excludes Codex", "block"),
            ("Without Codex", "warn"),
            ("No support for Codex is available", "block"),
        ):
            with self.subTest(compatibility=compatibility), tempfile.TemporaryDirectory() as tmp:
                skill = self.make_skill(Path(tmp))
                Path(skill.path).write_text(
                    f"---\nname: portable-skill\ndescription: Test\ncompatibility: {compatibility}\n---\n",
                    encoding="utf-8",
                )
                checks = CompatibilityChecker().check(skill, FakeAdapter())
                note = next(check for check in checks if check.name == "compatibility-notes")
                self.assertEqual(note.status, expected_status)
                self.assertIn("Codex", note.message)

    def test_negation_is_limited_to_the_named_harness_clause(self) -> None:
        class ClaudeAdapter(FakeAdapter):
            agent_id = "claude"
            display_name = "Claude Code"

        for compatibility in (
            "Supported by Codex, not Claude Code",
            "Codex works and not Claude Code",
            "Codex is supported, Claude Code is not",
        ):
            with self.subTest(compatibility=compatibility), tempfile.TemporaryDirectory() as tmp:
                skill = self.make_skill(Path(tmp))
                Path(skill.path).write_text(
                    f"---\nname: portable-skill\ndescription: Test\ncompatibility: {compatibility}\n---\n",
                    encoding="utf-8",
                )
                checker = CompatibilityChecker()
                codex_note = next(check for check in checker.check(skill, FakeAdapter()) if check.name == "compatibility-notes")
                claude_note = next(check for check in checker.check(skill, ClaudeAdapter()) if check.name == "compatibility-notes")
                self.assertEqual(codex_note.status, "pass")
                self.assertEqual(claude_note.status, "block")

    def test_shared_negation_applies_to_every_harness_in_a_list(self) -> None:
        class ClaudeAdapter(FakeAdapter):
            agent_id = "claude"
            display_name = "Claude Code"

        class QwenAdapter(FakeAdapter):
            agent_id = "qwen"
            display_name = "Qwen Code"

        for compatibility in (
            "Codex, Claude Code are unsupported",
            "Codex, Claude Code, and Qwen are unsupported",
            "Codex and Claude Code are never supported",
            "Codex and Claude Code cannot run",
            "Codex and Claude Code do not work",
            "Neither Codex nor Claude Code are supported",
            "No support for Codex, Claude Code",
            "No support for Codex or Claude Code is available",
        ):
            with self.subTest(compatibility=compatibility), tempfile.TemporaryDirectory() as tmp:
                skill = self.make_skill(Path(tmp))
                Path(skill.path).write_text(
                    f"---\nname: portable-skill\ndescription: Test\ncompatibility: {compatibility}\n---\n",
                    encoding="utf-8",
                )
                checker = CompatibilityChecker()
                codex_note = next(check for check in checker.check(skill, FakeAdapter()) if check.name == "compatibility-notes")
                claude_note = next(check for check in checker.check(skill, ClaudeAdapter()) if check.name == "compatibility-notes")
                self.assertEqual(codex_note.status, "block")
                self.assertEqual(claude_note.status, "block")
                if "Qwen" in compatibility:
                    qwen_note = next(check for check in checker.check(skill, QwenAdapter()) if check.name == "compatibility-notes")
                    self.assertEqual(qwen_note.status, "block")

    def test_target_specific_positive_predicate_is_not_tainted_by_prior_exclusion(self) -> None:
        class ClaudeAdapter(FakeAdapter):
            agent_id = "claude"
            display_name = "Claude Code"

        for compatibility in (
            "Without Codex, Claude Code is supported",
            "No support for Codex, Claude Code is supported",
        ):
            with self.subTest(compatibility=compatibility), tempfile.TemporaryDirectory() as tmp:
                skill = self.make_skill(Path(tmp))
                Path(skill.path).write_text(
                    f"---\nname: portable-skill\ndescription: Test\ncompatibility: {compatibility}\n---\n",
                    encoding="utf-8",
                )
                checker = CompatibilityChecker()
                codex_note = next(check for check in checker.check(skill, FakeAdapter()) if check.name == "compatibility-notes")
                claude_note = next(check for check in checker.check(skill, ClaudeAdapter()) if check.name == "compatibility-notes")
                self.assertEqual(codex_note.status, "warn" if compatibility.startswith("Without") else "block")
                self.assertEqual(claude_note.status, "pass")

    def test_common_harness_short_name_is_checked_for_exclusion(self) -> None:
        class QwenAdapter(FakeAdapter):
            agent_id = "qwen"
            display_name = "Qwen Code"

        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(Path(tmp))
            Path(skill.path).write_text(
                "---\nname: portable-skill\ndescription: Test\ncompatibility: No Qwen support\n---\n",
                encoding="utf-8",
            )
            note = next(
                check for check in CompatibilityChecker().check(skill, QwenAdapter())
                if check.name == "compatibility-notes"
            )
            self.assertEqual(note.status, "block")
            self.assertIn("explicitly excludes Qwen Code", note.message)

    def test_versioned_target_compatibility_is_kept_for_review(self) -> None:
        for compatibility in (
            "Codex >= 2.0 required",
            "Codex > 2.0",
            "Codex < 2.0",
            "Codex v2 required",
            "Codex version 2",
        ):
            with self.subTest(compatibility=compatibility), tempfile.TemporaryDirectory() as tmp:
                skill = self.make_skill(Path(tmp))
                Path(skill.path).write_text(
                    f"---\nname: portable-skill\ndescription: Test\ncompatibility: {compatibility}\n---\n",
                    encoding="utf-8",
                )
                checks = CompatibilityChecker().check(skill, FakeAdapter())
                note = next(check for check in checks if check.name == "compatibility-notes")
                self.assertEqual(note.status, "warn")
                self.assertIn("versioned requirement", note.message)

    def test_yaml_block_compatibility_is_not_discarded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(Path(tmp))
            Path(skill.path).write_text(
                "---\nname: portable-skill\ndescription: Test\ncompatibility: |\n  Not compatible with Codex\n---\n",
                encoding="utf-8",
            )
            checks = CompatibilityChecker().check(skill, FakeAdapter())
            note = next(check for check in checks if check.name == "compatibility-notes")
            self.assertEqual(note.status, "block")
            self.assertIn("Not compatible with Codex", note.details["compatibility"])

    def test_advisory_compatibility_text_is_not_treated_as_unknown_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(Path(tmp))
            Path(skill.path).write_text(
                "---\nname: portable-skill\ndescription: Test\ncompatibility: Works in local agent environments\n---\n",
                encoding="utf-8",
            )
            checks = CompatibilityChecker().check(skill, FakeAdapter())
            note = next(check for check in checks if check.name == "compatibility-notes")
            self.assertEqual(note.status, "pass")
            self.assertIn("informational", note.message)

    def test_target_version_change_invalidates_compatibility_cache(self) -> None:
        class VersionedAdapter(FakeAdapter):
            version = "1.0"

            def get_version(self):
                return self.version

        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(Path(tmp))
            Path(skill.path).write_text(
                "---\nname: portable-skill\ndescription: Test\ncompatibility: Harness >= 1.0\n---\n",
                encoding="utf-8",
            )
            checker = CompatibilityChecker()
            adapter = VersionedAdapter()
            first = checker.check(skill, adapter)
            adapter.version = "2.0"
            second = checker.check(skill, adapter)

            first_note = next(check for check in first if check.name == "compatibility-notes")
            second_note = next(check for check in second if check.name == "compatibility-notes")
            self.assertEqual(first_note.details["targetVersion"], "1.0")
            self.assertEqual(second_note.details["targetVersion"], "2.0")

    def test_local_support_references_warn_because_they_are_not_synced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(Path(tmp), "Run scripts/check.py and read references/guide.md.")
            (Path(skill.path).parent / "scripts").mkdir()
            (Path(skill.path).parent / "scripts" / "check.py").write_text("# local helper", encoding="utf-8")
            checks = CompatibilityChecker().check(skill, FakeAdapter())
            scope_check = next(check for check in checks if check.name == "sync-scope")
            self.assertEqual(scope_check.status, "warn")
            self.assertEqual(scope_check.details["references"], ["scripts/check.py", "references/guide.md"])
            self.assertEqual(scope_check.details["presentReferences"], ["scripts/check.py"])
            self.assertEqual(scope_check.details["missingReferences"], ["references/guide.md"])
            self.assertEqual(scope_check.details["copyScope"], ["SKILL.md"])

    def test_reference_outside_skill_folder_is_not_followed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = self.make_skill(root, "Read [private](../outside.md).")
            checks = CompatibilityChecker().check(skill, FakeAdapter())
            scope_check = next(check for check in checks if check.name == "sync-scope")
            self.assertEqual(scope_check.details["outsideSkillFolderReferences"], ["../outside.md"])

    def test_bare_rich_text_and_config_references_are_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = self.make_skill(root, "Read docs/guide.rst and data/config.ini before running.")
            docs = Path(skill.path).parent / "docs"
            data = Path(skill.path).parent / "data"
            docs.mkdir()
            data.mkdir()
            (docs / "guide.rst").write_text("Guide", encoding="utf-8")
            (data / "config.ini").write_text("[tool]", encoding="utf-8")
            checks = CompatibilityChecker().check(skill, FakeAdapter())
            scope_check = next(check for check in checks if check.name == "sync-scope")
            self.assertEqual(scope_check.details["references"], ["docs/guide.rst", "data/config.ini"])
            self.assertEqual(scope_check.details["presentReferences"], ["docs/guide.rst", "data/config.ini"])
            self.assertEqual(scope_check.details["missingReferences"], [])

    def test_directory_only_dependency_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = self.make_skill(root, "Use scripts/ and templates/ when running.")
            (Path(skill.path).parent / "scripts").mkdir()
            (Path(skill.path).parent / "templates").mkdir()
            checks = CompatibilityChecker().check(skill, FakeAdapter())
            scope_check = next(check for check in checks if check.name == "sync-scope")
            self.assertEqual(scope_check.details["references"], ["scripts/", "templates/"])
            self.assertEqual(scope_check.details["presentReferences"], ["scripts/", "templates/"])

    def test_frontmatter_description_dependencies_are_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(Path(tmp))
            Path(skill.path).write_text(
                "---\nname: portable-skill\ndescription: Run scripts/helper.py to process the input\n---\n",
                encoding="utf-8",
            )
            checks = CompatibilityChecker().check(skill, FakeAdapter())
            scope_check = next(check for check in checks if check.name == "sync-scope")
            self.assertEqual(scope_check.details["references"], ["scripts/helper.py"])
            self.assertEqual(scope_check.details["missingReferences"], ["scripts/helper.py"])

    def test_invalid_utf8_is_not_classified_as_technically_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(Path(tmp))
            Path(skill.path).write_bytes(
                b"---\nname: portable-skill\ndescription: Test\n---\n\xff"
            )
            checks = CompatibilityChecker().check(skill, FakeAdapter())
            result = PreflightResult.from_checks(checks)
            self.assertEqual(result.technical_compatibility["status"], "incompatible")

    def test_remote_url_paths_are_not_treated_as_bundled_resources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(Path(tmp), "Read https://example.com/assets/reference.pdf for details.")
            checks = CompatibilityChecker().check(skill, FakeAdapter())
            scope_check = next(check for check in checks if check.name == "sync-scope")
            self.assertEqual(scope_check.status, "pass")

    def test_markdown_link_to_any_local_file_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(Path(tmp), "See [the guide](docs/guide.md) for details.")
            checks = CompatibilityChecker().check(skill, FakeAdapter())
            scope_check = next(check for check in checks if check.name == "sync-scope")
            self.assertEqual(scope_check.status, "warn")
            self.assertIn("docs/guide.md", scope_check.details["references"])

    def test_bare_jinja_template_reference_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = self.make_skill(Path(tmp), "Render templates/prompt.j2 before continuing.")
            checks = CompatibilityChecker().check(skill, FakeAdapter())
            scope_check = next(check for check in checks if check.name == "sync-scope")
            self.assertEqual(scope_check.status, "warn")
            self.assertIn("templates/prompt.j2", scope_check.details["references"])


if __name__ == "__main__":
    unittest.main()
