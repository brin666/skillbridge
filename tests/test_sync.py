"""Tests for Phase 5B Safe Sync + Atomic Installation."""

from __future__ import annotations

import sys
import threading
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.adapters.base import AgentAdapter
from backend.core.cache_manager import CacheManager
from backend.core.hash_utils import compute_skill_md_hash
from backend.core.installer import Installer
from backend.core.preflight import PreflightChecker
from backend.core.rollback import RollbackManager
from backend.core.sync_manager import SyncManager
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


def make_skill(
    root: Path,
    name: str = "pdf",
    description: str = "PDF tools",
    clean: bool = False,
) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    consent = "metadata:\n  skillbridge-sync: allow\n" if clean else ""
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n{consent}---\n",
        encoding="utf-8",
    )
    if clean:
        (skill_dir / "metadata.json").write_text(
            '{"repository": "https://github.com/example/pdf-skill"}',
            encoding="utf-8",
        )
        (skill_dir / "scripts").mkdir(exist_ok=True)
        (skill_dir / "references").mkdir(exist_ok=True)
    return skill_dir


def make_manager(base: Path, source_root: Path, target_root: Path) -> SyncManager:
    cache = CacheManager(base / "cache")
    adapter = FakeAdapter(target_root)
    checker = PreflightChecker(adapters=[adapter], cache_manager=cache)
    installer = Installer(tmp_root=base / "tmp")
    rollback = RollbackManager(state_root=base)
    return SyncManager(
        preflight_checker=checker,
        installer=installer,
        rollback_manager=rollback,
        cache_manager=cache,
    )


