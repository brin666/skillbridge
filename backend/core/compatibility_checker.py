"""Fast, local-only compatibility checks for SKILL.md syncs.

This checker is intentionally static: it never starts a Harness or invokes a
model. A clean result means the file looks portable enough to sync, not that
the Skill's behavior is guaranteed to be identical in every Harness.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from ..adapters.base import AgentAdapter
from ..models.preflight import CheckResult
from ..models.skill import Skill
from ..skill_files import find_skill_md
from .skill_parser import SkillParser


class CompatibilityChecker:
    """Check a Skill's static format and known target-Harness constraints."""

    _name_pattern = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    _local_reference_pattern = re.compile(
        r"(?<![A-Za-z0-9_./-])(?:\.{1,2}/)?(?:scripts|references|assets|templates|docs|examples|data|bin|config|configs|schemas|prompts|workflows)/[^\s\x60)>\"']*",
        re.IGNORECASE,
    )
    _markdown_link_pattern = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
    _file_reference_pattern = re.compile(
        r"(?<![A-Za-z0-9_./-])(?:\.{1,2}/)?(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.(?:md|mdx|rst|txt|json|jsonl|ya?ml|toml|ini|cfg|conf|xml|csv|tsv|log|py|js|mjs|cjs|ts|tsx|jsx|sh|ps1|bat|r|rb|go|rs|java|c|cpp|h|hpp|vue|svelte|png|jpe?g|svg|html|css|sql|j2|jinja2?|tmpl|pdf|docx|xlsx|ipynb|wasm|bin)(?![A-Za-z0-9_-])",
        re.IGNORECASE,
    )
    _target_aliases = {
        "codex": ("codex", "openai codex"),
        "claude": ("claude code", "claude"),
        "hermes": ("hermes agent", "hermes"),
        "dsh": ("deepseek harness", "deepseek", "dsh"),
        "qwen": ("qwen code", "qwen"),
        "trae": ("trae",),
        "codebuddy": ("codebuddy",),
        "lingma": ("tongyi lingma", "qoder", "lingma"),
    }
    _explicit_requirement_pattern = re.compile(
        r"\b(?:must|requires?|only|exclusively|minimum|at least)\b|"
        r"(?:>=|<=|==|~=|(?<![<>])>|(?<![<>])<|\^)|"
        r"\bversion\s+v?\d+(?:\.\d+){0,2}\b|\bv?\d+\.\d+(?:\.\d+)?\b|\bv\d+(?:\.\d+){0,2}\b",
        re.IGNORECASE,
    )

    def __init__(self, parser: SkillParser | None = None, max_cache_entries: int = 512) -> None:
        self.parser = parser or SkillParser()
        self.max_cache_entries = max_cache_entries
        self._cache: dict[tuple[str, str, str, str, str, str, str], list[CheckResult]] = {}

    def check(self, skill: Skill, target: AgentAdapter) -> list[CheckResult]:
        skill_md = self._skill_md_path(skill)
        try:
            raw = skill_md.read_bytes()
        except OSError as exc:
            return [CheckResult("compatibility", "block", f"Cannot read SKILL.md: {exc}")]

        digest = hashlib.sha256(raw).hexdigest()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return [CheckResult("compatibility", "block", "SKILL.md is not valid UTF-8")]

        skill_support = str(target.supports_skill(skill)).lower()
        tool_support = str(target.supports_allowed_tools()).lower()
        target_version = target.get_version()
        frontmatter, body, warnings = self.parser._split_frontmatter(text)
        raw_frontmatter = self._raw_frontmatter(text)
        references = self._referenced_resources(body + "\n" + raw_frontmatter)
        resource_inventory = self._inspect_references(skill_md.parent, references)
        resource_signature = hashlib.sha256(
            json.dumps(resource_inventory, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        key = (
            digest,
            skill_md.parent.name.casefold(),
            target.agent_id,
            target_version or "",
            skill_support,
            tool_support,
            resource_signature,
        )
        cached = self._cache.get(key)
        if cached is not None:
            return [CheckResult(c.name, c.status, c.message, dict(c.details)) for c in cached]

        checks: list[CheckResult] = []
        if warnings and any("not closed" in warning for warning in warnings):
            checks.append(CheckResult("skill-format", "block", "SKILL.md frontmatter is not closed"))
        elif not text.startswith("---"):
            checks.append(CheckResult("skill-format", "block", "SKILL.md must start with YAML frontmatter"))
        else:
            name = str(frontmatter.get("name") or "").strip()
            description = str(frontmatter.get("description") or "").strip()
            problems: list[str] = []
            if not name or len(name) > 64 or not self._name_pattern.fullmatch(name):
                problems.append("name must use lowercase letters, numbers, and single hyphens")
            if not description or len(description) > 1024:
                problems.append("description must contain 1–1024 characters")
            checks.append(
                CheckResult(
                    "skill-format",
                    "block" if problems else "pass",
                    "; ".join(problems) if problems else "Required Agent Skills metadata is valid",
                )
            )
            if name and name != skill_md.parent.name:
                checks.append(
                    CheckResult(
                        "skill-location",
                        "pass",
                        f"Document declares '{name}' in folder '{skill_md.parent.name}'; using the SKILL.md name as its identity",
                        {"declaredName": name, "folderName": skill_md.parent.name},
                    )
                )

        compatibility = self._compatibility_value(frontmatter, raw_frontmatter)
        if compatibility:
            checks.append(self._check_compatibility_note(compatibility, target, target_version))
        else:
            checks.append(CheckResult("compatibility-notes", "pass", "No explicit environment requirement to verify"))

        checks.append(self._check_document_compatibility(body, target))

        allowed_tools = frontmatter.get("allowed-tools")
        if allowed_tools:
            support = target.supports_allowed_tools()
            if support is True:
                checks.append(CheckResult("allowed-tools", "pass", f"{target.get_name()} supports allowed-tools"))
            elif support is False:
                checks.append(
                    CheckResult(
                        "allowed-tools",
                        "warn",
                        f"{target.get_name()} may ignore the experimental allowed-tools field",
                    )
                )
            else:
                checks.append(
                    CheckResult(
                        "allowed-tools",
                        "warn",
                        f"{target.get_name()} allowed-tools support is not verified",
                    )
                )
        else:
            checks.append(CheckResult("allowed-tools", "pass", "No allowed-tools requirement"))

        if references:
            present = resource_inventory["present"]
            missing = resource_inventory["missing"]
            outside = resource_inventory["outside"]
            if missing or outside:
                message = (
                    f"Found {len(present)} referenced file(s) in the Skill folder; "
                    f"{len(missing) + len(outside)} reference(s) are missing or outside it. "
                    "Only SKILL.md is copied."
                )
            else:
                message = (
                    f"Found {len(present)} referenced supporting file(s) locally, "
                    "but only SKILL.md is copied; the target may need those files separately"
                )
            checks.append(
                CheckResult(
                    "sync-scope",
                    "warn",
                    message,
                    {
                        "references": references,
                        "presentReferences": present,
                        "missingReferences": missing,
                        "outsideSkillFolderReferences": outside,
                        "copyScope": ["SKILL.md"],
                    },
                )
            )
        else:
            checks.append(
                CheckResult(
                    "sync-scope",
                    "pass",
                    "No supporting files referenced by SKILL.md",
                    {"references": [], "presentReferences": [], "missingReferences": [], "copyScope": ["SKILL.md"]},
                )
            )

        if self.max_cache_entries > 0:
            if len(self._cache) >= self.max_cache_entries:
                self._cache.clear()
            self._cache[key] = checks
        return [CheckResult(c.name, c.status, c.message, dict(c.details)) for c in checks]

    def _check_compatibility_note(
        self,
        note: str,
        target: AgentAdapter,
        target_version: str | None,
    ) -> CheckResult:
        mentioned = [
            agent_id
            for agent_id, aliases in self._target_aliases.items()
            if any(self._contains_term(note, alias) for alias in aliases)
        ]
        details = {
            "compatibility": note,
            "targetAgent": target.agent_id,
            "targetVersion": target_version,
            "mentionedHarnesses": mentioned,
        }
        required = self._required_by_without_phrase(note)
        if required:
            details["requiredHarnesses"] = required
            if target.agent_id in required:
                return CheckResult(
                    "compatibility-notes",
                    "pass",
                    f"Compatibility note indicates {target.get_name()} is required, not excluded",
                    details,
                )
            labels = ", ".join(required)
            return CheckResult(
                "compatibility-notes",
                "block",
                f"Compatibility note requires {labels}; {target.get_name()} cannot satisfy that Harness requirement",
                details,
            )
        if self._target_is_negated(note, target.agent_id):
            definitive = (
                self._is_definitive_exclusion(note)
                and not self._is_conditional_restriction(note)
            )
            return CheckResult(
                "compatibility-notes",
                "block" if definitive else "warn",
                (
                    f"SKILL.md explicitly excludes {target.get_name()}"
                    if definitive
                    else f"SKILL.md may exclude {target.get_name()}; the wording is ambiguous"
                ),
                details,
            )
        exclusive = self._exclusive_harnesses(note, mentioned)
        if exclusive and target.agent_id not in exclusive:
            labels = ", ".join(exclusive)
            return CheckResult(
                "compatibility-notes",
                "block",
                f"SKILL.md limits compatibility to {labels}, excluding {target.get_name()}",
                details,
            )
        if self._explicit_requirement_pattern.search(note):
            return CheckResult(
                "compatibility-notes",
                "warn",
                "Compatibility field contains an explicit or versioned requirement that needs review",
                details,
            )
        if target.agent_id in mentioned:
            return CheckResult(
                "compatibility-notes",
                "pass",
                f"Compatibility note explicitly includes {target.get_name()}",
                details,
            )
        if mentioned:
            labels = ", ".join(mentioned)
            return CheckResult(
                "compatibility-notes",
                "pass",
                f"SKILL.md mentions {labels}, but does not state that other Harnesses are incompatible",
                details,
            )
        return CheckResult(
            "compatibility-notes",
            "pass",
            "Compatibility field is informational; no target-specific constraint was detected",
            details,
        )

    def _check_document_compatibility(self, body: str, target: AgentAdapter) -> CheckResult:
        """Look for explicit Harness restrictions in the explanatory prose."""
        prose = re.sub(r"```.*?```|~~~.*?~~~", " ", body, flags=re.DOTALL)
        prose = re.sub(r"<!--.*?-->", " ", prose, flags=re.DOTALL)
        clauses = [clause.strip() for clause in re.split(r"[;.!?\n]+", prose) if clause.strip()]
        for clause in clauses:
            required = self._required_by_without_phrase(clause)
            if required:
                if target.agent_id in required:
                    continue
                labels = ", ".join(required)
                return CheckResult(
                    "skill-content-compatibility",
                    "block",
                    f"Skill instructions require {labels}; {target.get_name()} cannot satisfy that Harness requirement",
                    {"targetAgent": target.agent_id, "requiredHarnesses": required, "evidence": clause[:240]},
                )
            if self._target_is_negated(clause, target.agent_id):
                definitive = (
                    self._is_definitive_exclusion(clause)
                    and not self._is_conditional_restriction(clause)
                )
                return CheckResult(
                    "skill-content-compatibility",
                    "block" if definitive else "warn",
                    (
                        f"Skill instructions explicitly exclude {target.get_name()}"
                        if definitive
                        else f"Skill instructions may exclude {target.get_name()}; the wording is ambiguous"
                    ),
                    {"targetAgent": target.agent_id, "evidence": clause[:240]},
                )

            mentioned = [
                agent_id
                for agent_id, aliases in self._target_aliases.items()
                if any(self._contains_term(clause, alias) for alias in aliases)
            ]
            exclusive = self._exclusive_harnesses(clause, mentioned)
            if exclusive and target.agent_id not in exclusive:
                labels = ", ".join(exclusive)
                return CheckResult(
                    "skill-content-compatibility",
                    "block",
                    f"Skill instructions limit use to {labels}, excluding {target.get_name()}",
                    {"targetAgent": target.agent_id, "limitedHarnesses": mentioned, "evidence": clause[:240]},
                )

        return CheckResult(
            "skill-content-compatibility",
            "pass",
            f"No explicit restriction against {target.get_name()} was found in the Skill instructions",
            {"targetAgent": target.agent_id},
        )

    def _exclusive_harnesses(self, text: str, mentioned: list[str]) -> list[str]:
        """Return Harnesses named in a direct Skill-availability restriction.

        A generic word such as ``only`` is not enough: it often scopes a tool,
        command, or exception within an otherwise portable Skill.
        """
        patterns = (
            r"\b(?:works?|runs?|functions?|operates?|is\s+supported|is\s+compatible|"
            r"is\s+available|is\s+designed|is\s+intended)\s+"
            r"(?:only|exclusively|solely)\s+(?:with|in|on|under|for|by)\s+{alias}\b",
            r"\b(?:only|exclusively|solely)\s+"
            r"(?:works?|runs?|functions?|operates?)\s+(?:with|in|on|under|for|by)\s+{alias}\b",
            r"\b(?:only|exclusively|solely)\s+"
            r"(?:compatible\s+with|supported\s+by|available\s+in|designed\s+for|"
            r"intended\s+for|usable\s+by)\s+{alias}\b",
            r"\b(?:for|with|in|on|under|by)\s+{alias}\s+(?:only|exclusively|solely)\b",
            r"\buse\s+(?:this|the)\s+skill\s+(?:only|exclusively|solely)\s+"
            r"(?:with|in|on|under|for|by)\s+{alias}\b",
            r"\b(?:only|exclusively|solely)\s+use\s+(?:this|the)\s+skill\s+"
            r"(?:with|in|on|under|for|by)\s+{alias}\b",
            r"\b(?:only|exclusively|solely)\s+{alias}\s+"
            r"(?:can|may|must|should)\s+(?:use|run|execute|support)\b",
        )
        exclusive: list[str] = []
        for agent_id in mentioned:
            aliases = sorted(self._target_aliases.get(agent_id, (agent_id,)), key=len, reverse=True)
            for alias in aliases:
                escaped = re.escape(alias)
                if any(
                    re.search(pattern.format(alias=escaped), text, re.IGNORECASE)
                    for pattern in patterns
                ):
                    exclusive.append(agent_id)
                    break
        return exclusive

    def _required_by_without_phrase(self, text: str) -> list[str]:
        requirement_pattern = re.compile(
            r"\b(?:cannot|can't|doesn't|does\s+not|won't|will\s+not|unable\s+to)\s+"
            r"(?:work|run|function|operate|execute)\s+without\s+(?:the\s+)?",
            re.IGNORECASE,
        )
        if not requirement_pattern.search(text):
            return []
        return [
            agent_id
            for agent_id, aliases in self._target_aliases.items()
            if any(
                re.search(
                    requirement_pattern.pattern + rf"{re.escape(alias)}(?![\w])",
                    text,
                    re.IGNORECASE,
                )
                for alias in aliases
            )
        ]

    @staticmethod
    def _is_definitive_exclusion(text: str) -> bool:
        return bool(
            re.search(
                r"\b(?:incompatible|unsupported|unavailable|disallowed|excluded|excludes|exclude|blocked)\b|"
                r"\bneither\b|\bnor\b|"
                r"\bno\b.{0,36}\b(?:support|compatibility|availability)\b|"
                r"\b(?:not|never|isn't|aren't|wasn't|weren't|doesn't|does\s+not|don't|do\s+not|"
                r"cannot|can't|won't|will\s+not)\b.{0,48}\b"
                r"(?:supported|compatible|available|allowed|permitted|usable|valid|work|works|run|runs)\b|"
                r"\b(?:supported|compatible|available|allowed|permitted|usable|valid|work|works|run|runs)\b"
                r".{0,48}\b(?:not|never|isn't|aren't|wasn't|weren't|doesn't|does\s+not|don't|do\s+not|"
                r"cannot|can't|won't|will\s+not)\b",
                text,
                re.IGNORECASE,
            )
        )

    @staticmethod
    def _is_conditional_restriction(text: str) -> bool:
        """A Harness limitation conditional on the local environment needs review."""
        return bool(
            re.search(
                r"\b(?:if|unless|when|whenever|outside|inside)\b|"
                r"\bdepending\s+on\b|"
                r"\bon\s+(?:a\s+)?(?:system|machine|environment)s?\s+where\b|"
                r"\bin\s+(?:a\s+)?(?:system|machine|environment)s?\s+where\b",
                text,
                re.IGNORECASE,
            )
        )

    @staticmethod
    def _contains_term(text: str, term: str) -> bool:
        return bool(re.search(rf"(?<![\w]){re.escape(term)}(?![\w])", text, re.IGNORECASE))

    def _target_is_negated(self, note: str, agent_id: str) -> bool:
        aliases = self._target_aliases.get(agent_id, (agent_id,))
        clauses = re.split(
            r"[;.!?]|\b(?:but|however|whereas|while)\b",
            note,
            flags=re.IGNORECASE,
        )
        explicit_negative_after = re.compile(
            r"^\s*(?:(?:is|are|was|were)\s+)?(?:not\s+)?"
            r"(?:unsupported|incompatible|unavailable|disallowed|excluded|blocked)\b|"
            r"^\s*(?:(?:is|are|was|were)\s+)?not\s+"
            r"(?:supported|compatible|available|allowed|permitted|recommended|enabled|usable|valid)\b|"
            r"^\s*(?:isn't|aren't|wasn't|weren't|doesn't|does\s+not|don't|do\s+not|"
            r"cannot|can't|won't|will\s+not)\b|"
            r"^\s*(?:(?:is|are|was|were)\s+)?never\s+"
            r"(?:supported|compatible|available|allowed|permitted|recommended|enabled|usable|valid|works|runs)\b|"
            r"^\s*(?:is|are|was|were)\s+not\b",
            re.IGNORECASE,
        )
        explicit_target_positive_after = re.compile(
            r"^\s*(?:(?:is|are|was|were)\s+)?"
            r"(?:supported|compatible|usable|works?|runs?)\b",
            re.IGNORECASE,
        )
        for clause in clauses:
            target_matches = [
                match
                for alias in aliases
                for match in re.finditer(rf"(?<![\w]){re.escape(alias)}(?![\w])", clause, re.IGNORECASE)
            ]
            if not target_matches:
                continue
            target_matches.sort(key=lambda match: (match.start(), -(match.end() - match.start())))
            non_overlapping_matches: list[re.Match[str]] = []
            for match in target_matches:
                if any(
                    existing.start() <= match.start() and match.end() <= existing.end()
                    for existing in non_overlapping_matches
                ):
                    continue
                non_overlapping_matches.append(match)
            target_matches = non_overlapping_matches

            if re.search(
                r"\bneither\b.{0,96}\bnor\b.{0,48}\b"
                r"(?:supported|compatible|available|allowed|permitted|usable|valid|work|works|run|runs)\b",
                clause,
                re.IGNORECASE,
            ):
                return True

            # A comma/and-separated Harness list can share one trailing negative
            # predicate ("Codex, Claude are unsupported"). Keep the list intact
            # and apply that predicate to every listed Harness.
            shared_negative_lists = self._shared_harness_list_exclusions(clause)
            if any(
                start <= match.start() and match.end() <= end
                for match in target_matches
                for start, end in shared_negative_lists
            ):
                return True

            for match in target_matches:
                after = clause[match.end():]
                before = clause[max(0, match.start() - 64):match.start()]
                if self._negative_support_phrase.search(before):
                    has_other_harness_before = any(
                        other_id != agent_id
                        and any(self._contains_term(before, alias) for alias in other_aliases)
                        for other_id, other_aliases in self._target_aliases.items()
                    )
                    if (
                        has_other_harness_before
                        and before.rstrip().endswith(",")
                        and explicit_target_positive_after.match(after)
                    ):
                        continue
                    return True
                if self._explicit_negative_before(before, after):
                    return True
                if explicit_negative_after.search(after):
                    return True
        return False

    def _explicit_negative_before(self, before: str, after: str) -> bool:
        """Recognize a negation directly attached to the Harness mention.

        Do not let a nearby phrase such as ``without a Python symlink`` taint a
        later mention of Claude or another Harness in the same sentence.
        """
        if re.search(
            r"\b(?:incompatible|unsupported|unavailable|disallowed|excluded|blocked)\s+"
            r"(?:with|for|in|on|by)?\s*$",
            before,
            re.IGNORECASE,
        ):
            return True
        if not re.search(
            r"\b(?:avoid|excluding|excludes?|except|without|not|never|no|neither|nor)\s*$",
            before,
            re.IGNORECASE,
        ):
            return False
        return bool(
            re.match(
                r"^\s*(?:[,;.!?)]|$|(?:support|compatibility|compatible|supported|available|"
                r"allowed|permitted|usable|valid|works?|runs?)\b)",
                after,
                re.IGNORECASE,
            )
        )

    _negative_support_phrase = re.compile(
        r"\b(?:no|not|never)\s+(?:(?:any|the)\s+)?"
        r"(?:support(?:ed)?|compatibility|compatible)\s+(?:for|with|by)\b|"
        r"\bneither\b.{0,64}\bnor\s*$",
        re.IGNORECASE,
    )
    def _shared_harness_list_exclusions(self, clause: str) -> list[tuple[int, int]]:
        all_aliases = sorted(
            {alias for aliases in self._target_aliases.values() for alias in aliases},
            key=len,
            reverse=True,
        )
        alias_pattern = "(?:" + "|".join(re.escape(alias) for alias in all_aliases) + ")"
        list_pattern = re.compile(
            rf"(?<![\w]){alias_pattern}(?:(?:\s*,\s*(?:(?:and|or)\s+)?|"
            rf"\s+(?:and|or)\s+|\s*&\s*){alias_pattern})+(?![\w])",
            re.IGNORECASE,
        )
        negative_predicate = re.compile(
            r"^\s*(?:(?:is|are|was|were)\s+)?(?:not|never)\s+"
            r"(?:supported|compatible|available|allowed|permitted|recommended|enabled|usable|valid)\b|"
            r"^\s*(?:(?:is|are|was|were)\s+)?(?:not\s+)?"
            r"(?:unsupported|incompatible|unavailable|disallowed|excluded|blocked)\b|"
            r"^\s*(?:(?:is|are|was|were)\s+)?not\s+"
            r"(?:supported|compatible|available|allowed|permitted|recommended|enabled|usable|valid)\b|"
            r"^\s*(?:cannot|can't|doesn't|does\s+not|don't|do\s+not|won't|will\s+not|unable\s+to)\b",
            re.IGNORECASE,
        )
        return [
            (match.start(), match.end())
            for match in list_pattern.finditer(clause)
            if negative_predicate.match(clause[match.end():])
        ]

    @staticmethod
    def _raw_frontmatter(text: str) -> str:
        lines = text.splitlines()
        if not lines or not lines[0].startswith("---"):
            return ""
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                return "\n".join(lines[1:index])
        return ""

    @classmethod
    def _compatibility_value(cls, frontmatter: dict, raw_frontmatter: str) -> str:
        parsed = str(frontmatter.get("compatibility") or "").strip()
        if parsed and parsed not in {"|", "|-", "|+", ">", ">-", ">+"}:
            return parsed

        lines = raw_frontmatter.splitlines()
        for index, line in enumerate(lines):
            match = re.match(r"^compatibility:\s*(.*)$", line)
            if not match:
                continue
            marker = match.group(1).strip()
            if not re.fullmatch(r"[|>](?:[1-9])?[+-]?", marker):
                return parsed or marker
            content: list[str] = []
            for following in lines[index + 1:]:
                if following.strip() and not following[:1].isspace():
                    break
                if following.strip():
                    content.append(following.strip())
            return " ".join(content).strip()
        return parsed

    @staticmethod
    def _inspect_references(skill_root: Path, references: list[str]) -> dict[str, list[str]]:
        root = skill_root.resolve()
        present: list[str] = []
        missing: list[str] = []
        outside: list[str] = []
        for reference in references:
            normalized = reference.replace("\\", "/")
            if re.match(r"^[A-Za-z]:/", normalized) or normalized.startswith("/"):
                outside.append(reference)
                continue
            candidate = (root / normalized).resolve()
            if not candidate.is_relative_to(root):
                outside.append(reference)
            elif candidate.exists():
                present.append(reference)
            else:
                missing.append(reference)
        return {"present": present, "missing": missing, "outside": outside}

    @classmethod
    def _referenced_resources(cls, body: str) -> list[str]:
        found: list[str] = []
        seen: set[str] = set()
        candidates = [match.group(0) for match in cls._local_reference_pattern.finditer(body)]
        candidates.extend(match.group(0) for match in cls._file_reference_pattern.finditer(body))
        candidates.extend(match.group(1).strip() for match in cls._markdown_link_pattern.finditer(body))
        for candidate in candidates:
            value = candidate.strip().strip("<>").rstrip(".,;:!?。；，")
            if value.casefold() == "skill.md" or value.startswith(("#", "http://", "https://", "mailto:")):
                continue
            value = value.split("#", 1)[0].split("?", 1)[0]
            if not value:
                continue
            key = value.casefold()
            if key not in seen:
                seen.add(key)
                found.append(value)
        return found

    @staticmethod
    def _skill_md_path(skill: Skill) -> Path:
        path = Path(skill.path).resolve()
        return find_skill_md(path) or find_skill_md(path.parent if path.name.casefold() == "skill.md" else path) or path / "SKILL.md"
