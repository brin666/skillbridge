"""Environment API helpers."""

from __future__ import annotations

from .skills import _get_api


def get_environment() -> dict:
    """Return a high-level environment summary from the current scan."""
    api = _get_api()
    agents = api.list_agents()
    skills = api.list_skills()
    return {
        "health": 100 if agents else 0,
        "agentCount": len([a for a in agents if a.get("installed")]),
        "skillCount": len(skills),
        "unsyncedCount": 0,
        "issueCount": 0,
    }
