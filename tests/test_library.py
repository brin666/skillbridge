"""Tests for Phase 6A Central Skill Library."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.adapters.base import AgentAdapter
from backend.core.cache_manager import CacheManager
from backend.core.hash_utils import compute_skill_hash
from backend.core.installer import Installer
from backend.core.library_manager import LibraryManager
from backend.core.preflight import PreflightChecker
from backend.core.rollback import RollbackManager
from backend.core.sync_manager import SyncManager
from backend.models.agent import Agent
from backend.models.skill import Skill


def make_skill(root: Path, name: str = "pdf", description: str = "PDF tools") -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\nmetadata:\n  skillbridge-sync: allow\n---\n",
        encoding="utf-8",
    )
    (skill_dir / "metadata.json").write_text(
        '{"repository": "https://github.com/example/pdf"}',
        encoding="utf-8",
    )
    (skill_dir / "scripts").mkdir(exist_ok=True)
    return skill_dir


class FakeAdapter(AgentAdapter):
    def __init__(self, agent_id: str, root: Path | None):
        super().__init__()
        self.agent_id = agent_id
        self.display_name = agent_id
        self.root = root

    def _candidate_skill_paths(self):
        return [self.root] if self.root is not None else []

    def supports_skill(self, skill):
        return True

    def capabilities(self):
        return ["filesystem", "shell"]


class LibraryTests(unittest.TestCase):
    def _library(self, base: Path) -> LibraryManager:
        return LibraryManager(
            library_root=base / "library",
            trash_root=base / "trash" / "library",
        )

    def _skill(self, source_dir: Path, name: str = "pdf") -> Skill:
        return Skill(
            id=name,
            name=name,
            path=str(source_dir / "SKILL.md"),
            hash=compute_skill_hash(source_dir),
        )

    def test_deployment_state_compares_only_skill_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_dir = make_skill(base / "source")
            target_root = base / "target"
            target_dir = target_root / "pdf"
            target_dir.mkdir(parents=True)
            (target_dir / "SKILL.md").write_bytes((source_dir / "SKILL.md").read_bytes())
            (target_dir / "local-notes.txt").write_text("target-only file", encoding="utf-8")

            library = self._library(base)
            library.import_skill(self._skill(source_dir), "codex")
            lib_skill = library.get_library_skill("pdf")
            agent = Agent(id="trae", name="Trae", installed=True, skill_paths=[str(target_root)])

            state = library.compare_deployments(lib_skill, [agent])["trae"]

            self.assertEqual(state.status, "same")
            self.assertTrue(state.same_hash)

    def test_deployment_state_marks_different_skill_md_as_diverged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_dir = make_skill(base / "source")
            target_root = base / "target"
            target_dir = make_skill(target_root, description="Different target version")

            library = self._library(base)
            library.import_skill(self._skill(source_dir), "codex")
            lib_skill = library.get_library_skill("pdf")
            agent = Agent(id="trae", name="Trae", installed=True, skill_paths=[str(target_root)])

            state = library.compare_deployments(lib_skill, [agent])["trae"]

            self.assertEqual(state.status, "diverged")
            self.assertFalse(state.same_hash)

    def test_deployment_state_finds_nested_skill_by_declared_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_dir = make_skill(base / "source")
            target_root = base / "target"
            nested_dir = make_skill(target_root / "group", "renamed-folder")
            (nested_dir / "SKILL.md").write_bytes((source_dir / "SKILL.md").read_bytes())

            library = self._library(base)
            library.import_skill(self._skill(source_dir), "codex")
            lib_skill = library.get_library_skill("pdf")
            agent = Agent(id="trae", name="Trae", installed=True, skill_paths=[str(target_root)])

            state = library.compare_deployments(lib_skill, [agent])["trae"]

            self.assertEqual(state.status, "same")
            self.assertTrue(state.same_hash)
            self.assertEqual(state.path, str(nested_dir))

    def test_deployment_state_finds_disabled_sibling_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_dir = make_skill(base / "source")
            target_root = base / "target" / "skills"
            disabled_dir = make_skill(base / "target" / "skills_disabled" / "group", "renamed-folder")
            (disabled_dir / "SKILL.md").write_bytes((source_dir / "SKILL.md").read_bytes())

            library = self._library(base)
            library.import_skill(self._skill(source_dir), "codex")
            lib_skill = library.get_library_skill("pdf")
            agent = Agent(id="trae", name="Trae", installed=True, skill_paths=[str(target_root)])

            state = library.compare_deployments(lib_skill, [agent])["trae"]

            self.assertEqual(state.status, "disabled")
            self.assertTrue(state.same_hash)
            self.assertEqual(state.path, str(disabled_dir))

    def test_library_import_canonicalizes_lowercase_skill_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_dir = make_skill(base / "source")
            (source_dir / "SKILL.md").rename(source_dir / "skill.md")
            skill = Skill(
                id="pdf",
                name="pdf",
                path=str(source_dir / "skill.md"),
                hash=compute_skill_hash(source_dir),
            )
            library = self._library(base)

            result = library.import_skill(skill, "codex")

            imported_dir = base / "library" / "skills" / "pdf"
            self.assertEqual(result["status"], "success")
            self.assertTrue((imported_dir / "SKILL.md").is_file())
            skill_md_names = [
                entry.name
                for entry in imported_dir.iterdir()
                if entry.name.casefold() == "skill.md"
            ]
            self.assertEqual(skill_md_names, ["SKILL.md"])
            self.assertEqual(compute_skill_hash(imported_dir), skill.hash)

    def test_normal_import_to_library(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            source_dir = make_skill(source_root)
            library = self._library(base)
            result = library.import_skill(self._skill(source_dir), "codex")
            self.assertEqual(result["status"], "success")
            self.assertTrue((base / "library" / "skills" / "pdf" / "SKILL.md").is_file())
            self.assertTrue((base / "library" / "index.json").is_file())

    def test_import_does_not_modify_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            source_dir = make_skill(source_root)
            before = (source_dir / "SKILL.md").read_text(encoding="utf-8")
            library = self._library(base)
            library.import_skill(self._skill(source_dir), "codex")
            after = (source_dir / "SKILL.md").read_text(encoding="utf-8")
            self.assertEqual(before, after)
            self.assertTrue((source_dir / "SKILL.md").is_file())

    def test_same_hash_reimport_returns_already_in_library(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            source_dir = make_skill(source_root)
            library = self._library(base)
            library.import_skill(self._skill(source_dir), "codex")
            result = library.import_skill(self._skill(source_dir), "codex")
            self.assertEqual(result["status"], "already_in_library")

    def test_different_hash_returns_library_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            source_dir = make_skill(source_root)
            library = self._library(base)
            library.import_skill(self._skill(source_dir), "codex")
            (source_dir / "SKILL.md").write_text(
                "---\nname: pdf\ndescription: changed version\n---\n",
                encoding="utf-8",
            )
            result = library.import_skill(self._skill(source_dir), "codex")
            self.assertEqual(result["status"], "library_conflict")

    def test_library_skill_deploy_to_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_root = base / "trae"
            target_root.mkdir()
            source_dir = make_skill(source_root)
            library = self._library(base)
            library.import_skill(self._skill(source_dir), "codex")
            lib_skill = library.get_library_skill("pdf")
            self.assertIsNotNone(lib_skill)

            cache = CacheManager(base / "cache")
            adapter = FakeAdapter("trae", target_root)
            checker = PreflightChecker(adapters=[adapter], cache_manager=cache)
            manager = SyncManager(
                preflight_checker=checker,
                installer=Installer(tmp_root=base / "tmp"),
                rollback_manager=RollbackManager(state_root=base),
                cache_manager=cache,
            )
            deploy_skill = Skill(
                id=lib_skill.id,
                name=lib_skill.name,
                path=str(Path(lib_skill.library_path) / "SKILL.md"),
                hash=lib_skill.hash,
            )
            result = manager.sync(deploy_skill, "trae", {})
            self.assertEqual(result["status"], "success")
            self.assertTrue((target_root / "pdf" / "SKILL.md").is_file())

    def test_deploy_same_hash_returns_already_installed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_root = base / "target"
            source_dir = make_skill(source_root)
            make_skill(target_root, "pdf", "PDF tools")
            library = self._library(base)
            library.import_skill(self._skill(source_dir), "codex")
            lib_skill = library.get_library_skill("pdf")
            cache = CacheManager(base / "cache")
            adapter = FakeAdapter("trae", target_root)
            checker = PreflightChecker(adapters=[adapter], cache_manager=cache)
            manager = SyncManager(
                preflight_checker=checker,
                installer=Installer(tmp_root=base / "tmp"),
                rollback_manager=RollbackManager(state_root=base),
                cache_manager=cache,
            )
            deploy_skill = Skill(
                id=lib_skill.id,
                name=lib_skill.name,
                path=str(Path(lib_skill.library_path) / "SKILL.md"),
                hash=lib_skill.hash,
            )
            result = manager.sync(deploy_skill, "trae", {})
            self.assertEqual(result["status"], "already_installed")

    def test_deploy_different_hash_returns_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_root = base / "target"
            source_dir = make_skill(source_root)
            make_skill(target_root, "pdf", "different version")
            library = self._library(base)
            library.import_skill(self._skill(source_dir), "codex")
            lib_skill = library.get_library_skill("pdf")
            cache = CacheManager(base / "cache")
            adapter = FakeAdapter("trae", target_root)
            checker = PreflightChecker(adapters=[adapter], cache_manager=cache)
            manager = SyncManager(
                preflight_checker=checker,
                installer=Installer(tmp_root=base / "tmp"),
                rollback_manager=RollbackManager(state_root=base),
                cache_manager=cache,
            )
            deploy_skill = Skill(
                id=lib_skill.id,
                name=lib_skill.name,
                path=str(Path(lib_skill.library_path) / "SKILL.md"),
                hash=lib_skill.hash,
            )
            result = manager.sync(deploy_skill, "trae", {"confirm_warning": True})
            self.assertEqual(result["status"], "conflict")

    def test_remove_from_library_keeps_agent_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            source_dir = make_skill(source_root)
            library = self._library(base)
            library.import_skill(self._skill(source_dir), "codex")
            result = library.remove_from_library("pdf")
            self.assertEqual(result["status"], "success")
            self.assertFalse((base / "library" / "skills" / "pdf").exists())
            self.assertTrue((source_dir / "SKILL.md").is_file())

    def test_index_rebuild_after_loss(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            source_dir = make_skill(source_root)
            library = self._library(base)
            library.import_skill(self._skill(source_dir), "codex")
            (base / "library" / "index.json").unlink()
            rebuilt = LibraryManager(
                library_root=base / "library",
                trash_root=base / "trash" / "library",
            )
            skills = rebuilt.list_library_skills()
            self.assertEqual(len(skills), 1)
            self.assertEqual(skills[0].id, "pdf")

    def test_library_hash_matches_scanner_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            source_dir = make_skill(source_root)
            library = self._library(base)
            library.import_skill(self._skill(source_dir), "codex")
            lib_skill = library.get_library_skill("pdf")
            scanner_hash = CacheManager(base / "cache").compute_skill_hash(source_dir)
            self.assertEqual(lib_skill.hash, scanner_hash)


if __name__ == "__main__":
    unittest.main()
