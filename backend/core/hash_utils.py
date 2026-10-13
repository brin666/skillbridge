"""Unified content hash for Skill directories."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import NamedTuple

from ..skill_files import find_skill_md

IGNORED_PARTS = {".git", "__pycache__", ".venv", "node_modules"}


class SkillFileMetadata(NamedTuple):
    """Cheap-to-compute metadata used to validate a cached Skill scan."""

    files: list[str]
    signature: str
    latest_mtime: float


def _iter_skill_files(root: Path):
    """Yield files while pruning ignored directories before traversal."""
    try:
        for directory, dirnames, filenames in os.walk(root, topdown=True):
            dirnames[:] = sorted(
                (name for name in dirnames if name not in IGNORED_PARTS),
                key=str.casefold,
            )
            for filename in sorted(filenames, key=str.casefold):
                path = Path(directory) / filename
                try:
                    if path.is_file():
                        yield path
                except OSError:
                    continue
    except OSError:
        return


def collect_skill_file_metadata(skill_dir: str | Path) -> SkillFileMetadata:
    """Collect file names and stat metadata without reading file contents."""
    root = Path(skill_dir)
    if not root.is_dir():
        return SkillFileMetadata([], "", 0.0)

    entries: list[tuple[str, int, int]] = []
    for path in _iter_skill_files(root):
        try:
            stat = path.stat()
        except OSError:
            continue
        entries.append(
            (
                path.relative_to(root).as_posix(),
                int(stat.st_size),
                int(stat.st_mtime_ns),
            )
        )

    entries.sort(key=lambda item: item[0].lower())
    signature_hash = hashlib.sha256()
    latest_mtime = 0.0
    for relative_path, size, mtime_ns in entries:
        signature_hash.update(relative_path.encode("utf-8", errors="replace"))
        signature_hash.update(b"\0")
        signature_hash.update(str(size).encode("ascii"))
        signature_hash.update(b"\0")
        signature_hash.update(str(mtime_ns).encode("ascii"))
        signature_hash.update(b"\0")
        latest_mtime = max(latest_mtime, mtime_ns / 1_000_000_000)

    return SkillFileMetadata(
        [relative_path for relative_path, _, _ in entries],
        signature_hash.hexdigest(),
        latest_mtime,
    )


def compute_skill_hash(skill_dir: str | Path) -> str:
    """Compute a deterministic SHA-256 hash for all files in a Skill dir."""
    root = Path(skill_dir)
    if not root.is_dir():
        return ""
    hasher = hashlib.sha256()
    files = list(_iter_skill_files(root))
    files.sort(key=lambda p: p.relative_to(root).as_posix().lower())
    for path in files:
        rel = path.relative_to(root).as_posix()
        if path.parent == root and path.name.casefold() == "skill.md":
            # Normalize case-only SKILL.md variants so a Library import can
            # canonicalize the filename without changing the verified hash.
            rel = "SKILL.md"
        hasher.update(rel.encode("utf-8", errors="replace"))
        hasher.update(b"\0")
        try:
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(65536), b""):
                    hasher.update(chunk)
        except OSError:
            continue
        hasher.update(b"\0")
    return hasher.hexdigest()


def compute_skill_md_hash(skill: str | Path) -> str:
    """Hash only the portable SKILL.md payload used by cross-Harness sync."""
    path = Path(skill)
    if path.is_dir():
        path = find_skill_md(path)
        if path is None:
            return ""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""
