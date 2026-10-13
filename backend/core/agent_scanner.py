"""Windows-first Agent Scanner.

The scanner is deliberately adapter-driven: it does not contain any
agent-specific path or command knowledge. Every agent is represented by an
independent :class:`~backend.adapters.base.AgentAdapter`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from ..adapters.base import AgentAdapter
from ..adapters import (
    CodeBuddyAdapter,
    CodexAdapter,
    ClaudeAdapter,
    DSHAdapter,
    HermesAdapter,
    LingmaAdapter,
    QwenAdapter,
    TraeAdapter,
)
from ..models.agent import Agent
from ..models.environment import EnvironmentSummary

DEFAULT_ADAPTER_CLASSES: tuple[type[AgentAdapter], ...] = (
    CodexAdapter,
    ClaudeAdapter,
    QwenAdapter,
    TraeAdapter,
    CodeBuddyAdapter,
    LingmaAdapter,
    HermesAdapter,
    DSHAdapter,
)


class AgentScanner:
    """Scan this machine for supported AI Agents and their Skill roots."""

    def __init__(
        self,
        adapters: Iterable[AgentAdapter] | None = None,
        project_dir: str | Path | None = None,
    ) -> None:
        if adapters is None:
            resolved_project = Path(project_dir or Path.cwd()).resolve()
            adapters = [cls(project_dir=resolved_project) for cls in DEFAULT_ADAPTER_CLASSES]
        self.adapters = list(adapters)

    def scan(self, include_skills: bool = False) -> list[Agent]:
        """Scan all adapters and return a unified Agent list.

        Args:
            include_skills: include discovered Skill objects on each Agent.
                The public JSON API normally does not need this.
        """
        agents: list[Agent] = []
        for adapter in self.adapters:
            adapter.refresh_version_cache()
            installed = adapter.detect()
            skill_paths = adapter.get_skill_paths()
            skills = adapter.scan_skills() if installed else []
            version = adapter.get_version() if installed else None
            agents.append(
                Agent(
                    id=adapter.agent_id,
                    name=adapter.get_name(),
                    installed=installed,
                    version=version,
                    skill_count=len(skills),
                    skill_paths=skill_paths,
                    skills=skills if include_skills else [],
                )
            )
        return agents

    def scan_environment(self, include_skills: bool = False) -> EnvironmentSummary:
        """Return a high-level environment summary.

        Phase 1 only populates agent and skill counts. Health/issue metrics
        arrive with the full parser and preflight phases.
        """
        agents = self.scan(include_skills=True)
        skill_count = len({skill.id for agent in agents for skill in agent.skills})
        if not include_skills:
            for agent in agents:
                agent.skills = []
        return EnvironmentSummary(
            health=100 if any(a.installed for a in agents) else 0,
            agent_count=len([a for a in agents if a.installed]),
            skill_count=skill_count,
            agents=agents,
        )


def default_scanner() -> AgentScanner:
    """Convenience factory for a default scanner."""
    return AgentScanner()
