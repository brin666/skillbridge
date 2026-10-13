"""Skill source detector.

Attempts to detect where a Skill came from by reading local files only.
It never guesses a GitHub URL.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

GITHUB_URL_RE = re.compile(
    r"https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)"
)
GITHUB_SSH_RE = re.compile(
    r"(?:git@github\.com:|ssh://git@github\.com/|ssh://github\.com/)([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)"
)


class SourceDetector:
    """Detects Skill source from local metadata files."""

    def detect(self, skill_path: str | Path) -> dict:
        """Return a source dict, e.g. ``{"type": "github", "url": "..."}``.

        If no reliable source is found, returns ``{"type": "unknown"}``.
        """
        path = Path(skill_path)
        if path.is_file():
            skill_dir = path.parent
        else:
            skill_dir = path

        # 1. A Git remote inside the Skill directory itself. A remote found
        # only in an enclosing project is not reliable Skill provenance.
        git_url = self._detect_from_git(skill_dir)
        if git_url:
            return self._normalize_git_url(git_url)

        # 2. metadata.json
        source = self._detect_from_json(skill_dir / "metadata.json")
        if source:
            return source

        # 3. README.md
        source = self._detect_from_readme(skill_dir / "README.md")
        if source:
            return source

        # 4. package.json
        source = self._detect_from_json(skill_dir / "package.json")
        if source:
            return source

        return {"type": "unknown"}

    # ------------------------------------------------------------------
    # .git/config
    # ------------------------------------------------------------------
    def _detect_from_git(self, skill_dir: Path) -> str | None:
        git_config = skill_dir / ".git" / "config"
        return self._read_git_remote_url(git_config) if git_config.is_file() else None

    def _read_git_remote_url(self, git_config: Path) -> str | None:
        try:
            lines = git_config.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return None
        in_origin = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("["):
                in_origin = "[remote " in stripped and "origin" in stripped
                continue
            if in_origin and "=" in stripped:
                key, value = stripped.split("=", 1)
                if key.strip() == "url":
                    return value.strip()
        return None

    # ------------------------------------------------------------------
    # JSON metadata
    # ------------------------------------------------------------------
    def _detect_from_json(self, json_path: Path) -> dict | None:
        if not json_path.is_file():
            return None
        try:
            data = json.loads(json_path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            return None

        candidates = []
        if isinstance(data, dict):
            for key in ("source", "repository", "repo", "homepage", "url", "git"):
                value = data.get(key)
                if isinstance(value, str):
                    candidates.append(value)
                elif isinstance(value, dict):
                    for sub_key in ("url", "repository", "web", "html_url"):
                        if isinstance(value.get(sub_key), str):
                            candidates.append(value[sub_key])
        for candidate in candidates:
            url = self._normalize_git_url(candidate)
            if url and url.get("type") in {"github", "git"}:
                return url
        return None

    # ------------------------------------------------------------------
    # README
    # ------------------------------------------------------------------
    def _detect_from_readme(self, readme_path: Path) -> dict | None:
        if not readme_path.is_file():
            return None
        try:
            text = readme_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

        for match in GITHUB_URL_RE.finditer(text):
            return self._normalize_git_url(match.group(0))
        return None

    # ------------------------------------------------------------------
    # URL normalization
    # ------------------------------------------------------------------
    def _normalize_git_url(self, value: str) -> dict:
        value = value.strip().strip("'\"")
        if not value:
            return {"type": "unknown"}

        # SSH GitHub forms.
        ssh_match = GITHUB_SSH_RE.search(value)
        if ssh_match:
            owner, repo = ssh_match.group(1), ssh_match.group(2)
            repo = repo[:-4] if repo.endswith(".git") else repo
            return {"type": "github", "url": f"https://github.com/{owner}/{repo}"}

        # HTTPS/HTTP GitHub forms.
        http_match = GITHUB_URL_RE.search(value)
        if http_match:
            owner, repo = http_match.group(1), http_match.group(2)
            repo = repo[:-4] if repo.endswith(".git") else repo
            return {"type": "github", "url": f"https://github.com/{owner}/{repo}"}

        # Any other explicit Git remote: keep the original URL as type git.
        if value.startswith(("git@", "ssh://", "http://", "https://", "git://")):
            return {"type": "git", "url": value}

        # Not a URL we can confirm.
        return {"type": "unknown"}
