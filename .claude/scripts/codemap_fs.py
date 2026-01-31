"""
CODEMAP Filesystem Module

Handles filesystem operations for the CODEMAP generator:
- rel_posix: Convert paths to POSIX-style relative paths
- walk_repo: Traverse directory tree and collect file records
- is_probably_binary: Detect binary files by content analysis
- sha256_file: Compute SHA-256 hash of file contents

This module depends on codemap_types (for FileRecord, IgnoreRules).
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from codemap_types import FileRecord, IgnoreRules


def rel_posix(root: Path, p: Path) -> str:
    """
    Convert a path to a POSIX-style relative path from root.

    Args:
        root: The root directory to calculate relative path from
        p: The path to convert

    Returns:
        POSIX-style relative path string (uses forward slashes)
    """
    return p.relative_to(root).as_posix()


def is_probably_binary(path: Path, sniff_bytes: int = 4096) -> bool:
    """
    Detect if a file is likely binary by examining its contents.

    Uses two heuristics:
    1. Presence of null bytes (common in binary files)
    2. High ratio of non-text bytes (control characters)

    Args:
        path: Path to the file to check
        sniff_bytes: Number of bytes to read for analysis (default: 4096)

    Returns:
        True if the file appears to be binary, False if it appears to be text.
        Returns True on any read errors (fail-safe).
    """
    try:
        with path.open("rb") as f:
            chunk = f.read(sniff_bytes)
        if b"\x00" in chunk:
            return True
        nontext = sum(1 for b in chunk if b < 9 or (13 < b < 32) or b == 127)
        return len(chunk) > 0 and (nontext / len(chunk)) > 0.30
    except Exception:
        return True


def sha256_file(path: Path, max_bytes: Optional[int] = None) -> str:
    """
    Compute SHA-256 hash of a file's contents.

    Args:
        path: Path to the file to hash
        max_bytes: Maximum number of bytes to hash (None for entire file)

    Returns:
        Hexadecimal SHA-256 hash string, or empty string on error.
    """
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            if max_bytes is None:
                for blk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(blk)
            else:
                remaining = max_bytes
                while remaining > 0:
                    blk = f.read(min(1024 * 1024, remaining))
                    if not blk:
                        break
                    h.update(blk)
                    remaining -= len(blk)
    except Exception:
        return ""
    return h.hexdigest()


def walk_repo(
    root: Path,
    ignores: IgnoreRules,
    include_hidden: bool,
    max_files: int,
) -> Tuple[List[FileRecord], List[str]]:
    """
    Walk the repository tree and collect file records.

    Traverses the directory tree starting from root, applying ignore rules
    and collecting metadata for each file. Respects hidden file settings
    and stops after reaching the maximum file count.

    Args:
        root: Repository root directory to start traversal
        ignores: IgnoreRules instance for filtering files/directories
        include_hidden: Whether to include hidden files/directories (dotfiles)
        max_files: Maximum number of files to collect

    Returns:
        Tuple of (records, warnings) where:
        - records: List of FileRecord objects for indexed files, sorted by path
        - warnings: List of warning messages (e.g., stat failures, max reached)
    """
    records: List[FileRecord] = []
    warnings: List[str] = []
    count = 0

    def should_skip(p: Path, is_dir: bool) -> bool:
        name = p.name
        if not include_hidden and name.startswith(".") and name not in {".github"}:
            return True
        return ignores.matches(root, p, is_dir=is_dir)

    for dirpath, dirnames, filenames in os.walk(root):
        d = Path(dirpath)

        pruned = []
        for dn in list(dirnames):
            dp = d / dn
            if should_skip(dp, is_dir=True):
                continue
            pruned.append(dn)
        dirnames[:] = pruned

        for fn in filenames:
            fp = d / fn
            if should_skip(fp, is_dir=False):
                continue

            try:
                st = fp.stat()
            except Exception as e:
                warnings.append(f"stat_failed: {rel_posix(root, fp)}: {e}")
                continue

            mtime_iso = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            records.append(
                FileRecord(
                    rel=rel_posix(root, fp),
                    size=int(st.st_size),
                    mtime_iso=mtime_iso,
                    is_dir=False,
                )
            )
            count += 1
            if count >= max_files:
                warnings.append(f"max_files_reached: {max_files}")
                return records, warnings

    records.sort(key=lambda r: r.rel)
    return records, warnings
