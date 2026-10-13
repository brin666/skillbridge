"""Localhost server for SkillBridge.

Serves the JSON API and, when built, the prebuilt React UI from ``ui/dist``.
The server binds to ``127.0.0.1`` only.
"""

from __future__ import annotations

import json
import mimetypes
import socket
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .api.skills import SkillsAPI

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 17321
MAX_PORT_TRIES = 50
PROJECT_ROOT = Path(__file__).resolve().parents[1]
UI_DIST = PROJECT_ROOT / "ui" / "dist"


def find_available_port(host: str = DEFAULT_HOST, preferred: int = DEFAULT_PORT) -> int:
    """Return the preferred port if free, otherwise the next free port."""
    port = preferred
    for _ in range(MAX_PORT_TRIES):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
                return port
            except OSError:
                port += 1
    raise RuntimeError(f"No available port found near {preferred}")


class SkillBridgeRequestHandler(BaseHTTPRequestHandler):
    """Serves SkillBridge JSON API and static UI files."""

    server_version = "SkillBridge/0.1"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path.rstrip("/") or "/")

        try:
            if path.startswith("/api/"):
                self._handle_api(path)
            else:
                self._serve_static(path)
        except Exception as exc:  # pragma: no cover - defensive API error
            self._send_json({"error": str(exc)}, status=500)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path.rstrip("/") or "/")

        try:
            if path == "/api/skills":
                self._send_json({"error": "method not allowed"}, status=405)
            elif path == "/api/library/import":
                payload = self._read_json_body()
                skill_id = payload.get("skill_id") or payload.get("skillId")
                source_agent = payload.get("source_agent") or payload.get("sourceAgent")
                if not skill_id or not source_agent:
                    self._send_json({"error": "skill_id and source_agent are required"}, status=400)
                else:
                    self._send_json(self.server.api.import_library_skill(skill_id, source_agent))
            elif path == "/api/sync/mutual/plan":
                payload = self._read_json_body()
                agents = payload.get("agents")
                agent_ids = list(dict.fromkeys(item.strip() for item in agents if isinstance(item, str) and item.strip())) if isinstance(agents, list) else []
                if len(agent_ids) < 2:
                    self._send_json({"code": "AGENTS_REQUIRED", "message": "Select at least two installed Harnesses"}, status=400)
                else:
                    self._send_json(self.server.api.plan_mutual_sync(agent_ids))
            elif path == "/api/sync/mutual":
                payload = self._read_json_body()
                agents = payload.get("agents")
                agent_ids = list(dict.fromkeys(item.strip() for item in agents if isinstance(item, str) and item.strip())) if isinstance(agents, list) else []
                if len(agent_ids) < 2:
                    self._send_json({"code": "AGENTS_REQUIRED", "message": "Select at least two installed Harnesses"}, status=400)
                else:
                    plan_id = payload.get("plan_id") or payload.get("planId")
                    if payload.get("background") is True:
                        result = self.server.api.start_mutual_sync(
                            agent_ids, str(plan_id or ""), background=True,
                            request_id=str(payload.get("request_id") or "") or None,
                        )
                    else:
                        result = self.server.api.start_mutual_sync(agent_ids, str(plan_id or ""))
                    status = 409 if result.get("code") and not result.get("id") else 200
                    self._send_json(result, status=status)
            elif path.startswith("/api/library/skills/") and path.endswith("/deploy"):
                skill_id = path[len("/api/library/skills/"):-len("/deploy")]
                payload = self._read_json_body()
                targets = payload.get("targets") or payload.get("targetAgents")
                if not isinstance(targets, list) or not targets:
                    self._send_json({"code": "TARGETS_REQUIRED", "message": "Targets are required"}, status=400)
                else:
                    confirm_warning = bool(payload.get("confirm_warning") or payload.get("confirmWarning"))
                    force_replace = bool(payload.get("force_replace") or payload.get("forceReplace"))
                    self._send_json(
                        self.server.api.deploy_library_skill(
                            skill_id,
                            [str(t) for t in targets],
                            confirm_warning=confirm_warning,
                            force_replace=force_replace,
                        )
                    )
            elif path.endswith("/preflight"):
                skill_id = self._management_skill_id(path, "/preflight")
                payload = self._read_json_body()
                target_agent = payload.get("target_agent") or payload.get("targetAgent")
                if not target_agent:
                    self._send_json({"code": "TARGET_AGENT_REQUIRED", "message": "Target Agent is required"}, status=400)
                else:
                    self._send_json(self.server.api.preflight_skill(skill_id, target_agent))
            elif path.endswith("/batch-sync"):
                skill_id = self._management_skill_id(path, "/batch-sync")
                payload = self._read_json_body()
                targets = payload.get("targets") or payload.get("targetAgents")
                if not isinstance(targets, list) or not targets:
                    self._send_json({"code": "TARGETS_REQUIRED", "message": "Targets are required"}, status=400)
                else:
                    confirm_warning = bool(payload.get("confirm_warning") or payload.get("confirmWarning"))
                    force_replace = bool(payload.get("force_replace") or payload.get("forceReplace"))
                    self._send_json(
                        self.server.api.batch_sync_skill(
                            skill_id,
                            [str(t) for t in targets],
                            confirm_warning=confirm_warning,
                            force_replace=force_replace,
                        )
                    )
            elif path.endswith("/sync"):
                skill_id = self._management_skill_id(path, "/sync")
                payload = self._read_json_body()
                target_agent = payload.get("target_agent") or payload.get("targetAgent")
                if not target_agent:
                    self._send_json({"code": "TARGET_AGENT_REQUIRED", "message": "Target Agent is required"}, status=400)
                else:
                    confirm_warning = bool(payload.get("confirm_warning") or payload.get("confirmWarning"))
                    force_replace = bool(payload.get("force_replace") or payload.get("forceReplace"))
                    self._send_json(
                        self.server.api.sync_skill(
                            skill_id,
                            target_agent,
                            confirm_warning=confirm_warning,
                            force_replace=force_replace,
                        )
                    )
            elif path.endswith("/open-folder"):
                skill_id = self._management_skill_id(path, "/open-folder")
                self._send_json(self.server.api.open_folder(skill_id))
            elif path.endswith("/open-file"):
                skill_id = self._management_skill_id(path, "/open-file")
                self._send_json(self.server.api.open_file(skill_id))
            elif path.endswith("/disable"):
                skill_id = self._management_skill_id(path, "/disable")
                self._send_json(self.server.api.disable_skill(skill_id))
            elif path.endswith("/enable"):
                skill_id = self._management_skill_id(path, "/enable")
                self._send_json(self.server.api.enable_skill(skill_id))
            else:
                self._send_json({"error": "not_found"}, status=404)
        except KeyError as exc:
            self._send_json({"error": str(exc)}, status=404)
        except ValueError as exc:
            self._send_json({"code": "INVALID_REQUEST", "message": str(exc)}, status=400)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def do_DELETE(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path.rstrip("/") or "/")

        try:
            if path.startswith("/api/library/skills/"):
                skill_id = path[len("/api/library/skills/"):]
                if "/" in skill_id:
                    self._send_json({"error": "not_found"}, status=404)
                else:
                    self._send_json(self.server.api.remove_library_skill(skill_id))
            elif path.startswith("/api/skills/"):
                skill_id = path[len("/api/skills/"):]
                if "/" in skill_id:
                    self._send_json({"error": "not_found"}, status=404)
                else:
                    self._send_json(self.server.api.uninstall_skill(skill_id))
            else:
                self._send_json({"error": "not_found"}, status=404)
        except KeyError as exc:
            self._send_json({"error": str(exc)}, status=404)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    @staticmethod
    def _management_skill_id(path: str, suffix: str) -> str:
        prefix = "/api/skills/"
        if not path.startswith(prefix) or not path.endswith(suffix):
            raise KeyError("Skill not found")
        skill_id = path[len(prefix):-len(suffix)]
        if not skill_id or "/" in skill_id:
            raise KeyError("Skill not found")
        return skill_id

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    def _handle_api(self, path: str) -> None:
        if path == "/api/skills":
            self._send_json(self.server.api.list_skills())
        elif path == "/api/rescan":
            self._send_json(self.server.api.rescan())
        elif path == "/api/agents":
            self._send_json(self.server.api.list_agents())
        elif path == "/api/environment":
            agents = self.server.api.list_agents()
            skills = self.server.api.list_skills()
            self._send_json(
                {
                    "health": 100 if agents else 0,
                    "agentCount": len([a for a in agents if a.get("installed")]),
                    "skillCount": len(skills),
                    "unsyncedCount": 0,
                    "issueCount": 0,
                }
            )
        elif path == "/api/sync/mutual/warmup":
            self._send_json(self.server.api.get_compatibility_warmup_status())
        elif path.startswith("/api/sync/mutual/jobs/"):
            job = self.server.api.get_mutual_sync_job(path[len("/api/sync/mutual/jobs/"):])
            if job is None:
                self._send_json({"code": "SYNC_JOB_NOT_FOUND", "message": "Sync batch not found"}, status=404)
            else:
                self._send_json(job)
        elif path == "/api/sync/history":
            self._send_json(self.server.api.list_sync_history())
        elif path.startswith("/api/sync/"):
            transaction_id = path[len("/api/sync/"):]
            transaction = self.server.api.get_sync_transaction(transaction_id)
            if transaction is None:
                self._send_json({"code": "TRANSACTION_NOT_FOUND", "message": "Transaction not found"}, status=404)
            else:
                self._send_json(transaction)
        elif path == "/api/library":
            self._send_json(self.server.api.list_library())
        elif path.startswith("/api/library/skills/"):
            skill_id = path[len("/api/library/skills/"):]
            library_skill = self.server.api.get_library_skill(skill_id)
            if library_skill is None:
                self._send_json({"code": "LIBRARY_SKILL_NOT_FOUND", "message": "Library Skill not found"}, status=404)
            else:
                self._send_json(library_skill)
        elif path.startswith("/api/skills/"):
            skill_id = path[len("/api/skills/"):]
            skill = self.server.api.get_skill(skill_id)
            if skill is None:
                self._send_json({"code": "SKILL_NOT_FOUND", "message": "Skill not found"}, status=404)
            else:
                self._send_json(skill)
        else:
            self._send_json({"error": "not_found"}, status=404)

    # ------------------------------------------------------------------
    # Static UI
    # ------------------------------------------------------------------
    def _serve_static(self, path: str) -> None:
        ui_dist = getattr(self.server, "ui_dir", UI_DIST).resolve()
        if not ui_dist.is_dir():
            self._send_json(
                {
                    "error": "UI not built. Run `npm run build` inside ui/ before starting dashboard.",
                },
                status=500,
            )
            return

        relative = path.lstrip("/")
        if not relative:
            relative = "index.html"

        candidate = (ui_dist / relative).resolve()
        try:
            candidate.relative_to(ui_dist)
        except ValueError:
            self._send_json({"error": "not_found"}, status=404)
            return

        if candidate.is_dir():
            candidate = candidate / "index.html"

        if candidate.is_file():
            self._send_file(candidate)
            return

        # SPA fallback: unknown client-side routes render the app shell.
        if "." not in Path(relative).name:
            index_file = ui_dist / "index.html"
            if index_file.is_file():
                self._send_file(index_file)
                return

        self._send_json({"error": "not_found"}, status=404)

    def _send_file(self, path: Path) -> None:
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, data, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:  # pragma: no cover - quiet logs
        pass


class SkillBridgeServer(ThreadingHTTPServer):
    """Localhost server with a SkillsAPI instance."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int | None = None,
        api: SkillsAPI | None = None,
        ui_dir: str | Path | None = None,
    ):
        self.host = host
        self.port = find_available_port(host, port or DEFAULT_PORT)
        self.api = api or SkillsAPI()
        self.ui_dir = Path(ui_dir or UI_DIST).resolve()
        super().__init__((self.host, self.port), SkillBridgeRequestHandler)


def run_server(
    host: str = DEFAULT_HOST,
    port: int | None = None,
    open_browser: bool = False,
    api: SkillsAPI | None = None,
) -> None:
    """Start the localhost server and block until interrupted."""
    server = SkillBridgeServer(host=host, port=port, api=api)
    warmup = getattr(server.api, "start_compatibility_warmup", None)
    if callable(warmup):
        warmup()
    url = f"http://{server.host}:{server.port}"
    print(f"SkillBridge server: {url}")
    if open_browser:
        webbrowser.open(url)
    print("API: /api/skills, /api/skills/<id>, /api/rescan, /api/agents, /api/environment")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
