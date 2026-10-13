"""SKILL.md parser.

Phase 2 implementation. Parses the YAML-ish frontmatter and Markdown body of
a ``SKILL.md`` file without requiring external YAML dependencies.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..skill_files import find_skill_md

STOPWORDS = {
    "about", "after", "again", "also", "and", "any", "are", "because", "been",
    "before", "being", "between", "both", "but", "can", "could", "did", "do",
    "does", "doing", "down", "during", "each", "few", "for", "from", "further",
    "had", "has", "have", "having", "he", "her", "here", "hers", "herself",
    "him", "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its",
    "itself", "just", "me", "more", "most", "my", "myself", "no", "nor", "not",
    "now", "of", "off", "on", "once", "only", "or", "other", "our", "ours",
    "ourselves", "out", "over", "own", "same", "she", "should", "so", "some",
    "such", "than", "that", "the", "their", "theirs", "them", "themselves",
    "then", "there", "these", "they", "this", "those", "through", "to", "too",
    "under", "until", "up", "very", "was", "we", "were", "what", "when",
    "where", "which", "while", "who", "whom", "why", "will", "with", "you",
    "your", "yours", "yourself", "yourselves",
}


class SkillParser:
    """Parses a Skill from its ``SKILL.md`` file."""

    def parse(self, skill_path: str | Path) -> dict:
        """Parse a SKILL.md file or a Skill directory.

        Returns a dictionary with normalized keys:

        - name
        - display_name
        - description
        - title
        - category
        - tags
        - version
        - when_to_use
        - main_purpose
        - body
        - warnings
        """
        path = Path(skill_path)
        if path.is_dir():
            path = find_skill_md(path) or path / "SKILL.md"
        if not path.is_file():
            return {
                "name": path.parent.name,
                "display_name": path.parent.name,
                "description": "",
                "title": "",
                "category": "",
                "tags": [],
                "version": None,
                "when_to_use": "",
                "main_purpose": "",
                "body": "",
                "warnings": [f"{path}: SKILL.md not found"],
            }

        text = path.read_text(encoding="utf-8", errors="replace")
        frontmatter, body, warnings = self._split_frontmatter(text)
        name = str(frontmatter.get("name") or path.parent.name or "skill").strip()
        display_name = str(
            frontmatter.get("display_name")
            or frontmatter.get("displayName")
            or frontmatter.get("title")
            or name.replace("-", " ").title()
        ).strip()
        description = str(frontmatter.get("description") or "").strip()
        category = str(frontmatter.get("category") or "").strip()
        version = frontmatter.get("version")
        if version is not None:
            version = str(version).strip() or None

        tags = self._extract_tags(frontmatter.get("tags"))
        if not tags:
            tags = self._keywords_from_text(f"{description} {body}")

        title = self._extract_title(body)
        main_purpose = self._extract_main_purpose(body, description)
        when_to_use = str(
            frontmatter.get("when_to_use")
            or frontmatter.get("whenToUse")
            or ""
        ).strip()

        return {
            "name": name,
            "display_name": display_name,
            "description": description,
            "title": title,
            "category": category,
            "tags": tags,
            "version": version,
            "when_to_use": when_to_use,
            "main_purpose": main_purpose,
            "body": body,
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # Frontmatter / Markdown helpers
    # ------------------------------------------------------------------
    def _split_frontmatter(self, text: str) -> tuple[dict, str, list[str]]:
        warnings: list[str] = []
        if not text.startswith("---"):
            return {}, text, warnings

        lines = text.splitlines(keepends=True)
        end_index: int | None = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end_index = i
                break
        if end_index is None:
            warnings.append("frontmatter is not closed; treating file as plain Markdown")
            return {}, text, warnings

        fm_text = "".join(lines[1:end_index])
        body = "".join(lines[end_index + 1:])
        data = self._parse_frontmatter_lines(fm_text)
        return data, body, warnings

    def _parse_frontmatter_lines(self, fm_text: str) -> dict:
        data: dict = {}
        metadata_indent: int | None = None
        for raw_line in fm_text.splitlines():
            indent = len(raw_line) - len(raw_line.lstrip())
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
            if not match:
                continue
            key = match.group(1)
            value = match.group(2).strip()
            if indent == 0:
                metadata_indent = None
                if key == "metadata" and not value:
                    data[key] = {}
                    metadata_indent = indent
                else:
                    data[key] = self._coerce_value(value)
            elif metadata_indent is not None and indent > metadata_indent:
                data.setdefault("metadata", {})[key] = self._coerce_value(value)
        return data

    def _coerce_value(self, value: str):
        if not value:
            return ""
        if value.startswith('"') and value.endswith('"') and len(value) >= 2:
            return value[1:-1]
        if value.startswith("'") and value.endswith("'") and len(value) >= 2:
            return value[1:-1]
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1]
            parts = [p.strip().strip('"').strip("'") for p in inner.split(",")]
            return [p for p in parts if p]
        return value

    def _extract_tags(self, raw_tags) -> list[str]:
        if raw_tags is None:
            return []
        if isinstance(raw_tags, list):
            tags = [str(t).strip() for t in raw_tags if str(t).strip()]
        else:
            text = str(raw_tags)
            tags = [p.strip() for p in re.split(r"[,，]", text) if p.strip()]
        # De-duplicate while preserving order.
        seen: set[str] = set()
        result: list[str] = []
        for tag in tags:
            key = tag.lower()
            if key not in seen:
                seen.add(key)
                result.append(tag)
        return result

    def _keywords_from_text(self, text: str, limit: int = 6) -> list[str]:
        words = re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", text)
        result: list[str] = []
        seen: set[str] = set()
        for word in words:
            low = word.lower()
            if low in STOPWORDS or low in seen:
                continue
            seen.add(low)
            result.append(word)
            if len(result) >= limit:
                break
        return result

    def _extract_title(self, body: str) -> str:
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                return stripped.lstrip("#").strip()
        return ""

    @staticmethod
    def _is_metadata_paragraph(text: str) -> bool:
        return bool(
            re.match(
                r"(?i)^(?:author(?:\s*/\s*author)?|作者(?:\s*/\s*author)?|英文名|english name|来源识别|source identification)\s*[:：]",
                text.strip(),
            )
            or re.match(r"(?i)^(?:adapted from|inspired by)\b", text.strip())
            or re.match(r"(?i)^by\s+[A-Z][\w.-]+(?:\s+[A-Z][\w.-]+)?(?:[.:]|$)", text.strip())
        )

    def _extract_main_purpose(self, body: str, description: str) -> str:
        for paragraph in re.split(r"\n\s*\n", body.strip()):
            lines = [
                line.strip()
                for line in paragraph.splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            clean = " ".join(lines)
            clean = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", clean)
            clean = re.sub(r"[*_`>#-]", "", clean).strip()
            if clean and not clean.startswith("```") and not self._is_metadata_paragraph(clean):
                if len(clean) > 1000:
                    clipped = clean[:1000]
                    clean = clipped.rsplit(" ", 1)[0] if " " in clipped else clipped
                return clean
        return description[:200]
