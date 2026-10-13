"""Skill Scanner.

Phase 2 implementation. Scans Agent-provided Skill roots, parses SKILL.md,
detects source, generates/caches summaries, and returns unified Skill models.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from ..models.agent import Agent
from ..models.skill import Skill
from ..skill_files import find_skill_md, iter_skill_dirs
from .cache_manager import CacheManager
from .hash_utils import collect_skill_file_metadata
from .skill_parser import SkillParser
from .source_detector import SourceDetector
from .summary.manager import SUMMARY_PIPELINE_VERSION
from .summary_manager import SummaryManager


class SkillScanner:
    """Scans Skills from Adapter-provided skill paths."""

    def __init__(
        self,
        parser: SkillParser | None = None,
        source_detector: SourceDetector | None = None,
        summary_manager: SummaryManager | None = None,
        cache_manager: CacheManager | None = None,
    ) -> None:
        self.parser = parser or SkillParser()
        self.source_detector = source_detector or SourceDetector()
        self.summary_manager = summary_manager or SummaryManager()
        self.cache_manager = cache_manager

    # ------------------------------------------------------------------
    # Main entry points
    # ------------------------------------------------------------------
    def scan_agents(self, agents: Iterable[Agent]) -> list[Skill]:
        """Scan all installed Agents' Skill roots and return merged Skills.

        Disabled sibling roots (``<root>_disabled``) are included so users can
        re-enable Skills from the UI after a restart.
        """
        raw_skills: list[Skill] = []
        for agent in agents:
            if not agent.installed:
                continue
            for root in agent.skill_paths:
                raw_skills.extend(
                    self.scan_skill_paths([root], agent_id=agent.id, include_disabled=True)
                )
        return self.merge_skills(raw_skills)

    def scan_skill_paths(
        self,
        skill_paths: Iterable[str | Path],
        agent_id: str = "",
        include_disabled: bool = False,
    ) -> list[Skill]:
        """Scan a list of Skill root directories for one Agent."""
        skills: list[Skill] = []
        for root in skill_paths:
            root_path = Path(root)
            if not root_path.is_dir():
                continue
            for skill_dir in self._iter_skill_dirs(root_path, include_disabled=include_disabled):
                skill = self._scan_skill_dir(
                    skill_dir,
                    agent_id,
                    enabled=not self._is_disabled_under(skill_dir, root_path),
                )
                if skill is not None:
                    skills.append(skill)

            if include_disabled:
                disabled_root = self._disabled_root_for(root_path)
                if disabled_root.is_dir():
                    for skill_dir in self._iter_skill_dirs(disabled_root, include_disabled=True):
                        skill = self._scan_skill_dir(skill_dir, agent_id, enabled=False)
                        if skill is not None:
                            skills.append(skill)
        return skills

    def scan(self, agents: Iterable[Agent]) -> list[Skill]:
        """Alias for :meth:`scan_agents`."""
        return self.scan_agents(agents)

    # ------------------------------------------------------------------
    # Merging / de-duplication
    # ------------------------------------------------------------------
    def merge_skills(self, skills: Iterable[Skill]) -> list[Skill]:
        """Merge Skill entries that refer to the same Skill.

        Simple Phase 2 rule: two entries match when id, name, or content hash
        are equal. No AI/semantic analysis is used.
        """
        result: list[Skill] = []
        groups: list[tuple[Skill, set[str], set[str], set[str]]] = []

        for skill in skills:
            skill_id = skill.id.strip().lower()
            skill_name = skill.name.strip().lower()
            skill_hash = skill.hash.strip()

            group_index = self._find_group(
                groups, skill_id, skill_name, skill_hash
            )
            if group_index is None:
                groups.append((skill, {skill_id}, {skill_name}, {skill_hash}))
            else:
                self._merge_into_group(groups[group_index], skill)

        for rep, _, _, _ in groups:
            result.append(rep)
        return result

    def _find_group(
        self,
        groups: list[tuple[Skill, set[str], set[str], set[str]]],
        skill_id: str,
        skill_name: str,
        skill_hash: str,
    ) -> int | None:
        for index, (_, ids, names, hashes) in enumerate(groups):
            if skill_id and skill_id in ids:
                return index
            if skill_name and skill_name in names:
                return index
            if skill_hash and skill_hash in hashes:
                return index
        return None

    def _merge_into_group(
        self,
        group: tuple[Skill, set[str], set[str], set[str]],
        skill: Skill,
    ) -> None:
        rep, ids, names, hashes = group
        ids.add(skill.id.strip().lower())
        names.add(skill.name.strip().lower())
        hashes.add(skill.hash.strip())

        if not rep.description and skill.description:
            rep.description = skill.description
        if not rep.summary and skill.summary:
            rep.summary = skill.summary
        if not rep.features and skill.features:
            rep.features = {language: list(items) for language, items in skill.features.items()}
        if not rep.display_name and skill.display_name:
            rep.display_name = skill.display_name
        if not rep.category and skill.category:
            rep.category = skill.category
        if not rep.version and skill.version:
            rep.version = skill.version
        if not rep.source or rep.source.get("type") == "unknown":
            if skill.source and skill.source.get("type") != "unknown":
                rep.source = skill.source

        for tag in skill.tags:
            if tag not in rep.tags:
                rep.tags.append(tag)
        for agent in skill.installed_agents:
            if agent not in rep.installed_agents:
                rep.installed_agents.append(agent)
            rep.locations[agent] = True
        for agent, info in skill.installed_locations.items():
            if agent not in rep.installed_locations or info.get("enabled"):
                rep.installed_locations[agent] = dict(info)
        for file_path in skill.files:
            if file_path not in rep.files:
                rep.files.append(file_path)

        if skill.enabled:
            rep.enabled = True
        rep.status = "enabled" if rep.enabled else "disabled"
        if skill.last_modified > rep.last_modified:
            rep.last_modified = skill.last_modified

        rep.duplicate_group = rep.duplicate_group or skill.duplicate_group or rep.id
        if not rep.duplicate_group:
            rep.duplicate_group = rep.id

    # ------------------------------------------------------------------
    # Single Skill directory scan
    # ------------------------------------------------------------------
    def _scan_skill_dir(
        self,
        skill_dir: Path,
        agent_id: str,
        enabled: bool = True,
    ) -> Skill | None:
        skill_md = find_skill_md(skill_dir)
        if skill_md is None:
            return None

        parsed = self.parser.parse(skill_md)
        skill_id = self._normalize_id(parsed.get("name") or skill_dir.name)
        if not skill_id:
            skill_id = skill_dir.name.lower()
        if not skill_id:
            return None

        metadata = collect_skill_file_metadata(skill_dir)
        cached = self.cache_manager.get(skill_id) if self.cache_manager else None
        cache_matches_files = bool(
            cached
            and cached.get("hash")
            and cached.get("file_signature") == metadata.signature
        )
        content_hash = str(cached.get("hash") or "") if cache_matches_files and cached else ""
        if not content_hash:
            content_hash = (
                self.cache_manager.compute_skill_hash(skill_dir)
                if self.cache_manager
                else self._fallback_hash(skill_dir)
            )

        cache_content_matches = bool(cached and cached.get("hash") == content_hash)
        cache_analysis_matches = bool(
            cache_content_matches
            and cached
            and cached.get("summary_pipeline_version") == SUMMARY_PIPELINE_VERSION
        )
        cached_summaries: dict[str, str] = {}
        cached_features: dict[str, list[str]] = {}
        if cache_analysis_matches and cached:
            cached_summaries = dict(cached.get("summaries") or {})
            cached_features = {
                language: list(items)
                for language, items in dict(cached.get("features") or {}).items()
                if isinstance(items, list)
            }
            source = dict(cached.get("source") or {})
        else:
            analysis = self.summary_manager.analyze(parsed, skill_dir)
            cached_summaries = dict(analysis.get("summaries") or {})
            cached_features = {
                language: list(items)
                for language, items in dict(analysis.get("features") or {}).items()
                if isinstance(items, list)
            }
            source = (
                dict(cached.get("source") or {})
                if cache_content_matches and cached
                else self.source_detector.detect(skill_dir)
            )
            if self.cache_manager:
                cache_data = {
                    "hash": content_hash,
                    "summary": cached_summaries.get("zh-CN") or "未知",
                    "summaries": cached_summaries,
                    "features": cached_features,
                    "summary_pipeline_version": SUMMARY_PIPELINE_VERSION,
                    "source": source,
                    "last_scan_time": self.cache_manager.now_iso(),
                    "file_signature": metadata.signature,
                }
                self.cache_manager.set(skill_id, cache_data)
        if (
            self.cache_manager
            and cached
            and cached.get("hash") == content_hash
            and cached.get("file_signature") != metadata.signature
        ):
            # Migrate older cache entries after the first verified scan.
            migrated = dict(cached)
            migrated["file_signature"] = metadata.signature
            self.cache_manager.set(skill_id, migrated)

        summary = cached_summaries.get("zh-CN") or "未知"
        status = "enabled" if enabled else "disabled"
        skill = Skill(
            id=skill_id,
            name=str(parsed.get("name") or skill_dir.name),
            display_name=str(parsed.get("display_name") or skill_dir.name),
            description=str(parsed.get("description") or ""),
            summary=summary,
            summaries=cached_summaries,
            features=cached_features,
            category=str(parsed.get("category") or ""),
            tags=list(parsed.get("tags") or []),
            version=parsed.get("version"),
            source=source,
            path=str(skill_md),
            installed_agents=[agent_id] if agent_id else [],
            locations={agent_id: enabled} if agent_id else {},
            installed_locations={
                agent_id: {"path": str(skill_dir), "enabled": enabled}
            }
            if agent_id
            else {},
            files=metadata.files,
            hash=content_hash,
            status=status,
            enabled=enabled,
            last_modified=self._format_mtime(metadata.latest_mtime),
            duplicate_group=skill_id,
        )
        return skill

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _iter_skill_dirs(self, root: Path, *, include_disabled: bool = False) -> Iterable[Path]:
        yield from iter_skill_dirs(root, include_disabled=include_disabled)

    @staticmethod
    def _is_disabled_under(skill_dir: Path, root: Path) -> bool:
        try:
            relative_parts = skill_dir.relative_to(root).parts[:-1]
        except ValueError:
            return False
        return any(part.casefold().endswith("_disabled") for part in relative_parts)

    @staticmethod
    def _disabled_root_for(root: Path) -> Path:
        return root.parent / f"{root.name}_disabled"

    @staticmethod
    def _format_mtime(timestamp: float) -> str:
        import datetime as _dt

        if timestamp <= 0:
            return ""
        return _dt.datetime.fromtimestamp(timestamp, tz=_dt.timezone.utc).isoformat(
            timespec="seconds"
        )

    @staticmethod
    def _normalize_id(value: str) -> str:
        value = value.strip().lower().replace(" ", "-")
        return value

    @staticmethod
    def _fallback_hash(skill_dir: Path) -> str:
        import hashlib

        hasher = hashlib.sha256()
        try:
            for path in sorted(skill_dir.rglob("*"), key=lambda p: p.as_posix().lower()):
                if path.is_file():
                    rel = path.relative_to(skill_dir).as_posix()
                    hasher.update(rel.encode("utf-8", errors="replace"))
                    hasher.update(b"\0")
                    hasher.update(path.read_bytes())
        except OSError:
            pass
        return hasher.hexdigest()
