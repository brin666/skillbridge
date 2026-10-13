"""Observable background sync, using isolated Codex/Hermes Skill roots."""

from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.api.skills import SkillsAPI
from backend.core.agent_scanner import AgentScanner
from backend.core.cache_manager import CacheManager
from backend.core.installer import Installer
from backend.core.library_manager import LibraryManager
from backend.core.preflight import PreflightChecker
from backend.core.rollback import RollbackManager
from backend.core.skill_scanner import SkillScanner
from backend.core.sync_history import SyncHistoryManager
from backend.core.sync_manager import SyncManager
from backend.models.sync import SyncTransaction
from tests.test_mutual_sync_api import FakeAdapter


class SyncJobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.source = self.base / "codex"
        self.target = self.base / "hermes"
        self.source.mkdir()
        self.target.mkdir()
        adapters = [FakeAdapter("codex", self.source), FakeAdapter("hermes", self.target)]
        cache = CacheManager(self.base / "cache")
        self.manager = SyncManager(
            preflight_checker=PreflightChecker(adapters=adapters, cache_manager=cache),
            installer=Installer(tmp_root=self.base / "tmp"),
            rollback_manager=RollbackManager(state_root=self.base / "state"),
            cache_manager=cache,
        )
        self.api = SkillsAPI(
            agent_scanner=AgentScanner(adapters=adapters),
            skill_scanner=SkillScanner(cache_manager=cache), sync_manager=self.manager,
            library_manager=LibraryManager(library_root=self.base / "library", trash_root=self.base / "trash"),
        )

    def tearDown(self):
        self.tmp.cleanup()

    def skills(self, count=2):
        for index in range(count):
            root = self.source / f"portable-{index}"
            root.mkdir()
            (root / "SKILL.md").write_text(
                f"---\nname: portable-{index}\ndescription: Summarize local notes.\n---\nWrite a concise summary.\n",
                encoding="utf-8",
            )
        return self.api.plan_mutual_sync(["codex", "hermes"])

    def wait_done(self, job_id):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            job = self.api.get_mutual_sync_job(job_id)
            if job["status"] != "running":
                return job
            time.sleep(0.01)
        self.fail("Sync job did not finish")

    def test_start_returns_before_revalidation_and_still_checks_new_conflicts(self):
        plan = self.skills()
        entered, release = threading.Event(), threading.Event()
        build = self.api._build_mutual_sync_plan

        def blocked_build(selected):
            entered.set()
            release.wait(5)
            return build(selected)

        with patch.object(self.api, "_build_mutual_sync_plan", side_effect=blocked_build):
            try:
                started = time.monotonic()
                job = self.api.start_mutual_sync(["codex", "hermes"], plan["planId"], background=True)
                self.assertLess(time.monotonic() - started, 0.5)
                self.assertTrue(entered.wait(1))
                self.assertEqual(self.api.get_mutual_sync_job(job["id"])["phase"], "validating")
                conflict = self.target / "portable-0"
                conflict.mkdir()
                (conflict / "SKILL.md").write_text("---\nname: portable-0\ndescription: Keep my version.\n---\n", encoding="utf-8")
            finally:
                release.set()
            final = self.wait_done(job["id"])
        self.assertEqual(final["status"], "failed")
        self.assertEqual(final["code"], "PLAN_STALE")
        self.assertIn("Keep my version", (conflict / "SKILL.md").read_text(encoding="utf-8"))
        self.assertFalse((self.target / "portable-1").exists())

    def test_running_progress_survives_repeated_reads_and_finishes(self):
        plan = self.skills()
        entered, release = threading.Event(), threading.Event()
        copy = self.manager.installer.copy_skill_md_to_temp

        def slow_copy(source, destination):
            entered.set()
            release.wait(5)
            return copy(source, destination)

        with patch.object(self.manager.installer, "copy_skill_md_to_temp", side_effect=slow_copy), patch.object(self.api, "rescan", wraps=self.api.rescan) as scan:
            try:
                job = self.api.start_mutual_sync(["codex", "hermes"], plan["planId"], background=True)
                self.assertTrue(entered.wait(2))
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    running = self.api.get_mutual_sync_job(job["id"])
                    if any(task["status"] == "running" and task["progress"] >= 35 for task in running["tasks"]):
                        break
                    time.sleep(0.02)
                self.assertTrue(any(task["status"] == "running" and task["progress"] >= 35 for task in running["tasks"]))
                self.assertEqual(running["status"], "running")
                self.assertEqual(self.api.get_mutual_sync_job(job["id"])["id"], job["id"])
            finally:
                release.set()
                final = self.wait_done(job["id"])
            self.assertEqual(scan.call_count, 1)
        self.assertEqual(final["status"], "success")
        self.assertEqual(len(final["tasks"]), 2)
        for task in final["tasks"]:
            self.assertEqual(task["status"], "success")
            self.assertEqual(task["progress"], 100)
            self.assertEqual((self.source / task["skillId"] / "SKILL.md").read_bytes(), (self.target / task["skillId"] / "SKILL.md").read_bytes())

    def test_launch_exception_is_visible_in_result(self):
        plan = self.skills(1)
        with patch.object(self.manager, "start_sync", side_effect=OSError("disk unavailable")):
            job = self.api.start_mutual_sync(["codex", "hermes"], plan["planId"], background=True)
            final = self.wait_done(job["id"])
        self.assertEqual(final["status"], "failed")
        self.assertEqual(final["tasks"][0]["status"], "failed")
        self.assertIn("disk unavailable", final["tasks"][0]["message"])

    def test_batch_limits_concurrent_writes(self):
        plan = self.skills(5)
        all_three, release = threading.Event(), threading.Event()
        lock = threading.Lock()
        entered = []
        copy = self.manager.installer.copy_skill_md_to_temp

        def held_copy(source, destination):
            with lock:
                entered.append(source)
                if len(entered) == 3:
                    all_three.set()
            release.wait(5)
            return copy(source, destination)

        with patch.object(self.manager.installer, "copy_skill_md_to_temp", side_effect=held_copy):
            try:
                job = self.api.start_mutual_sync(["codex", "hermes"], plan["planId"], background=True)
                self.assertTrue(all_three.wait(2))
                time.sleep(0.2)
                self.assertEqual(len(entered), 3)
            finally:
                release.set()
            final = self.wait_done(job["id"])
        self.assertEqual(final["status"], "success")
        self.assertEqual(len(entered), 5)

    def test_history_is_readable_while_next_state_is_staged(self):
        history = SyncHistoryManager(self.base / "history")
        other_reader = SyncHistoryManager(self.base / "history")
        transaction = SyncTransaction(id="atomic", skill="demo", target_agent="hermes", progress=5)
        history.create(transaction)
        entered, release = threading.Event(), threading.Event()
        replace = os.replace

        def held_replace(source, destination):
            entered.set()
            release.wait(3)
            return replace(source, destination)

        transaction.progress = 85
        with patch("backend.core.sync_history.os.replace", side_effect=held_replace):
            worker = threading.Thread(target=history.update, args=(transaction,))
            worker.start()
            try:
                self.assertTrue(entered.wait(1))
                self.assertEqual(other_reader.get("atomic").progress, 5)
            finally:
                release.set()
                worker.join(3)
        self.assertEqual(history.get("atomic").progress, 85)
        self.assertFalse(list(history.history_dir.glob("*.tmp")))

    def test_lost_start_response_can_be_retried_without_duplicate_writes(self):
        plan = self.skills(1)
        request_id = "a" * 32
        entered, release = threading.Event(), threading.Event()
        copy = self.manager.installer.copy_skill_md_to_temp

        def held_copy(source, destination):
            entered.set()
            release.wait(5)
            return copy(source, destination)

        with patch.object(self.manager.installer, "copy_skill_md_to_temp", side_effect=held_copy) as copying:
            try:
                job = self.api.start_mutual_sync(["codex", "hermes"], plan["planId"], background=True, request_id=request_id)
                self.assertTrue(entered.wait(2))
                retried = self.api.start_mutual_sync(["codex", "hermes"], plan["planId"], background=True, request_id=request_id)
                self.assertEqual(retried["id"], job["id"])
                self.assertEqual(copying.call_count, 1)
                mismatch = self.api.start_mutual_sync(["codex", "hermes"], "other-plan", background=True, request_id=request_id)
                self.assertEqual(mismatch["code"], "SYNC_REQUEST_MISMATCH")
            finally:
                release.set()
            final = self.wait_done(job["id"])
        self.assertEqual(final["status"], "success")

    def test_batch_result_is_persisted_and_interruption_is_explicit(self):
        plan = self.skills()
        job = self.api.start_mutual_sync(["codex", "hermes"], plan["planId"], background=True)
        final = self.wait_done(job["id"])

        def reopened():
            return SkillsAPI(
                agent_scanner=self.api.agent_scanner, skill_scanner=self.api.skill_scanner,
                sync_manager=self.manager, library_manager=self.api.library_manager,
            )

        recovered = reopened().get_mutual_sync_job(job["id"])
        self.assertEqual(recovered, final)
        final.update(status="running", phase="syncing")
        final.pop("endedAt", None)
        final["tasks"][0]["status"] = "running"  # reconcile its durable completed tx
        final["tasks"][1].update(status="queued", transaction_id=None)
        self.api._mutual_sync_job_store.save(final)
        interrupted = reopened().get_mutual_sync_job(job["id"])
        self.assertEqual(interrupted["status"], "failed")
        self.assertEqual(interrupted["code"], "SYNC_INTERRUPTED")
        self.assertEqual(interrupted["tasks"][0]["status"], "success")
        self.assertEqual(interrupted["tasks"][1]["status"], "interrupted")

    def test_permanently_missing_status_has_bounded_unknown_result(self):
        plan = self.skills(5)
        self.api._sync_status_retry_seconds = 0.04
        with patch.object(self.manager, "start_sync", return_value={"status": "started", "transaction_id": "missing"}) as start, patch.object(self.manager, "get_transaction", return_value=None):
            job = self.api.start_mutual_sync(["codex", "hermes"], plan["planId"], background=True)
            final = self.wait_done(job["id"])
        self.assertEqual(final["status"], "failed")
        self.assertEqual(final["code"], "SYNC_STATUS_LOST")
        self.assertLessEqual(start.call_count, 3)
        self.assertTrue(any(task["status"] == "unknown" for task in final["tasks"]))
        self.assertTrue(any(task["status"] == "skipped" for task in final["tasks"]))

    def test_live_results_do_not_require_readable_history(self):
        plan = self.skills(1)
        with patch.object(self.manager.history, "get", return_value=None):
            job = self.api.start_mutual_sync(["codex", "hermes"], plan["planId"], background=True)
            final = self.wait_done(job["id"])
        self.assertEqual(final["status"], "success")
        tx = self.manager.get_transaction(final["tasks"][0]["transaction_id"])
        self.assertEqual(tx["status"], "success")

    def test_history_write_failure_is_visible_not_running_forever(self):
        plan = self.skills(1)
        with patch.object(self.manager.history, "update", side_effect=OSError("history permission denied")):
            job = self.api.start_mutual_sync(["codex", "hermes"], plan["planId"], background=True)
            final = self.wait_done(job["id"])
        self.assertEqual(final["status"], "failed")
        self.assertEqual(final["tasks"][0]["status"], "failed")
        self.assertIn("history permission denied", final["tasks"][0]["message"])

    def test_request_id_cannot_escape_history_directory(self):
        plan = self.skills(1)
        result = self.api.start_mutual_sync(["codex", "hermes"], plan["planId"], background=True, request_id="../escape")
        self.assertEqual(result["code"], "SYNC_REQUEST_INVALID")
        self.assertFalse(list(self.target.iterdir()))


if __name__ == "__main__":
    unittest.main()
