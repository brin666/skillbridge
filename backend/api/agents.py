"""Agents API helpers."""

from __future__ import annotations

from .skills import _get_api


def list_agents() -> list[dict]:
    return _get_api().list_agents()


def get_agent(agent_id: str) -> dict | None:
    for agent in _get_api().list_agents():
        if agent["id"] == agent_id:
            return agent
    return None