class SyncManagerTests(unittest.TestCase):
    def test_normal_sync_installs_to_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_root = base / "target"
            target_root.mkdir()
            source_dir = make_skill(source_root, clean=True)
            cache = CacheManager(base / "cache")
            skill = Skill(
                id="pdf",
                name="pdf",
                path=str(source_dir / "SKILL.md"),
                hash=cache.compute_skill_hash(source_dir),
            )
            manager = make_manager(base, source_root, target_root)
            result = manager.sync(skill, "trae", {})
            self.assertEqual(result["status"], "success")
            self.assertTrue((target_root / "pdf" / "SKILL.md").is_file())

    def test_sync_does_not_duplicate_same_skill_found_in_nested_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_root = base / "target"
            source_dir = make_skill(source_root, clean=True)
            nested_dir = target_root / "group" / "renamed-folder"
            nested_dir.mkdir(parents=True)
            (nested_dir / "SKILL.md").write_bytes((source_dir / "SKILL.md").read_bytes())
            skill = Skill(id="pdf", name="pdf", path=str(source_dir / "SKILL.md"))

            result = make_manager(base, source_root, target_root).sync(skill, "trae", {})

            self.assertEqual(result["status"], "already_installed")
            self.assertFalse((target_root / "pdf").exists())
            self.assertEqual(result["target"], str(nested_dir / "SKILL.md"))

    def test_force_replace_cannot_create_duplicate_for_nested_different_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_root = base / "target"
            source_dir = make_skill(source_root, description="Source version", clean=True)
            nested_dir = target_root / "group" / "renamed-folder"
            nested_dir.mkdir(parents=True)
            (nested_dir / "SKILL.md").write_text(
                "---\nname: pdf\ndescription: Existing different version\n---\n",
                encoding="utf-8",
            )
            skill = Skill(id="pdf", name="pdf", path=str(source_dir / "SKILL.md"))

            result = make_manager(base, source_root, target_root).sync(
                skill,
                "trae",
                {"confirm_warning": True, "force_replace": True},
            )

            self.assertEqual(result["status"], "conflict")
            self.assertIn(str(nested_dir / "SKILL.md"), result["target"])
            self.assertFalse((target_root / "pdf").exists())

    def test_sync_copies_only_skill_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            source_dir = make_skill(source_root, clean=True)
            (source_dir / "scripts").mkdir(exist_ok=True)
            (source_dir / "scripts" / "helper.py").write_text("print('source')", encoding="utf-8")
            target_root = base / "target"
            target_root.mkdir()
            skill = Skill(id="pdf", name="pdf", path=str(source_dir / "SKILL.md"))
            result = make_manager(base, source_root, target_root).sync(skill, "trae", {})
            self.assertEqual(result["status"], "success")
            self.assertTrue((target_root / "pdf" / "SKILL.md").is_file())
            self.assertFalse((target_root / "pdf" / "scripts").exists())

    def test_force_replace_preserves_target_files_other_than_skill_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            source_dir = make_skill(source_root, description="New source version", clean=True)
            target_root = base / "target"
            target_dir = make_skill(target_root, description="Existing target version")
            (target_dir / "local-note.txt").write_text("keep me", encoding="utf-8")
            skill = Skill(id="pdf", name="pdf", path=str(source_dir / "SKILL.md"))
            result = make_manager(base, source_root, target_root).sync(
                skill,
                "trae",
                {"confirm_warning": True, "force_replace": True},
            )
            self.assertEqual(result["status"], "success")
            self.assertTrue((target_dir / "local-note.txt").is_file())

    def test_failed_replace_restores_only_the_old_skill_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_root = base / "target"
            source_dir = make_skill(source_root, description="New source version", clean=True)
            target_dir = make_skill(target_root, description="Existing target version")
            old_contents = (target_dir / "SKILL.md").read_text(encoding="utf-8")
            (target_dir / "local-note.txt").write_text("keep me", encoding="utf-8")
            skill = Skill(id="pdf", name="pdf", path=str(source_dir / "SKILL.md"))
            manager = make_manager(base, source_root, target_root)
            installer = manager.installer
            install = installer.install_skill_md_bytes

            def install_then_fail(payload, destination, transaction_id):
                install(payload, destination, transaction_id)
                raise RuntimeError("simulated commit failure")

            installer.install_skill_md_bytes = install_then_fail  # type: ignore[method-assign]
            result = manager.sync(skill, "trae", {"confirm_warning": True, "force_replace": True})
            self.assertEqual(result["status"], "failed")
            self.assertEqual((target_dir / "SKILL.md").read_text(encoding="utf-8"), old_contents)
            self.assertEqual((target_dir / "local-note.txt").read_text(encoding="utf-8"), "keep me")

    def test_failed_first_install_removes_only_its_new_skill_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_root = base / "target"
            target_root.mkdir()
            source_dir = make_skill(source_root, clean=True)
            manager = make_manager(base, source_root, target_root)
            installer = manager.installer
            install = installer.install_skill_md_bytes

            def install_then_fail(payload, destination, transaction_id):
                install(payload, destination, transaction_id)
                raise RuntimeError("simulated post-install failure")

            installer.install_skill_md_bytes = install_then_fail  # type: ignore[method-assign]
            result = manager.sync(
                Skill(id="pdf", name="pdf", path=str(source_dir / "SKILL.md")),
                "trae",
                {},
            )

            self.assertEqual(result["status"], "failed")
            self.assertFalse((target_root / "pdf").exists())

    def test_missing_skill_md_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_root = base / "target"
            source_root.mkdir()
            target_root.mkdir()
            skill = Skill(id="pdf", name="pdf", path=str(source_root / "pdf" / "SKILL.md"))
            manager = make_manager(base, source_root, target_root)
            result = manager.sync(skill, "trae", {})
            self.assertEqual(result["status"], "failed")
            self.assertFalse((target_root / "pdf").exists())

    def test_sync_refuses_to_write_through_target_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_root = base / "target"
            target_root.mkdir()
            source_dir = make_skill(source_root, clean=True)
            external_skill = make_skill(base / "external", description="Keep this version")
            old_contents = (external_skill / "SKILL.md").read_text(encoding="utf-8")
            target_skill_dir = target_root / "pdf"
            target_skill_dir.mkdir()
            (target_skill_dir / "SKILL.md").write_text("different target", encoding="utf-8")
            skill = Skill(id="pdf", name="pdf", path=str(source_dir / "SKILL.md"))

            with patch.object(Path, "is_symlink", lambda path: path == target_skill_dir):
                result = make_manager(base, source_root, target_root).sync(
                    skill,
                    "trae",
                    {"confirm_warning": True, "force_replace": True},
                )

            self.assertEqual(result["status"], "failed")
            self.assertEqual((external_skill / "SKILL.md").read_text(encoding="utf-8"), old_contents)

    def test_expected_source_hash_prevents_syncing_unreviewed_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_root = base / "target"
            target_root.mkdir()
            source_dir = make_skill(source_root, clean=True)
            expected_hash = compute_skill_md_hash(source_dir / "SKILL.md")
            (source_dir / "SKILL.md").write_text(
                "---\nname: pdf\ndescription: Changed after preview\n---\n",
                encoding="utf-8",
            )
            skill = Skill(id="pdf", name="pdf", path=str(source_dir / "SKILL.md"))

            result = make_manager(base, source_root, target_root).start_sync(
                skill,
                "trae",
                {"expected_skill_md_hash": expected_hash},
            )

            self.assertEqual(result["status"], "stale")
            self.assertFalse((target_root / "pdf").exists())

    def test_source_change_during_staging_does_not_install_unreviewed_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_root = base / "target"
            target_root.mkdir()
            source_dir = make_skill(source_root, clean=True)
            source_md = source_dir / "SKILL.md"
            expected_hash = compute_skill_md_hash(source_md)
            skill = Skill(id="pdf", name="pdf", path=str(source_md))
            manager = make_manager(base, source_root, target_root)
            installer = manager.installer
            copy_payload = installer.copy_skill_md_to_temp

            def copy_then_change_source(source, temp_path):
                staged = copy_payload(source, temp_path)
                source_md.write_text(
                    "---\nname: pdf\ndescription: Changed while staging\n---\n",
                    encoding="utf-8",
                )
                return staged

            installer.copy_skill_md_to_temp = copy_then_change_source  # type: ignore[method-assign]
            result = manager.sync(
                skill,
                "trae",
                {"expected_skill_md_hash": expected_hash},
            )

            self.assertEqual(result["status"], "failed")
            self.assertIn("hash mismatch", result["reason"].casefold())
            self.assertFalse((target_root / "pdf").exists())

    def test_async_sync_without_preview_hash_pins_source_before_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_root = base / "target"
            target_root.mkdir()
            source_dir = make_skill(source_root, clean=True)
            source_md = source_dir / "SKILL.md"
            skill = Skill(id="pdf", name="pdf", path=str(source_md))
            manager = make_manager(base, source_root, target_root)
            installer = manager.installer
            copy_payload = installer.copy_skill_md_to_temp
            copy_started = threading.Event()
            allow_copy = threading.Event()

            def wait_then_copy(source, temp_path):
                copy_started.set()
                if not allow_copy.wait(timeout=5):
                    raise RuntimeError("timed out waiting for test to release staging")
                return copy_payload(source, temp_path)

            installer.copy_skill_md_to_temp = wait_then_copy  # type: ignore[method-assign]
            result = manager.start_sync(skill, "trae", {})
            self.assertEqual(result["status"], "started")
            self.assertTrue(copy_started.wait(timeout=2))

            # Revoke consent after preflight, while the background transaction is
            # paused immediately before it reads the source SKILL.md.
            source_md.write_text(
                "---\nname: pdf\ndescription: Revoked\nmetadata:\n  skillbridge-sync: deny\n---\n",
                encoding="utf-8",
            )
            allow_copy.set()

            transaction = None
            for _ in range(100):
                transaction = manager.get_transaction(result["transaction_id"])
                if transaction and transaction["status"] in {"success", "failed"}:
                    break
                time.sleep(0.02)

            self.assertIsNotNone(transaction)
            self.assertEqual(transaction["status"], "failed")
            self.assertFalse((target_root / "pdf").exists())

    def test_sync_installs_validated_bytes_if_staging_path_changes_after_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_root = base / "target"
            target_root.mkdir()
            source_dir = make_skill(source_root, clean=True)
            source_md = source_dir / "SKILL.md"
            expected_hash = compute_skill_md_hash(source_md)
            skill = Skill(id="pdf", name="pdf", path=str(source_md))
            manager = make_manager(base, source_root, target_root)
            validate_temp = manager._validate_temp

            def validate_then_tamper(source, temp_dir, expected_hash=""):
                result = validate_temp(source, temp_dir, expected_hash)
                if result["ok"]:
                    (temp_dir / "SKILL.md").write_text(
                        "---\nname: pdf\ndescription: Tampered after validation\n---\n",
                        encoding="utf-8",
                    )
                return result

            manager._validate_temp = validate_then_tamper  # type: ignore[method-assign]
            result = manager.sync(skill, "trae", {})

            self.assertEqual(result["status"], "success")
            self.assertEqual(compute_skill_md_hash(target_root / "pdf" / "SKILL.md"), expected_hash)
            self.assertNotIn(
                "Tampered after validation",
                (target_root / "pdf" / "SKILL.md").read_text(encoding="utf-8"),
            )

    def test_same_hash_returns_already_installed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_root = base / "target"
            source_dir = make_skill(source_root, clean=True)
            target_dir = make_skill(target_root, clean=True)
            # Make target identical.
            (target_dir / "SKILL.md").write_text(
                (source_dir / "SKILL.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            cache = CacheManager(base / "cache")
            skill = Skill(
                id="pdf",
                name="pdf",
                path=str(source_dir / "SKILL.md"),
                hash=cache.compute_skill_hash(source_dir),
            )
            manager = make_manager(base, source_root, target_root)
            result = manager.sync(skill, "trae", {})
            self.assertEqual(result["status"], "already_installed")

    def test_different_hash_returns_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_root = base / "target"
            source_dir = make_skill(source_root, "pdf", "Source version", clean=True)
            make_skill(target_root, "pdf", "Target different version", clean=True)
            cache = CacheManager(base / "cache")
            skill = Skill(
                id="pdf",
                name="pdf",
                path=str(source_dir / "SKILL.md"),
                hash=cache.compute_skill_hash(source_dir),
            )
            manager = make_manager(base, source_root, target_root)
            result = manager.sync(skill, "trae", {"confirm_warning": True})
            self.assertEqual(result["status"], "conflict")

    def test_copy_failure_triggers_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_root = base / "target"
            target_root.mkdir()
            source_dir = make_skill(source_root, clean=True)
            cache = CacheManager(base / "cache")
            skill = Skill(
                id="pdf",
                name="pdf",
                path=str(source_dir / "SKILL.md"),
                hash=cache.compute_skill_hash(source_dir),
            )
            manager = make_manager(base, source_root, target_root)
            installer = manager.installer

            def boom(source, temp_path):
                raise RuntimeError("simulated copy failure")

            installer.copy_skill_md_to_temp = boom  # type: ignore[method-assign]
            result = manager.sync(skill, "trae", {})
            self.assertEqual(result["status"], "failed")
            self.assertIn("simulated copy failure", result["reason"])
            self.assertFalse((target_root / "pdf").exists())
            tmp_root = base / "tmp"
            if tmp_root.exists():
                self.assertEqual(list(tmp_root.iterdir()), [])

    def test_unknown_source_does_not_require_author_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_root = base / "target"
            target_root.mkdir()
            source_dir = make_skill(source_root)  # unknown origin is not a compatibility failure
            cache = CacheManager(base / "cache")
            skill = Skill(
                id="pdf",
                name="pdf",
                path=str(source_dir / "SKILL.md"),
                hash=cache.compute_skill_hash(source_dir),
            )
            manager = make_manager(base, source_root, target_root)
            result = manager.sync(skill, "trae", {})
            self.assertEqual(result["status"], "success")
            self.assertFalse(result.get("warnings"))
            self.assertTrue((target_root / "pdf" / "SKILL.md").is_file())

    def test_warn_confirmed_can_sync(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            target_root = base / "target"
            target_root.mkdir()
            source_dir = make_skill(source_root)
            cache = CacheManager(base / "cache")
            skill = Skill(
                id="pdf",
                name="pdf",
                path=str(source_dir / "SKILL.md"),
                hash=cache.compute_skill_hash(source_dir),
            )
            manager = make_manager(base, source_root, target_root)
            result = manager.sync(skill, "trae", {"confirm_warning": True})
            self.assertEqual(result["status"], "success")
            self.assertTrue((target_root / "pdf" / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
