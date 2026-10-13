"""Bilingual summary manager."""

from __future__ import annotations

import re
from pathlib import Path

from .feature_extractor import FeatureExtractor
from .rule_provider import RuleSummaryProvider

SUMMARY_PIPELINE_VERSION = 25
_MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
_MARKDOWN_PATH = re.compile(r"(?<![\w./-])((?:[\w.-]+/)+[\w.-]+\.md|[\w.-]+\.md)", re.IGNORECASE)
_MAX_REFERENCE_FILE_BYTES = 256 * 1024
_MAX_REFERENCE_TOTAL_BYTES = 1024 * 1024
_MAX_REFERENCE_FILES = 16


class SummaryManager:
    """Generates and stores bilingual Skill summaries."""

    def __init__(self) -> None:
        self.rule = RuleSummaryProvider()
        self.feature_extractor = FeatureExtractor()

    def generate_summary(self, description: str, content: str, target_language: str) -> str:
        return self.rule.generate(description, content, target_language)

    def analyze(self, parsed: dict, skill_dir: str | Path | None = None) -> dict:
        raw_description = str(parsed.get("description") or "").strip()
        short_description = self._first_sentence(raw_description)
        if self.feature_extractor._is_metadata_item(short_description):
            short_description = ""
        main_purpose = str(parsed.get("main_purpose") or "").strip()
        if self.feature_extractor._is_metadata_item(main_purpose):
            main_purpose = ""
            parsed = {**parsed, "main_purpose": ""}
        description = short_description
        if main_purpose and (len(short_description) > 150 or not short_description):
            description = self._first_sentence(main_purpose)
        if len(description) > 125:
            description = re.sub(r"\s*\([^)]*\)", "", description).strip()
            description = re.split(r"(?i)\s+(?:such as|for example|including)\s+", description, maxsplit=1)[0].strip()
        body = str(parsed.get("body") or "")
        references = self._read_referenced_markdown(skill_dir, f"{raw_description}\n{body}") if skill_dir is not None else []
        if skill_dir is not None and not short_description:
            readme = self._readme_text(Path(skill_dir) / "README.md")
            if readme:
                references.append(readme)
                intro = self._readme_intro(readme)
                if intro and not parsed.get("main_purpose"):
                    parsed = {**parsed, "main_purpose": intro}
                    if not description:
                        description = self._first_sentence(intro)
        features = self.feature_extractor.extract(parsed, references)
        description = description or self._first_sentence(str(parsed.get("main_purpose") or "")) or (features[0] if features else "")
        summaries = (
            {
                "zh-CN": self.generate_summary(description, body, "zh-CN"),
                "en-US": self.generate_summary(description, body, "en-US"),
            }
            if description
            else {"zh-CN": "未知", "en-US": "Unknown"}
        )
        summaries["zh-CN"] = summaries["zh-CN"] or "未知"
        summaries["en-US"] = summaries["en-US"] or "Unknown"
        localized_features = {
            "zh-CN": [self.rule.generate(feature, "", "zh-CN") for feature in features],
            "en-US": [self.rule.generate(feature, "", "en-US") for feature in features],
        }
        if not self.rule._contains_cjk(summaries["zh-CN"]):
            for feature in localized_features["zh-CN"]:
                cjk_count = len(re.findall(r"[\u4e00-\u9fff]", feature))
                latin_count = len(re.findall(r"[A-Za-z]", feature))
                if len(feature) <= 160 and cjk_count >= 4 and cjk_count / max(cjk_count + latin_count, 1) >= 0.4:
                    summaries["zh-CN"] = feature
                    break
        return {"summaries": summaries, "features": localized_features}

    def generate_bilingual(self, parsed: dict, skill_dir: str | Path | None = None) -> dict:
        return self.analyze(parsed, skill_dir)["summaries"]

    def generate_features(self, parsed: dict, skill_dir: str | Path | None = None) -> dict[str, list[str]]:
        return self.analyze(parsed, skill_dir)["features"]

    def generate(self, parsed: dict, skill_dir: str | Path | None = None) -> str:
        """Backward-compatible single summary (Chinese preferred)."""
        summaries = self.generate_bilingual(parsed, skill_dir)
        return summaries.get("zh-CN") or summaries.get("en-US") or ""

    @staticmethod
    def _readme_text(readme_path: Path) -> str:
        if not readme_path.is_file():
            return ""
        try:
            if readme_path.stat().st_size > _MAX_REFERENCE_FILE_BYTES:
                return ""
            text = readme_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return text

    @staticmethod
    def _readme_intro(text: str) -> str:
        paragraphs = re.split(r"\n\s*\n", text)
        for paragraph in paragraphs:
            lines = [
                line.strip()
                for line in paragraph.splitlines()
                if line.strip()
                and not line.strip().startswith(("#", "!", "<", "[!"))
            ]
            clean = re.sub(r"\s+", " ", " ".join(lines)).strip()
            if clean and not clean.startswith(("http://", "https://")):
                return clean
        return ""

    @staticmethod
    def _first_sentence(text: str) -> str:
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return ""
        sentence = re.split(r"(?<=[.!?。！？])\s+", text, maxsplit=1)[0].strip()
        sentence = re.sub(
            r"(?i)(?:\s+|[;:,.，；]+)(?:do not use|don't use|never use|avoid when|avoid|not for)\b.*$",
            "",
            sentence,
        )
        sentence = re.sub(r"(?:[；;，,。.]?\s*)(?:不适用|不适合|不要使用|不要用于|避免使用).*$", "", sentence)
        if re.match(r"(?i)^(?:do not use|don't use|never use|avoid when|avoid|not for)\b", sentence):
            return ""
        return sentence.strip()

    @classmethod
    def _read_referenced_markdown(cls, skill_dir: str | Path | None, text: str) -> list[str]:
        if skill_dir is None:
            return []
        root = Path(skill_dir).resolve()
        candidates: list[str] = []
        for match in _MARKDOWN_LINK.finditer(text):
            target = match.group(1).strip().strip("<>\"'").split("#", 1)[0].split("?", 1)[0]
            if target and "://" not in target:
                candidates.append(target)
        candidates.extend(match.group(1) for match in _MARKDOWN_PATH.finditer(text))

        seen: set[Path] = set()
        documents: list[str] = []
        total_bytes = 0
        for candidate in candidates:
            relative = candidate.replace("\\", "/")
            while relative.startswith("./"):
                relative = relative[2:]
            if not relative or relative.startswith(("/", "../")):
                continue
            try:
                path = (root / relative).resolve(strict=True)
                path.relative_to(root)
                if path in seen or not path.is_file() or path.suffix.casefold() != ".md" or path.name.casefold() == "skill.md":
                    continue
                size = path.stat().st_size
                if size > _MAX_REFERENCE_FILE_BYTES or total_bytes + size > _MAX_REFERENCE_TOTAL_BYTES:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                continue
            seen.add(path)
            total_bytes += size
            documents.append(text)
            if len(documents) >= _MAX_REFERENCE_FILES:
                break
        return documents
