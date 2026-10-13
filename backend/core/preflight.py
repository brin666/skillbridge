"""Preflight safety checks for Skill sync.

Phase 5A only implements checks. It never copies or modifies files.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from ..adapters.base import AgentAdapter
from ..models.preflight import CheckResult, PreflightResult
from ..models.skill import Skill
from ..skill_files import find_skill_md, has_skill_md_symlink, iter_skill_md_files
from .agent_scanner import DEFAULT_ADAPTER_CLASSES
from .cache_manager import CacheManager
from .compatibility_checker import CompatibilityChecker
from .hash_utils import compute_skill_md_hash
from .skill_parser import SkillParser
from .source_detector import SourceDetector

RUNTIMES = ("python", "node", "npm", "pnpm")


class PreflightChecker:
    """Run independent safety checks before a Skill sync."""

    def __init__(
        self,
        adapters: list[AgentAdapter] | None = None,
        cache_manager: CacheManager | None = None,
    ) -> None:
        self.adapters = adapters or [cls() for cls in DEFAULT_ADAPTER_CLASSES]
        self.cache_manager = cache_manager or CacheManager()
        self.parser = SkillParser()
        self.source_detector = SourceDetector()
        self.compatibility_checker = CompatibilityChecker(parser=self.parser)
        self._runtime_versions: dict[str, str | None] = {}

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------
    def check(
        self,
        skill: Skill,
        target_agent: str | AgentAdapter,
        *,
        target_inventory_checked: bool = False,
    ) -> PreflightResult:
        checks: list[CheckResult] = []
        adapter = self._resolve_adapter(target_agent)

        checks.append(self._check_skill_exists(skill))
        checks.append(self._check_frontmatter(skill))
        checks.append(self._check_directory_structure(skill))
        if adapter is not None:
            checks.extend(self.compatibility_checker.check(skill, adapter))
        checks.append(self._check_source(skill))
        checks.append(self._check_target_agent(skill, adapter))
        checks.append(self._check_capabilities(skill, adapter))
        checks.extend(self._check_runtime(skill))
        checks.append(
            self._check_conflict(
                skill,
                adapter,
                target_inventory_checked=target_inventory_checked,
            )
        )

        return PreflightResult.from_checks(checks)

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------
    def _check_skill_exists(self, skill: Skill) -> CheckResult:
        skill_dir = self._skill_dir(skill)
        if not skill_dir.is_dir():
            return CheckResult(
                name="SKILL.md",
                status="block",
                message="SKILL.md not found",
            )
        skill_md = find_skill_md(skill.path) or find_skill_md(skill_dir)
        if skill_md is None:
            return CheckResult(
                name="SKILL.md",
                status="block",
                message="SKILL.md not found",
            )
        return CheckResult(name="SKILL.md", status="pass", message="SKILL.md exists")

    def _check_frontmatter(self, skill: Skill) -> CheckResult:
        skill_dir = self._skill_dir(skill)
        if not skill_dir.is_dir():
            return CheckResult(
                name="frontmatter",
                status="block",
                message="Skill directory missing",
            )
        parsed = self.parser.parse(find_skill_md(skill.path) or skill_dir)
        warnings = parsed.get("warnings") or []
        if any("frontmatter is not closed" in w for w in warnings):
            return CheckResult(
                name="frontmatter",
                status="block",
                message="Frontmatter is not closed or not parseable",
            )
        if not parsed.get("name"):
            return CheckResult(
                name="frontmatter",
                status="block",
                message="Frontmatter name is missing",
            )
        return CheckResult(name="frontmatter", status="pass", message="Frontmatter is valid")

    def _check_directory_structure(self, skill: Skill) -> CheckResult:
        return CheckResult(
            name="directory-structure",
            status="pass",
            message="A Skill with only SKILL.md is valid for the selected sync scope",
        )

    def _check_source(self, skill: Skill) -> CheckResult:
        source = skill.source or self.source_detector.detect(self._skill_dir(skill))
        source_type = source.get("type", "unknown") if isinstance(source, dict) else "unknown"
        try:
            skill_md = find_skill_md(skill.path) or find_skill_md(self._skill_dir(skill))
            raw = skill_md.read_text(encoding="utf-8") if skill_md else ""
        except (OSError, UnicodeDecodeError):
            raw = ""
        frontmatter, _, _ = self.parser._split_frontmatter(raw)
        metadata = frontmatter.get("metadata")
        sync_permission = str(
            metadata.get("skillbridge-sync", "") if isinstance(metadata, dict) else ""
        ).strip().casefold()
        if sync_permission in {"deny", "denied", "never"}:
            return CheckResult(
                name="source",
                status="block",
                message="This Skill explicitly opts out of SkillBridge sync",
            )
        if sync_permission in {"allow", "approved"}:
            return CheckResult(
                name="source",
                status="pass",
                message="This Skill explicitly opts in to SkillBridge sync",
                details={"sourceType": source_type, "syncPermission": sync_permission},
            )
        return CheckResult(
            name="source",
            status="pass",
            message="Origin does not determine Harness compatibility; no explicit SkillBridge opt-out was found",
            details={"sourceType": source_type, "syncPermission": "unspecified"},
        )

    def _check_target_agent(self, skill: Skill, adapter: AgentAdapter | None) -> CheckResult:
        if adapter is None:
            return CheckResult(
                name="target-agent",
                status="block",
                message="Target Agent is not supported",
            )
        support = adapter.supports_skill(skill)
        if support is False:
            return CheckResult(
                name="target-agent",
                status="block",
                message="Target Agent does not support this Skill",
            )
        if support == "unknown":
            return CheckResult(
                name="target-agent",
                status="warn",
                message="Target Agent support is unknown",
            )
        return CheckResult(
            name="target-agent",
            status="pass",
            message=f"Target Agent {adapter.get_name()} supports this Skill",
        )

    def _check_capabilities(self, skill: Skill, adapter: AgentAdapter | None) -> CheckResult:
        required = self._skill_requires(self._skill_dir(skill))
        if not required:
            return CheckResult(
                name="capabilities",
                status="pass",
                message="No special capabilities required",
            )
        if adapter is None:
            return CheckResult(
                name="capabilities",
                status="block",
                message="Target Agent is not supported",
            )
        available = set(adapter.capabilities() or [])
        missing = [cap for cap in required if cap not in available]
        if missing:
            return CheckResult(
                name="capabilities",
                status="warn",
                message="Target Agent may lack capabilities: " + ", ".join(missing),
                details={"required": required, "missing": missing},
            )
        return CheckResult(
            name="capabilities",
            status="pass",
            message="Required capabilities are available",
        )

    def _check_runtime(self, skill: Skill) -> list[CheckResult]:
        requirements = self._runtime_requirements(self._skill_dir(skill))
        checks: list[CheckResult] = []
        for runtime in RUNTIMES:
            requirement = requirements.get(runtime)
            if not requirement:
                continue
            installed = self._installed_runtime_version(runtime)
            if installed is None:
                checks.append(
                    CheckResult(
                        name=f"runtime-{runtime}",
                        status="block",
                        message=f"{runtime} is required but not found",
                    )
                )
                continue
            satisfies = self._version_satisfies(installed, requirement)
            if satisfies is None:
                checks.append(
                    CheckResult(
                        name=f"runtime-{runtime}",
                        status="warn",
                        message=f"Cannot verify {runtime} requirement syntax: {requirement}",
                        details={"installed": installed, "required": requirement},
                    )
                )
            elif satisfies:
                checks.append(
                    CheckResult(
                        name=f"runtime-{runtime}",
                        status="pass",
                        message=f"{runtime} {installed} satisfies {requirement}",
                    )
                )
            else:
                checks.append(
                    CheckResult(
                        name=f"runtime-{runtime}",
                        status="block",
                        message=f"{runtime} {installed} does not satisfy {requirement}",
                        details={"installed": installed, "required": requirement},
                    )
                )
        if not checks:
            checks.append(
                CheckResult(name="runtime", status="pass", message="No runtime requirements found")
            )
        return checks

    def _check_conflict(
        self,
        skill: Skill,
        adapter: AgentAdapter | None,
        *,
        target_inventory_checked: bool = False,
    ) -> CheckResult:
        if adapter is None:
            return CheckResult(
                name="conflict",
                status="block",
                message="Target Agent is not supported",
            )
        roots = adapter.get_skill_paths()
        if not roots:
            return CheckResult(
                name="conflict",
                status="block",
                message="Target Agent Skill directory not found",
            )
        target_dir = Path(roots[0]) / skill.id
        target_skill_md = find_skill_md(target_dir)
        if target_dir.is_symlink() or has_skill_md_symlink(target_dir):
            return CheckResult(
                name="conflict",
                status="block",
                message="Target Skill path is a symbolic link; refusing to sync through it",
                details={"targetPath": str(target_dir)},
            )
        if not target_dir.exists():
            if not target_inventory_checked:
                nested_matches = self.find_target_skill_dirs(skill, adapter)
                if nested_matches:
                    source_hash = compute_skill_md_hash(self._skill_dir(skill))
                    match_hashes = {
                        compute_skill_md_hash(path) for path in nested_matches
                    }
                    match_hashes.discard("")
                    paths = [str(path) for path in nested_matches]
                    if match_hashes == {source_hash}:
                        return CheckResult(
                            name="conflict",
                            status="pass",
                            message="Matching SKILL.md already installed in a nested target directory",
                            details={"targetPaths": paths},
                        )
                    return CheckResult(
                        name="conflict",
                        status="warn",
                        message="A Skill with the same declared name already exists in a nested target directory; it will not be overwritten automatically",
                        details={"targetPaths": paths},
                    )
            return CheckResult(
                name="conflict",
                status="pass",
                message="No existing Skill at target location",
            )
        source_hash = compute_skill_md_hash(self._skill_dir(skill))
        existing_hash = compute_skill_md_hash(target_dir)
        if existing_hash and source_hash and existing_hash == source_hash:
            return CheckResult(
                name="conflict",
                status="pass",
                message="Matching SKILL.md already installed",
            )
        if not existing_hash:
            return CheckResult(
                name="conflict",
                status="pass",
                message="No existing SKILL.md at target location",
            )
        return CheckResult(
            name="conflict",
            status="warn",
            message="Existing Skill differs",
            details={
                "targetPath": str(target_dir),
                "sourceSha256": source_hash,
                "targetSha256": existing_hash,
            },
        )

    def find_target_skill_dirs(
        self,
        skill: Skill,
        adapter: AgentAdapter,
    ) -> list[Path]:
        """Find active target Skills by the name declared in their SKILL.md."""
        wanted = self._normalize_skill_id(skill.id)
        if not wanted:
            return []
        matches: list[Path] = []
        seen: set[str] = set()
        for root in adapter.get_skill_paths():
            for document in iter_skill_md_files(root):
                parsed = self.parser.parse(document)
                declared_name = self._normalize_skill_id(str(parsed.get("name") or ""))
                if declared_name != wanted:
                    continue
                key = str(document.resolve(strict=False)).casefold()
                if key not in seen:
                    seen.add(key)
                    matches.append(document)
        return matches

    @staticmethod
    def _normalize_skill_id(value: str) -> str:
        return value.strip().casefold().replace(" ", "-")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _resolve_adapter(self, target_agent: str | AgentAdapter) -> AgentAdapter | None:
        if isinstance(target_agent, AgentAdapter):
            return target_agent
        for adapter in self.adapters:
            if adapter.agent_id == target_agent:
                return adapter
        return None

    @staticmethod
    def _skill_dir(skill: Skill) -> Path:
        path = Path(skill.path).resolve()
        if path.is_file() or path.name.lower() == "skill.md":
            return path.parent
        return path

    @staticmethod
    def _read_json(path: Path) -> dict | None:
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            return data if isinstance(data, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    def _skill_requires(self, skill_dir: Path) -> list[str]:
        metadata = self._read_json(skill_dir / "metadata.json") or {}
        requires = metadata.get("requires") or metadata.get("capabilities") or []
        if isinstance(requires, str):
            requires = [requires]
        return [str(item) for item in requires if str(item).strip()]

    def _runtime_requirements(self, skill_dir: Path) -> dict[str, str]:
        requirements: dict[str, str] = {}

        metadata = self._read_json(skill_dir / "metadata.json") or {}
        runtime = metadata.get("runtime") or metadata.get("engines") or {}
        if isinstance(runtime, dict):
            for key in RUNTIMES:
                value = runtime.get(key)
                if value:
                    requirements[key] = str(value)

        package = self._read_json(skill_dir / "package.json") or {}
        engines = package.get("engines") or {}
        if isinstance(engines, dict):
            for key in RUNTIMES:
                value = engines.get(key)
                if value:
                    requirements[key] = str(value)

        return requirements

    def _installed_runtime_version(self, runtime: str) -> str | None:
        if runtime in self._runtime_versions:
            return self._runtime_versions[runtime]
        if runtime == "python":
            version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            self._runtime_versions[runtime] = version
            return version
        commands = {
            "node": ["node", "--version"],
            "npm": ["npm", "--version"],
            "pnpm": ["pnpm", "--version"],
        }
        command = commands.get(runtime)
        if not command:
            self._runtime_versions[runtime] = None
            return None
        executable = shutil.which(command[0])
        if not executable:
            self._runtime_versions[runtime] = None
            return None
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            self._runtime_versions[runtime] = None
            return None
        version = (proc.stdout or proc.stderr).strip().splitlines()
        if not version:
            self._runtime_versions[runtime] = None
            return None
        self._runtime_versions[runtime] = version[0].strip().lstrip("vV")
        return self._runtime_versions[runtime]

    # ------------------------------------------------------------------
    # Minimal version comparison
    # ------------------------------------------------------------------
    def _version_satisfies(self, installed: str, requirement: str) -> bool | None:
        req = requirement.strip()
        match = re.fullmatch(r"(>=|<=|>|<|==|=|\^|~)?\s*v?([\d.]+)", req)
        if not match:
            return None
        operator = match.group(1) or "="
        required_version = match.group(2)
        installed_tuple = self._version_tuple(installed)
        required_tuple = self._version_tuple(required_version)

        if operator == ">=":
            return installed_tuple >= required_tuple
        if operator == "<=":
            return installed_tuple <= required_tuple
        if operator == ">":
            return installed_tuple > required_tuple
        if operator == "<":
            return installed_tuple < required_tuple
        if operator in ("^", "~"):
            if installed_tuple < required_tuple:
                return False
            major, minor, patch = required_tuple
            if operator == "~":
                upper = (major, minor + 1, 0)
            elif major > 0:
                upper = (major + 1, 0, 0)
            elif minor > 0:
                upper = (0, minor + 1, 0)
            else:
                upper = (0, 0, patch + 1)
            return installed_tuple < upper
        return installed_tuple == required_tuple

    @staticmethod
    def _version_tuple(value: str) -> tuple[int, ...]:
        parts = re.findall(r"\d+", value)
        nums = [int(p) for p in parts[:3]]
        while len(nums) < 3:
            nums.append(0)
        return tuple(nums)


# Compatibility exports for existing code/tests.
from ..models.preflight import CheckResult as CheckResult  # noqa: E402
from ..models.preflight import PreflightResult as PreflightResult  # noqa: E402
