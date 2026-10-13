"""Central Skill Library manager.

The Library is the managed source of truth for Skills. It never deletes or
migrates original Agent Skills; import is a non-destructive copy.
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..models.agent import Agent
from ..models.library import DeploymentState, LibraryEntry, LibrarySkill
from ..models.skill import Skill
from ..skill_files import find_skill_md, iter_skill_md_files
from .hash_utils import compute_skill_hash, compute_skill_md_hash
from .installer import Installer
from .skill_parser import SkillParser
from .source_detector import SourceDetector
from .summary_manager import SummaryManager
from .trash_manager import TrashManager

DEFAULT_LIBRARY_ROOT = Path.home() / ".skillbridge" / "library"
DEFAULT_LIBRARY_TRASH = Path.home() / ".skillbridge" / "trash" / "library"


class LibraryManager:
    """Manages the local SkillBridge Library."""

    def __init__(
        self,
        library_root: str | Path | None = None,
        trash_root: str | Path | None = None,
    ) -> None:
        self.library_root = Path(library_root or DEFAULT_LIBRARY_ROOT)
        self.skills_dir = self.library_root / "skills"
        self.index_path = self.library_root / "index.json"
        self.trash = TrashManager(trash_root=Path(trash_root or DEFAULT_LIBRARY_TRASH))
        self.parser = SkillParser()
        self.source_detector = SourceDetector()
        self.summary_manager = SummaryManager()
        self.installer = Installer(tmp_root=self.library_root / "tmp")
        self._data: list[dict] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def list_library_skills(self, agents: list[Agent] | None = None) -> list[LibrarySkill]:
        self.refresh_library_index()
        skills: list[LibrarySkill] = []
        for entry in self._load_index():
            skill = self._library_skill_from_entry(entry)
            if agents is not None:
                skill.deployments = self.compare_deployments(skill, agents)
            skills.append(skill)
        skills.sort(key=lambda s: s.display_name.lower())
        return skills

    def get_library_skill(
        self,
        skill_id: str,
        agents: list[Agent] | None = None,
    ) -> LibrarySkill | None:
        for skill in self.list_library_skills(agents=agents):
            if skill.id == skill_id or skill.name == skill_id:
                return skill
        return None

    def import_skill(self, skill: Skill, source_agent: str = "") -> dict:
        """Copy an Agent Skill into the Library without modifying the source."""
        source_dir = self._skill_dir(skill)
        if not source_dir.is_dir():
            return {"status": "failed", "message": "Source Skill directory not found"}

        incoming_hash = compute_skill_hash(source_dir)
        existing = self.get_library_skill(skill.id)
        if existing is not None:
            if existing.hash == incoming_hash:
                return {"status": "already_in_library", "message": "Skill already exists in Library"}
            return {
                "status": "library_conflict",
                "library_hash": existing.hash,
                "incoming_hash": incoming_hash,
                "message": "A different version already exists in SkillBridge Library",
            }

        temp_path = self.installer.prepare_temp_path(skill.id)
        try:
            self.installer.copy_skill_to_temp(source_dir, temp_path)
            imported_skill_md = find_skill_md(temp_path)
            if imported_skill_md is None:
                raise RuntimeError("Imported Skill is missing SKILL.md")
            if compute_skill_hash(temp_path) != incoming_hash:
                raise RuntimeError("Temporary copy verification failed")
            if imported_skill_md.name != "SKILL.md":
                normalization_path = temp_path / f".skillbridge-normalize-{uuid.uuid4().hex}"
                imported_skill_md.rename(normalization_path)
                normalization_path.rename(temp_path / "SKILL.md")
            if compute_skill_hash(temp_path) != incoming_hash:
                raise RuntimeError("Canonical SKILL.md verification failed")

            target_dir = self.skills_dir / skill.id
            if target_dir.exists():
                raise FileExistsError("Library Skill already exists")
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(temp_path), str(target_dir))

            parsed = self.parser.parse(target_dir)
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            entry = LibraryEntry(
                id=skill.id,
                hash=incoming_hash,
                source=self.source_detector.detect(target_dir),
                imported_from={"agent": source_agent, "path": str(source_dir)},
                imported_at=now,
                library_path=str(target_dir),
            )
            self._upsert_index(entry)
            self._save_index()
            return {
                "status": "success",
                "message": "Added to SkillBridge Library",
                "library_skill": self._library_skill_from_entry(entry.to_dict()).to_dict(),
            }
        except Exception as exc:
            if temp_path.exists():
                shutil.rmtree(temp_path, ignore_errors=True)
            return {"status": "failed", "message": str(exc)}

    def remove_from_library(self, skill_id: str) -> dict:
        skill = self.get_library_skill(skill_id)
        if skill is None:
            return {"status": "not_found", "message": "Library Skill not found"}
        source_dir = Path(skill.library_path)
        if source_dir.exists():
            self.trash.trash(source_dir, skill_id)
        self._remove_index(skill_id)
        self._save_index()
        return {
            "status": "success",
            "message": "Removed from Library. Existing Agent copies were not modified.",
        }

    def compare_deployments(
        self,
        library_skill: LibrarySkill,
        agents: list[Agent],
    ) -> dict[str, DeploymentState]:
        """Compare Library hash against all detected Agent copies."""
        deployments: dict[str, DeploymentState] = {}
        for agent in agents:
            if not agent.installed:
                continue
            state = self._deployment_state(library_skill, agent)
            deployments[agent.id] = state
        return deployments

    def refresh_library_index(self) -> None:
        """Rebuild index entries from the real Library files if needed."""
        if not self.skills_dir.is_dir():
            self._save_index()
            return
        entries = self._load_index()
        existing = {entry["id"]: entry for entry in entries}
        new_entries: list[LibraryEntry] = []
        for skill_dir in sorted(self.skills_dir.iterdir(), key=lambda p: p.name.lower()):
            if not skill_dir.is_dir():
                continue
            skill_md = find_skill_md(skill_dir)
            if skill_md is None:
                continue
            skill_id = skill_dir.name
            content_hash = compute_skill_hash(skill_dir)
            old = existing.get(skill_id, {})
            entry = LibraryEntry(
                id=skill_id,
                hash=content_hash,
                source=self.source_detector.detect(skill_dir),
                imported_from=old.get("importedFrom", {}),
                imported_at=old.get("importedAt", ""),
                library_path=str(skill_dir),
            )
            new_entries.append(entry)
        self._data = [e.to_dict() for e in new_entries]
        self._save_index()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _deployment_state(self, library_skill: LibrarySkill, agent: Agent) -> DeploymentState:
        active_matches: list[Path] = []
        for root in agent.skill_paths:
            root_path = Path(root)
            for document in iter_skill_md_files(root_path):
                if self._declares_skill_id(document, library_skill.id):
                    active_matches.append(document.parent)
        if active_matches:
            states = [self._state_for_dir(path, library_skill) for path in active_matches]
            return next((state for state in states if state.status == "same"), states[0])

        disabled_matches: list[Path] = []
        for root in agent.skill_paths:
            root_path = Path(root)
            disabled_roots = [
                root_path.parent / f"{root_path.name}_disabled",
                root_path,
            ]
            for disabled_root in disabled_roots:
                for document in iter_skill_md_files(disabled_root, include_disabled=True):
                    if not self._path_is_disabled(document, root_path, disabled_root):
                        continue
                    if self._declares_skill_id(document, library_skill.id):
                        disabled_matches.append(document.parent)
        if disabled_matches:
            states = [self._state_for_dir(path, library_skill) for path in disabled_matches]
            state = next((item for item in states if item.same_hash), states[0])
            state.status = "disabled"
            return state
        return DeploymentState(installed=False, same_hash=False, status="not_deployed")

    def _declares_skill_id(self, document: Path, skill_id: str) -> bool:
        parsed = self.parser.parse(document)
        declared = str(parsed.get("name") or document.parent.name)
        return self._normalize_skill_id(declared) == self._normalize_skill_id(skill_id)

    @staticmethod
    def _normalize_skill_id(value: str) -> str:
        return value.strip().casefold().replace(" ", "-")

    @staticmethod
    def _path_is_disabled(document: Path, active_root: Path, scanned_root: Path) -> bool:
        if scanned_root != active_root:
            return scanned_root.name.casefold().endswith("_disabled")
        try:
            relative_parts = document.parent.relative_to(active_root).parts[:-1]
        except ValueError:
            return False
        return any(part.casefold().endswith("_disabled") for part in relative_parts)

    def _state_for_dir(self, skill_dir: Path, library_skill: LibrarySkill) -> DeploymentState:
        # Cross-Harness deployment deliberately copies only SKILL.md. Keep the
        # Library's full-directory hash for import integrity, but compare the
        # deployed payload using the same file-level boundary as SyncManager.
        library_hash = compute_skill_md_hash(library_skill.library_path)
        content_hash = compute_skill_md_hash(skill_dir)
        same = bool(content_hash) and content_hash == library_hash
        return DeploymentState(
            installed=True,
            same_hash=same,
            path=str(skill_dir),
            status="same" if same else "diverged",
        )

    @staticmethod
    def _skill_dir(skill: Skill) -> Path:
        path = Path(skill.path).resolve()
        if path.is_file() or path.name.lower() == "skill.md":
            return path.parent
        return path

    def _library_skill_from_entry(self, entry: dict) -> LibrarySkill:
        path = Path(entry.get("libraryPath", ""))
        parsed = self.parser.parse(path) if path.is_dir() else {}
        return LibrarySkill(
            id=entry.get("id", ""),
            name=entry.get("id", ""),
            display_name=parsed.get("display_name") or entry.get("id", ""),
            summary=self.summary_manager.generate(parsed, path) if path.is_dir() else "",
            category=parsed.get("category", ""),
            tags=parsed.get("tags", []),
            library_path=str(path),
            hash=entry.get("hash", ""),
            source=entry.get("source", {}),
            imported_from=entry.get("importedFrom", {}),
            imported_at=entry.get("importedAt", ""),
        )

    # ------------------------------------------------------------------
    # Index persistence
    # ------------------------------------------------------------------
    def _load_index(self) -> list[dict]:
        if not self.index_path.is_file():
            return []
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if isinstance(data, dict):
            return data.get("skills", [])
        if isinstance(data, list):
            return data
        return []

    def _save_index(self) -> None:
        self.library_root.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(
            json.dumps({"version": 1, "skills": self._data}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _upsert_index(self, entry: LibraryEntry) -> None:
        data = self._load_index()
        self._data = [e for e in data if e.get("id") != entry.id]
        self._data.append(entry.to_dict())

    def _remove_index(self, skill_id: str) -> None:
        self._data = [e for e in self._load_index() if e.get("id") != skill_id]
