"""
CODEMAP Ignore Module

Handles loading and building ignore rules for the CODEMAP generator.
This module provides functionality to:
- Load patterns from .codemapignore and .gitignore files
- Build IgnoreRules instances from loaded patterns and defaults

This module depends on codemap_types (for IgnoreRules) and codemap_config
(for default exclude patterns and filename constants).
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from codemap_config import (
    CODEMAPIGNORE_FILENAMES,
    DEFAULT_DIR_EXCLUDES,
    DEFAULT_FILE_EXCLUDES,
    GITIGNORE_FILENAMES,
)
from codemap_types import IgnoreRules


def load_patterns_file(path: Path) -> List[str]:
    """
    Load ignore patterns from a file (e.g., .gitignore, .codemapignore).

    Reads the file and extracts non-empty, non-comment lines as patterns.
    Comments are lines starting with '#'.

    Args:
        path: Path to the patterns file

    Returns:
        List of pattern strings, stripped of whitespace.
        Returns empty list if file cannot be read.
    """
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    except Exception:
        return []


def build_ignore_rules(root: Path, include_gitignore: bool) -> IgnoreRules:
    """
    Build IgnoreRules by combining default excludes with patterns from ignore files.

    Loads patterns from .codemapignore files (always) and .gitignore files
    (if include_gitignore is True). Combines these with the default directory
    and file exclusion patterns from codemap_config.

    Args:
        root: Repository root directory to search for ignore files
        include_gitignore: Whether to include patterns from .gitignore files

    Returns:
        IgnoreRules instance configured with all applicable patterns
    """
    patterns: List[str] = []

    # Load patterns from .codemapignore files
    for fname in CODEMAPIGNORE_FILENAMES:
        f = root / fname
        if f.exists() and f.is_file():
            patterns.extend(load_patterns_file(f))

    # Optionally load patterns from .gitignore files
    if include_gitignore:
        for fname in GITIGNORE_FILENAMES:
            f = root / fname
            if f.exists() and f.is_file():
                patterns.extend(load_patterns_file(f))

    return IgnoreRules(
        dir_names=set(DEFAULT_DIR_EXCLUDES),
        file_globs=set(DEFAULT_FILE_EXCLUDES),
        gitignore_like_patterns=patterns,
    )
