"""Extract documented Skill capabilities without inventing missing ones."""

from __future__ import annotations

import re


_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+|>\s*)")
_CAPABILITY_HEADINGS = {
    "capability",
    "capabilities",
    "core capabilities",
    "key capabilities",
    "skill capabilities",
    "function",
    "functions",
    "core functions",
    "key functions",
    "skill functions",
    "feature",
    "features",
    "core features",
    "key features",
    "skill features",
    "what this skill does",
    "what this skill can do",
    "what i can do",
    "what it can do",
    "what it delivers",
    "when to use",
    "when to use this skill",
    "use cases",
    "supported scenarios",
    "key actions",
    "supported actions",
    "purpose",
    "main purpose",
    "主要功能",
    "核心功能",
    "功能列表",
    "功能概览",
    "功能",
    "核心能力",
    "主要能力",
    "能力",
    "能做什么",
    "主要用途",
    "核心用途",
    "适用场景",
    "使用场景",
    "何时使用",
    "可执行操作",
    "支持的场景",
}
_CAPABILITY_PREFIXES = (
    "core capabilities ",
    "key capabilities ",
    "skill capabilities ",
    "core functions ",
    "key functions ",
    "skill functions ",
)
_EXCLUDED_HEADINGS = (
    "prerequisite",
    "requirement",
    "installation",
    "setup",
    "authentication",
    "security",
    "hard rule",
    "constraint",
    "limitation",
    "troubleshooting",
    "reference",
    "appendix",
    "when not to use",
    "do not use",
    "don't use",
    "avoid when",
    "限制",
    "前置条件",
    "安装",
    "认证",
    "安全",
    "故障排除",
    "参考资料",
    "不适用场景",
)
class FeatureExtractor:
    """Prefer explicit capability sections; avoid treating procedure steps as features."""

    def extract(self, parsed: dict, referenced_markdown: list[str] | None = None) -> list[str]:
        body = str(parsed.get("body") or "")
        documents = [body, *(referenced_markdown or [])]
        explicit: list[str] = []
        for document in documents:
            for title, section_body in self._sections(document):
                if self._is_capability_heading(title):
                    explicit.extend(self._section_items(self._without_excluded_subsections(section_body)))
        features = self._unique(explicit)
        if features:
            return features

        # The introductory purpose can document several distinct capabilities.
        # Keep those complete statements without mistaking workflow steps for features.
        # Frontmatter descriptions are usually the Skill's user-facing capability
        # contract. Combine them with the concise body purpose, while filtering
        # operational notes that describe how an agent should communicate.
        purpose_items: list[str] = []
        for source in (
            str(parsed.get("description") or ""),
            str(parsed.get("when_to_use") or ""),
            str(parsed.get("main_purpose") or ""),
        ):
            purpose_items.extend(
                item for item in self._paragraphs(source) if not self._is_excluded_item(item)
            )
        return self._unique(purpose_items)

    @staticmethod
    def _sections(markdown: str) -> list[tuple[str, str]]:
        lines = markdown.splitlines()
        headings: list[tuple[int, int, str]] = []
        for index, line in enumerate(lines):
            match = _HEADING.match(line.strip())
            if match:
                headings.append((index, len(match.group(1)), match.group(2).strip()))
        sections: list[tuple[str, str]] = []
        for heading_index, (line_index, level, title) in enumerate(headings):
            end = len(lines)
            for next_index, next_level, _ in headings[heading_index + 1:]:
                if next_level <= level:
                    end = next_index
                    break
            sections.append((title, "\n".join(lines[line_index + 1:end])))
        return sections

    @staticmethod
    def _normalize_heading(title: str) -> str:
        title = re.sub(r"[`*_]", "", title).casefold()
        return re.sub(r"[^\w\u4e00-\u9fff]+", " ", title).strip()

    @classmethod
    def _without_excluded_subsections(cls, text: str) -> str:
        kept: list[str] = []
        excluded_level: int | None = None
        for line in text.splitlines():
            match = _HEADING.match(line.strip())
            if excluded_level is not None:
                if not match or len(match.group(1)) > excluded_level:
                    continue
                excluded_level = None
            if match and cls._is_excluded_heading(match.group(2)):
                excluded_level = len(match.group(1))
                continue
            kept.append(line)
        return "\n".join(kept)

    @classmethod
    def _is_capability_heading(cls, title: str) -> bool:
        normalized = cls._normalize_heading(title)
        if cls._is_excluded_heading(title):
            return False
        return normalized in _CAPABILITY_HEADINGS or normalized.startswith(_CAPABILITY_PREFIXES)

    @classmethod
    def _is_excluded_heading(cls, title: str) -> bool:
        normalized = cls._normalize_heading(title)
        return any(term in normalized for term in _EXCLUDED_HEADINGS)

    def _section_items(self, text: str) -> list[str]:
        # Capability sections often mix a short explanation with a list. Keep
        # both: dropping the prose would silently hide documented capabilities.
        candidates = [*self._paragraphs(text), *self._list_items(text)]
        return self._unique([item for item in candidates if not self._is_excluded_item(item)])

    @staticmethod
    def _is_metadata_item(item: str) -> bool:
        text = item.strip()
        return bool(
            re.match(
                r"(?i)^(?:author(?:\s*/\s*author)?|作者(?:\s*/\s*author)?|英文名|english name|来源识别|source identification)\s*[:：]",
                text,
            )
            or re.match(r"(?i)^(?:adapted from|inspired by)\b", text)
            or re.match(r"(?i)^by\s+[A-Z][\w.-]+(?:\s+[A-Z][\w.-]+)?(?:[.:]|$)", text)
            or re.match(
                r"(?i)^(?:when this skill is first invoked|on first invocation|respond only with|do not provide any other information until)\b",
                text,
            )
        )

    @classmethod
    def _is_excluded_item(cls, item: str) -> bool:
        text = item.strip()
        return bool(
            cls._is_metadata_item(text)
            or re.match(r"(?i)^(?:do not use|don't use|do not|don't|never use|not for|avoid\b|不适用|不要使用)", text)
            or re.match(r"(?i)^(?:on|at|upon) activation\b", text)
            or re.search(r"(?i)\bsee .{0,120}\bskill instead\b", text)
            or re.search(r"(?i)\b(?:does not|do not|did not|cannot|can't|won't|isn't|aren't|shouldn't|must not)\b", text)
        )

    def _list_items(self, text: str) -> list[str]:
        items: list[str] = []
        current: list[str] = []
        in_code = False

        def flush() -> None:
            if current:
                item = self._clean_item(" ".join(current))
                if item:
                    items.append(item)
                current.clear()

        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                flush()
                in_code = not in_code
                continue
            if in_code:
                continue
            if _LIST_ITEM.match(line):
                flush()
                current.append(_LIST_ITEM.sub("", line, count=1).strip())
            elif current and line[:1].isspace() and stripped and not stripped.startswith(("|", "#")):
                # Markdown permits a list item's sentence to wrap onto indented
                # continuation lines. Keep it as one complete capability.
                current.append(stripped)
            else:
                flush()
        flush()
        return items

    def _paragraphs(self, text: str) -> list[str]:
        paragraphs: list[list[str]] = []
        current: list[str] = []
        in_code = False
        in_list = False

        def flush() -> None:
            if current:
                paragraphs.append(current.copy())
                current.clear()

        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                flush()
                in_code = not in_code
                in_list = False
                continue
            if in_code:
                continue
            if _LIST_ITEM.match(line):
                flush()
                in_list = True
                continue
            if not stripped:
                flush()
                continue
            if stripped.startswith(("|", "#")):
                flush()
                in_list = False
                continue
            if in_list and line[:1].isspace():
                # Continuation text belongs to the preceding list item; it is
                # joined by _list_items and must not become a separate feature.
                continue
            if in_list:
                in_list = False
                flush()
            if not stripped:
                continue
            current.append(stripped)
        flush()

        items: list[str] = []
        for paragraph in paragraphs:
            joined = re.sub(r"\s+", " ", " ".join(paragraph)).strip()
            parts = re.split(r"(?<=[.!?])\s+|(?<=[。！？])", joined)
            items.extend(item for item in (self._clean_item(part) for part in parts) if item)
        return items

    @staticmethod
    def _clean_item(item: str) -> str:
        negative = re.search(
            r"(?i)(?:\s+|[;:,.，；]+)(?:do not use|don't use|never use|avoid when|avoid|not for)\b",
            item,
        )
        if not negative:
            negative = re.search(
                r"(?i)(?:,|;|\s)\s*(?:but|however)\b(?=.{0,180}\b(?:never|not|cannot)\b)",
                item,
            )
        if negative:
            item = item[:negative.start()].rstrip(" ;:,.，；")
        elif re.match(r"(?i)^(?:do not use|don't use|never use|avoid when|avoid|not for)\b", item.strip()):
            return ""
        item = re.sub(r"(?:[；;，,。.]?\s*)(?:不适用|不适合|不要使用|不要用于|避免使用).*$", "", item)
        if re.match(r"(?i)^keywords?\s*:", item.strip()) or re.match(
            r"(?i)^(?:use when the user asks to|use this skill when the user asks to)\s*:?\s*$",
            item.strip(),
        ) or re.match(
            r"(?i)^(?:use(?: this(?: skill)?)?\s+(?:when|whenever|if)\b|when the user asks\b).*(?::|\bto)\s*$",
            item.strip(),
        ):
            return ""
        item = re.sub(r"<!--.*?-->", " ", item)
        item = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", item)
        item = re.sub(r"[`*_]", "", item)
        item = re.sub(r"\s+", " ", item).strip(" \t-:;，,。.")
        if not item or item.startswith(("http://", "https://")):
            return ""
        if len(item) > 500:
            item = item[:500].rsplit(" ", 1)[0]
        return item

    @staticmethod
    def _unique(items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            key = re.sub(r"\W+", " ", item.casefold()).strip()
            if key and key not in seen:
                seen.add(key)
                result.append(item)
        return result
