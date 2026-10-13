#!/usr/bin/env python3
"""SkillBridge command line entry point.

Phase 3 commands:

    python backend/main.py dashboard
    python backend/main.py scan [--json]
    python backend/main.py server
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make stdout UTF-8 on Windows consoles for Chinese skill names.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Allow both `python backend/main.py` and `python -m backend.main`.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.api.skills import SkillsAPI
from backend.core.cache_manager import CacheManager
from backend.core.skill_scanner import SkillScanner
from backend.server import run_server


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skillbridge",
        description="SkillBridge local-first AI Skills control center.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    dashboard = subparsers.add_parser("dashboard", help="Start the local Dashboard and open the browser.")
    dashboard.add_argument("--json", action="store_true", help="Print a JSON summary and exit (no server).")
    dashboard.add_argument(
        "--cache-dir",
        type=str,
        default=None,
        help="Override the Skill cache directory.",
    )

    scan = subparsers.add_parser("scan", help="Scan Agents and Skills.")
    scan.add_argument("--json", action="store_true", help="Output JSON result.")
    scan.add_argument(
        "--project-dir",
        type=str,
        default=None,
        help="Also scan project-local skill roots under this directory.",
    )
    scan.add_argument(
        "--cache-dir",
        type=str,
        default=None,
        help="Override the Skill cache directory.",
    )

    server = subparsers.add_parser("server", help="Start the localhost JSON API server.")
    server.add_argument("--port", type=int, default=None, help="Preferred port (default 17321).")
    server.add_argument(
        "--cache-dir",
        type=str,
        default=None,
        help="Override the Skill cache directory.",
    )
    return parser


def _make_api(project_dir: str | None, cache_dir: str | None) -> SkillsAPI:
    from backend.core.agent_scanner import AgentScanner

    agent_scanner = AgentScanner(project_dir=project_dir)
    cache = CacheManager(cache_dir) if cache_dir else CacheManager()
    skill_scanner = SkillScanner(cache_manager=cache)
    return SkillsAPI(agent_scanner=agent_scanner, skill_scanner=skill_scanner)


def _print_dashboard(api: SkillsAPI, json_output: bool) -> int:
    data = api.rescan()
    if json_output:
        print(json.dumps(
            {
                "health": 100 if data["agents"] else 0,
                "agentCount": data["agents"],
                "skillCount": data["skills"],
                "unsyncedCount": 0,
                "issueCount": 0,
            },
            ensure_ascii=False,
            indent=2,
        ))
        return 0

    print("SkillBridge V0.1 - Phase 2")
    print("=" * 50)
    print(f"Detected Agents : {data['agents']}")
    print(f"Discovered Skills: {data['skills']}")
    print()
    for agent in data["agentList"]:
        status = "detected" if agent["installed"] else "not found"
        print(f"  {agent['name']:<22} {status:<10} skills={agent['skillCount']}")
    return 0


def _print_scan(api: SkillsAPI, json_output: bool) -> int:
    data = api.rescan()
    if json_output:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    print(f"Agents detected : {data['agents']}")
    print(f"Skills discovered: {data['skills']}")
    print()
    print("Agents:")
    for agent in data["agentList"]:
        status = "detected" if agent["installed"] else "not found"
        print(f"  {agent['name']:<24}{status:<12}skills={agent['skillCount']}")
    print()
    print("Skills:")
    for skill in data["skillList"]:
        source_type = skill.get("source", {}).get("type", "unknown")
        agents = ", ".join(skill.get("installedAgents", [])) or "-"
        print(f"  {skill.get('displayName') or skill.get('name'):<28}{source_type:<10}{agents}")
        if skill.get("path"):
            print(f"    {skill['path']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "dashboard":
        if args.json:
            api = _make_api(None, args.cache_dir)
            return _print_dashboard(api, True)
        api = _make_api(None, args.cache_dir) if args.cache_dir else None
        run_server(open_browser=True, api=api)
        return 0

    if args.command == "scan":
        project_dir = Path(args.project_dir).resolve() if args.project_dir else None
        api = _make_api(project_dir, args.cache_dir)
        return _print_scan(api, args.json)

    if args.command == "server":
        api = _make_api(None, args.cache_dir) if args.cache_dir else None
        run_server(port=args.port, api=api)
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
