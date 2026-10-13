"""Shared, bounded discovery helpers for portable Skill documents."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator


SKILL_DOCUMENT_NAME = "skill.md"
MAX_SKILL_SEARCH_DEPTH = 8
MAX_SKILL_SEARCH_DIRECTORIES = 20_000
IGNORED_SEARCH_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "vendor",
    "__pycache__",
    ".cache",
    "cache",
    "dist",
    "build",
    "coverage",
    ".next",
    ".nuxt",
}


def find_skill_md(skill_path: str | Path) -> Path | None:
    """Find the direct Skill document in a Skill directory, case-insensitively.

    A document path is accepted as-is when its filename is a case-insensitive
    match for ``SKILL.md``. For directory inputs, an exact canonical filename
    wins; otherwise a single case-insensitive match is accepted. Ambiguous
    case variants are left unresolved instead of choosing one silently.
    """
    path = Path(skill_path)
    if path.is_file():
        return path if path.name.casefold() == SKILL_DOCUMENT_NAME and not path.is_symlink() else None
    if not path.is_dir():
        return None
    try:
        candidates = [
            entry
            for entry in path.iterdir()
            if entry.name.casefold() == SKILL_DOCUMENT_NAME
            and not entry.is_symlink()
            and entry.is_file()
        ]
    except OSError:
        return None
    if not candidates:
        return None
    candidates.sort(key=lambda entry: (entry.name != "SKILL.md", entry.name.casefold(), entry.name))
    canonical = next((entry for entry in candidates if entry.name == "SKILL.md"), None)
    if canonical is not None:
        return canonical
    return candidates[0] if len(candidates) == 1 else None


def iter_skill_md_files(
    root: str | Path,
    *,
    max_depth: int = MAX_SKILL_SEARCH_DEPTH,
    max_directories: int = MAX_SKILL_SEARCH_DIRECTORIES,
    include_disabled: bool = False,
) -> Iterator[Path]:
    """Yield Skill documents under a Harness root using a bounded deep scan.

    A directory containing a Skill document is treated as one Skill bundle;
    traversal does not continue into its supporting-file subdirectories.
    Common generated/dependency directories and symlinks are skipped.
    """
    root_path = Path(root)
    if root_path.is_symlink():
        return
    if root_path.is_file():
        document = find_skill_md(root_path)
        if document is not None:
            yield document
        return
    if not root_path.is_dir():
        return

    stack: list[tuple[Path, int]] = [(root_path, 0)]
    visited: set[str] = set()
    scanned = 0
    while stack and scanned < max_directories:
        directory, depth = stack.pop()
        try:
            resolved_key = os.path.normcase(str(directory.resolve(strict=False)))
        except OSError:
            continue
        if resolved_key in visited:
            continue
        visited.add(resolved_key)
        scanned += 1

        document = find_skill_md(directory)
        if document is not None:
            yield document
            continue
        if depth >= max_depth:
            continue
        try:
            entries = sorted(directory.iterdir(), key=lambda entry: (entry.name.casefold(), entry.name))
        except OSError:
            continue
        child_directories: list[Path] = []
        for entry in entries:
            if entry.name.casefold() in IGNORED_SEARCH_DIRECTORIES or entry.is_symlink():
                continue
            if not include_disabled and entry.name.casefold().endswith("_disabled"):
                continue
            try:
                if entry.is_dir():
                    child_directories.append(entry)
            except OSError:
                continue
        stack.extend((child, depth + 1) for child in reversed(child_directories))


def iter_skill_dirs(root: str | Path, *, include_disabled: bool = False) -> Iterator[Path]:
    """Yield the parent directory of each discovered Skill document."""
    for document in iter_skill_md_files(root, include_disabled=include_disabled):
        yield document.parent


def has_skill_md_symlink(skill_dir: str | Path) -> bool:
    """Return whether a Skill directory contains a symlink named SKILL.md."""
    directory = Path(skill_dir)
    try:
        return any(
            entry.name.casefold() == SKILL_DOCUMENT_NAME and entry.is_symlink()
            for entry in directory.iterdir()
        )
    except OSError:
        return False
