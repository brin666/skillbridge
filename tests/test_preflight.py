"""Tests for Phase 5A Preflight safety checks."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.adapters.base import AgentAdapter
from backend.core.cache_manager import CacheManager
from backend.core.preflight import PreflightChecker
from backend.models.skill import Skill


class FakeAdapter(AgentAdapter):
    agent_id = "trae"
    display_name = "TRAE"

    def __init__(self, root: Path):
        super().__init__()
        self.root = root

    def _candidate_skill_paths(self):
        return [self.root]

    def supports_skill(self, skill):
        return True

    def capabilities(self):
        return ["filesystem", "shell"]


def make_skill_dir(root: Path, name: str = "pdf", description: str = "PDF tools") -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n",
        encoding="utf-8",
    )
    return skill_dir


class PreflightTests(unittest.TestCase):
    def test_unknown_runtime_range_is_not_assumed_compatible(self) -> None:
        checker = PreflightChecker(adapters=[])
        self.assertIsNone(checker._version_satisfies("20.0.0", ">=18 <20"))
        self.assertFalse(checker._version_satisfies("2.0.0", "^1.2.0"))
        self.assertTrue(checker._version_satisfies("1.9.0", "^1.2.0"))

    def test_missing_skill_md_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "pdf"
            skill_dir.mkdir()
            skill = Skill(id="pdf", name="pdf", path=str(skill_dir / "SKILL.md"))
            checker = PreflightChecker(adapters=[FakeAdapter(root)])
            result = checker.check(skill, "trae")
            self.assertEqual(result.status, "block")
            self.assertTrue(any(c.name == "SKILL.md" and c.status == "block" for c in result.checks))

    def test_bad_frontmatter_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "pdf"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "---\nname: pdf\ndescription: broken\n",
                encoding="utf-8",
            )
            skill = Skill(id="pdf", name="pdf", path=str(skill_dir / "SKILL.md"))
            checker = PreflightChecker(adapters=[FakeAdapter(root)])
            result = checker.check(skill, "trae")
            self.assertEqual(result.status, "block")
            self.assertTrue(any(c.name == "frontmatter" and c.status == "block" for c in result.checks))

    def test_unknown_source_does_not_gate_compatibility_or_sync(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skills"
            make_skill_dir(root, "pdf")
            skill_dir = root / "pdf"
            skill = Skill(id="pdf", name="pdf", path=str(skill_dir / "SKILL.md"))
            checker = PreflightChecker(adapters=[FakeAdapter(root)])
            result = checker.check(skill, "trae")
            source_check = next(c for c in result.checks if c.name == "source")
            self.assertEqual(source_check.status, "pass")
            self.assertEqual(result.status, "pass")

    def test_technical_compatibility_is_separate_from_permission_and_target_setup(self) -> None:
        class MissingTargetRootAdapter(FakeAdapter):
            def _candidate_skill_paths(self):
                return [self.root / "not-created-yet"]

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_root = base / "target"
            skill_dir = make_skill_dir(source_root, "pdf")
            skill = Skill(id="pdf", name="pdf", path=str(skill_dir / "SKILL.md"))

            result = PreflightChecker(adapters=[MissingTargetRootAdapter(target_root)]).check(skill, "trae")

            self.assertEqual(result.status, "block")
            self.assertEqual(result.technical_compatibility["status"], "compatible")
            self.assertEqual(result.technical_compatibility["notes"], [])
            self.assertEqual(
                result.to_dict()["technicalCompatibility"]["status"],
                "compatible",
            )

    def test_detected_source_without_explicit_sync_permission_is_still_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skills"
            skill_dir = make_skill_dir(root, "pdf")
            (skill_dir / "metadata.json").write_text(
                '{"repository":"https://github.com/example/pdf"}',
                encoding="utf-8",
            )
            skill = Skill(id="pdf", name="pdf", path=str(skill_dir / "SKILL.md"))

            result = PreflightChecker(adapters=[FakeAdapter(root)]).check(skill, "trae")

            source_check = next(check for check in result.checks if check.name == "source")
            self.assertEqual(source_check.status, "pass")
            self.assertIn("does not determine Harness compatibility", source_check.message)

    def test_explicit_sync_permission_allows_source_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skills"
            skill_dir = make_skill_dir(root, "pdf")
            (skill_dir / "SKILL.md").write_text(
                "---\nname: pdf\ndescription: PDF tools\nmetadata:\n  skillbridge-sync: allow\n---\n",
                encoding="utf-8",
            )
            (skill_dir / "metadata.json").write_text(
                '{"repository":"https://github.com/example/pdf"}',
                encoding="utf-8",
            )
            skill = Skill(id="pdf", name="pdf", path=str(skill_dir / "SKILL.md"))

            result = PreflightChecker(adapters=[FakeAdapter(root)]).check(skill, "trae")

            source_check = next(check for check in result.checks if check.name == "source")
            self.assertEqual(source_check.status, "pass")
            self.assertEqual(source_check.details["syncPermission"], "allow")

    def test_explicit_sync_opt_out_blocks_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skills"
            skill_dir = make_skill_dir(root, "pdf")
            (skill_dir / "SKILL.md").write_text(
                "---\nname: pdf\ndescription: PDF tools\nmetadata:\n  skillbridge-sync: deny\n---\n",
                encoding="utf-8",
            )
            skill = Skill(id="pdf", name="pdf", path=str(skill_dir / "SKILL.md"))

            result = PreflightChecker(adapters=[FakeAdapter(root)]).check(skill, "trae")

            source_check = next(check for check in result.checks if check.name == "source")
            self.assertEqual(source_check.status, "block")
            self.assertEqual(result.status, "block")

    def test_symbolic_link_target_blocks_sync(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "source"
            target_root = root / "target"
            skill_dir = make_skill_dir(source_root, "pdf")
            target_root.mkdir()
            external_skill = make_skill_dir(root / "external", "pdf")
            target_skill_dir = target_root / "pdf"
            target_skill_dir.mkdir()
            (target_skill_dir / "SKILL.md").write_bytes((external_skill / "SKILL.md").read_bytes())
            skill = Skill(id="pdf", name="pdf", path=str(skill_dir / "SKILL.md"))

            with patch.object(Path, "is_symlink", lambda path: path == target_skill_dir):
                result = PreflightChecker(adapters=[FakeAdapter(target_root)]).check(skill, "trae")

            conflict = next(check for check in result.checks if check.name == "conflict")
            self.assertEqual(conflict.status, "block")
            self.assertIn("symbolic link", conflict.message)

    def test_single_file_skill_does_not_warn_about_optional_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skills"
            skill_dir = make_skill_dir(root, "pdf")
            skill = Skill(id="pdf", name="pdf", path=str(skill_dir / "SKILL.md"))
            result = PreflightChecker(adapters=[FakeAdapter(root)]).check(skill, "trae")
            directory_check = next(c for c in result.checks if c.name == "directory-structure")
            scope_check = next(c for c in result.checks if c.name == "sync-scope")
            self.assertEqual(directory_check.status, "pass")
            self.assertEqual(scope_check.status, "pass")

    def test_referenced_resources_are_reported_for_single_file_sync(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skills"
            skill_dir = make_skill_dir(root, "pdf")
            (skill_dir / "SKILL.md").write_text(
                "---\nname: pdf\ndescription: PDF tools\n---\nRun `scripts/extract.py` and read references/guide.md.\n",
                encoding="utf-8",
            )
            skill = Skill(id="pdf", name="pdf", path=str(skill_dir / "SKILL.md"))
            result = PreflightChecker(adapters=[FakeAdapter(root)]).check(skill, "trae")
            scope_check = next(c for c in result.checks if c.name == "sync-scope")
            self.assertEqual(scope_check.status, "warn")
            self.assertEqual(scope_check.details["references"], ["scripts/extract.py", "references/guide.md"])

    def test_runtime_mismatch_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skills"
            skill_dir = make_skill_dir(root, "pdf")
            (skill_dir / "package.json").write_text(
                '{"engines": {"node": ">=999.0.0"}}',
                encoding="utf-8",
            )
            skill = Skill(id="pdf", name="pdf", path=str(skill_dir / "SKILL.md"))
            checker = PreflightChecker(adapters=[FakeAdapter(root)])
            result = checker.check(skill, "trae")
            self.assertEqual(result.status, "block")
            self.assertTrue(any(c.name == "runtime-node" and c.status == "block" for c in result.checks))

    def test_same_hash_at_target_passes_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_root = base / "target"
            source_dir = make_skill_dir(source_root, "pdf")
            target_dir = make_skill_dir(target_root, "pdf")
            cache = CacheManager(base / "cache")
            same_hash = cache.compute_skill_hash(source_dir)
            # Make target identical.
            (target_dir / "SKILL.md").write_text(
                (source_dir / "SKILL.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            same_hash = cache.compute_skill_hash(source_dir)
            skill = Skill(id="pdf", name="pdf", path=str(source_dir / "SKILL.md"), hash=same_hash)
            checker = PreflightChecker(adapters=[FakeAdapter(target_root)], cache_manager=cache)
            result = checker.check(skill, "trae")
            conflict = next(c for c in result.checks if c.name == "conflict")
            self.assertEqual(conflict.status, "pass")
            self.assertIn("already installed", conflict.message)

    def test_different_hash_at_target_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_root = base / "target"
            source_dir = make_skill_dir(source_root, "pdf", "Source version")
            make_skill_dir(target_root, "pdf", "Different target version")
            cache = CacheManager(base / "cache")
            source_hash = cache.compute_skill_hash(source_dir)
            skill = Skill(id="pdf", name="pdf", path=str(source_dir / "SKILL.md"), hash=source_hash)
            checker = PreflightChecker(adapters=[FakeAdapter(target_root)], cache_manager=cache)
            result = checker.check(skill, "trae")
            conflict = next(c for c in result.checks if c.name == "conflict")
            self.assertEqual(conflict.status, "warn")
            self.assertIn("differs", conflict.message)

    def test_nested_target_skill_is_found_by_declared_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_root = base / "target"
            source_dir = make_skill_dir(source_root, "pdf")
            nested_dir = target_root / "community" / "another-folder"
            nested_dir.mkdir(parents=True)
            (nested_dir / "SKILL.md").write_text(
                (source_dir / "SKILL.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            skill = Skill(id="pdf", name="pdf", path=str(source_dir / "SKILL.md"))

            result = PreflightChecker(adapters=[FakeAdapter(target_root)]).check(skill, "trae")

            conflict = next(check for check in result.checks if check.name == "conflict")
            self.assertEqual(conflict.status, "pass")
            self.assertIn("nested target directory", conflict.message)
            self.assertEqual(conflict.details["targetPaths"], [str(nested_dir / "SKILL.md")])

    def test_nested_target_version_difference_is_reviewed_with_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_dir = make_skill_dir(base / "source", "pdf", "Source version")
            nested_dir = base / "target" / "community" / "pdf-copy"
            make_skill_dir(nested_dir.parent, "pdf-copy", "Different target version")
            (nested_dir / "SKILL.md").write_text(
                "---\nname: pdf\ndescription: Different target version\n---\n",
                encoding="utf-8",
            )
            skill = Skill(id="pdf", name="pdf", path=str(source_dir / "SKILL.md"))

            result = PreflightChecker(adapters=[FakeAdapter(base / "target")]).check(skill, "trae")

            conflict = next(check for check in result.checks if check.name == "conflict")
            self.assertEqual(conflict.status, "warn")
            self.assertIn(str(nested_dir / "SKILL.md"), conflict.details["targetPaths"])


if __name__ == "__main__":
    unittest.main()
