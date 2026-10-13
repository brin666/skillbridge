"""Plan safe, bidirectional Skill completion across selected Harnesses."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from ..adapters.base import AgentAdapter
from ..models.preflight import CheckResult
from ..models.skill import Skill
from .hash_utils import compute_skill_md_hash
from .preflight import PreflightChecker


@dataclass
class MutualSyncEntry:
    skill_id: str
    skill_name: str
    source_agent: str
    target_agent: str
    status: str
    message: str
    skill_description: str = ""
    checks: list[CheckResult] = field(default_factory=list)
    source_skill: Skill | None = field(default=None, repr=False)
    source_hash: str = ""
    compatibility_status: str = "unknown"
    compatibility_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "skillId": self.skill_id,
            "skillName": self.skill_name,
            "skillDescription": self.skill_description,
            "sourceAgent": self.source_agent,
            "targetAgent": self.target_agent,
            "status": self.status,
            "message": self.message,
            "compatibilityStatus": self.compatibility_status,
            "compatibilityNotes": list(self.compatibility_notes),
            "checks": [check.to_dict() for check in self.checks],
        }


@dataclass
class MutualSyncPlan:
    agents: list[str]
    entries: list[MutualSyncEntry]
    plan_id: str = ""
    inventory_hash: str = ""

    @property
    def ready_entries(self) -> list[MutualSyncEntry]:
        return [entry for entry in self.entries if entry.status == "ready"]

    def to_dict(self) -> dict:
        summary = {
            "ready": 0,
            "review": 0,
            "blocked": 0,
            "conflicts": 0,
            "alreadySynced": 0,
            "compatibility": {
                "compatible": 0,
                "review": 0,
                "incompatible": 0,
                "unknown": 0,
            },
        }
        for entry in self.entries:
            key = {
                "ready": "ready",
                "review": "review",
                "blocked": "blocked",
                "conflict": "conflicts",
                "same": "alreadySynced",
            }.get(entry.status)
            if key:
                summary[key] += 1
            if entry.target_agent and entry.status not in {"conflict", "same"}:
                compatibility = entry.compatibility_status
                if compatibility in summary["compatibility"]:
                    summary["compatibility"][compatibility] += 1
        return {
            "planId": self.plan_id,
            "agents": list(self.agents),
            "summary": summary,
            "items": [entry.to_dict() for entry in self.entries],
        }


class MutualSyncPlanner:
    """Use static preflight results to find safe missing Skill copies."""

    def __init__(self, adapters: list[AgentAdapter], preflight: PreflightChecker) -> None:
        self.adapters = {adapter.agent_id: adapter for adapter in adapters}
        self.preflight = preflight

    def build(
        self,
        agent_ids: list[str],
        skills_by_agent: dict[str, list[Skill]],
    ) -> MutualSyncPlan:
        selected = list(dict.fromkeys(agent_ids))
        entries: list[MutualSyncEntry] = []
        indexed: dict[str, dict[str, list[tuple[Skill, str]]]] = {agent_id: {} for agent_id in selected}
        inventory: list[tuple[str, str, str]] = []
        for agent_id in selected:
            for skill in skills_by_agent.get(agent_id, []):
                if not skill.id:
                    continue
                skill_id = skill.id.casefold()
                digest = compute_skill_md_hash(skill.path)
                indexed[agent_id].setdefault(skill_id, []).append((skill, digest))
                inventory.append((agent_id, skill_id, digest))
        skill_ids = sorted({skill_id for by_id in indexed.values() for skill_id in by_id})

        for skill_id in skill_ids:
            copies: dict[str, dict[str, Skill]] = {}
            for agent_id in selected:
                for skill, digest in indexed[agent_id].get(skill_id, []):
                    copies.setdefault(digest, {})[agent_id] = skill

            variants = [(digest, by_agent) for digest, by_agent in copies.items() if digest]
            all_agents = sorted({agent for _, by_agent in variants for agent in by_agent})
            representative = next(iter(variants[0][1].values()), None) if variants else None
            name = representative.display_name or representative.name if representative else skill_id

            if len(variants) > 1 or not variants:
                conflict_checks = [
                    CheckResult(
                        "version-conflict",
                        "block",
                        f"{agent_id}: {skill.path} (SHA-256 {digest[:12]})",
                        {"agent": agent_id, "path": skill.path, "sha256": digest},
                    )
                    for digest, by_agent in variants
                    for agent_id, skill in sorted(by_agent.items())
                ]
                entries.append(
                    MutualSyncEntry(
                        skill_id=skill_id,
                        skill_name=name,
                        source_agent=", ".join(all_agents),
                        target_agent="",
                        status="conflict" if variants else "blocked",
                        message=(
                            "Different SKILL.md versions are installed across the selected Harnesses; nothing was overwritten"
                            if variants
                            else "Could not read SKILL.md content"
                        ),
                        skill_description=representative.description if representative else "",
                        checks=conflict_checks,
                        source_hash=hashlib.sha256(
                            "\0".join(sorted(digest for digest, _ in variants)).encode("utf-8")
                        ).hexdigest() if variants else "",
                    )
                )
                continue

            digest, by_agent = variants[0]
            source_agent = min(
                by_agent,
                key=lambda agent_id: (
                    by_agent[agent_id].source.get("type", "unknown") == "unknown",
                    agent_id,
                ),
            )
            source_skill = by_agent[source_agent]
            added_target = False
            for target_agent in selected:
                existing = indexed[target_agent].get(skill_id, [])
                if existing:
                    if all(existing_hash == digest for _, existing_hash in existing):
                        continue
                    entries.append(
                        MutualSyncEntry(
                            skill_id=skill_id,
                            skill_name=name,
                        source_agent=source_agent,
                        target_agent=target_agent,
                        status="conflict",
                        message="Target already has a different SKILL.md; it was left unchanged",
                            skill_description=source_skill.description,
                        checks=[
                            CheckResult(
                                "target-version-conflict",
                                "block",
                                f"{target_agent}: {existing_skill.path} (SHA-256 {existing_hash[:12]})",
                                {"agent": target_agent, "path": existing_skill.path, "sha256": existing_hash},
                            )
                            for existing_skill, existing_hash in existing
                        ],
                            source_hash=digest,
                        )
                    )
                    continue

                added_target = True
                # The full selected-Harness inventory above already proves this
                # Skill ID is absent from the target, avoiding a repeated deep walk.
                preflight = self.preflight.check(
                    source_skill,
                    target_agent,
                    target_inventory_checked=True,
                )
                status = {
                    "pass": "ready",
                    "warn": "review",
                    "block": "blocked",
                }[preflight.status]
                compatibility = preflight.technical_compatibility
                messages = preflight.warnings if status == "review" else preflight.errors
                entries.append(
                    MutualSyncEntry(
                        skill_id=skill_id,
                        skill_name=name,
                        source_agent=source_agent,
                        target_agent=target_agent,
                        status=status,
                        message="; ".join(messages) if messages else preflight.summary,
                        skill_description=source_skill.description,
                        checks=preflight.checks,
                        source_skill=source_skill if status == "ready" else None,
                        source_hash=digest,
                        compatibility_status=compatibility["status"],
                        compatibility_notes=compatibility["notes"],
                    )
                )

            if not added_target and not any(
                entry.skill_id == skill_id and entry.status == "conflict" for entry in entries
            ):
                entries.append(
                    MutualSyncEntry(
                        skill_id=skill_id,
                        skill_name=name,
                        source_agent=source_agent,
                        target_agent="",
                        status="same",
                        message="This Skill already exists in all selected Harnesses",
                        skill_description=source_skill.description,
                        source_hash=digest,
                    )
                )

        entries.sort(key=lambda entry: (entry.skill_name.casefold(), entry.target_agent.casefold()))
        inventory_hasher = hashlib.sha256()
        for agent_id, skill_id, digest in sorted(inventory):
            inventory_hasher.update(json.dumps((agent_id, skill_id, digest), separators=(",", ":")).encode("utf-8"))
            inventory_hasher.update(b"\0")
        return MutualSyncPlan(
            agents=selected,
            entries=entries,
            inventory_hash=inventory_hasher.hexdigest(),
        )
