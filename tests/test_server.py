"""Tests for the localhost server (API + static UI)."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.server import SkillBridgeServer, run_server


class FakeAPI:
    def list_skills(self):
        return [{"id": "pdf", "name": "pdf", "displayName": "PDF Tools"}]

    def list_agents(self):
        return [{"id": "codex", "name": "Codex", "installed": True, "skillCount": 1}]

    def rescan(self):
        return {"agents": 1, "skills": 1}

    def get_skill(self, skill_id):
        if skill_id == "pdf":
            return self.list_skills()[0]
        return None

    def plan_mutual_sync(self, agents):
        return {"planId": "reviewed-plan", "agents": agents, "summary": {"ready": 1}, "items": []}

    def start_mutual_sync(self, agents, plan_id=None):
        if not plan_id:
            return {"code": "PLAN_REQUIRED", "message": "Analyze before starting"}
        return {"plan": self.plan_mutual_sync(agents), "tasks": []}

    def get_compatibility_warmup_status(self):
        return {"status": "ready", "checkedPairs": 3, "error": None}


class ServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.ui_dir = Path(self.tmp.name) / "ui-dist"
        self.ui_dir.mkdir()
        (self.ui_dir / "index.html").write_text("<html><body>SkillBridge</body></html>", encoding="utf-8")
        self.server = SkillBridgeServer(port=18421, api=FakeAPI(), ui_dir=self.ui_dir)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        time.sleep(0.1)

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def _get(self, path: str):
        with urllib.request.urlopen(f"http://127.0.0.1:18421{path}") as response:
            return response.status, response.headers.get("Content-Type"), response.read().decode("utf-8")

    def _post(self, path: str, payload: dict):
        request = urllib.request.Request(
            f"http://127.0.0.1:18421{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_api_skills(self) -> None:
        status, content_type, body = self._get("/api/skills")
        self.assertEqual(status, 200)
        self.assertIn("application/json", content_type)
        self.assertEqual(json.loads(body)[0]["id"], "pdf")

    def test_static_index(self) -> None:
        status, content_type, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        self.assertIn("SkillBridge", body)

    def test_spa_fallback(self) -> None:
        status, _, body = self._get("/skills")
        self.assertEqual(status, 200)
        self.assertIn("SkillBridge", body)

    def test_mutual_sync_plan_endpoint(self) -> None:
        status, body = self._post("/api/sync/mutual/plan", {"agents": ["codex", "hermes"]})
        self.assertEqual(status, 200)
        self.assertEqual(body["agents"], ["codex", "hermes"])

    def test_mutual_sync_start_endpoint(self) -> None:
        status, body = self._post("/api/sync/mutual", {"agents": ["codex", "hermes"], "plan_id": "reviewed-plan"})
        self.assertEqual(status, 200)
        self.assertIn("plan", body)
        self.assertEqual(body["tasks"], [])

    def test_mutual_sync_warmup_status_endpoint(self) -> None:
        status, content_type, body = self._get("/api/sync/mutual/warmup")
        self.assertEqual(status, 200)
        self.assertIn("application/json", content_type)
        self.assertEqual(json.loads(body)["status"], "ready")

    def test_server_start_triggers_read_only_compatibility_warmup(self) -> None:
        class StartupAPI(FakeAPI):
            warmup_started = False

            def start_compatibility_warmup(self):
                self.warmup_started = True

        class StoppedServer:
            host = "127.0.0.1"
            port = 17321

            def __init__(self, api):
                self.api = api

            def serve_forever(self):
                raise KeyboardInterrupt

            def server_close(self):
                return None

        api = StartupAPI()
        server = StoppedServer(api)
        with patch("backend.server.SkillBridgeServer", return_value=server), redirect_stdout(StringIO()):
            run_server(api=api)

        self.assertTrue(api.warmup_started)

    def test_mutual_sync_start_requires_reviewed_plan(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self._post("/api/sync/mutual", {"agents": ["codex", "hermes"]})
        self.assertEqual(raised.exception.code, 409)

    def test_mutual_sync_requires_two_agents(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self._post("/api/sync/mutual/plan", {"agents": ["codex"]})
        self.assertEqual(raised.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
