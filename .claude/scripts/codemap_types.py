"""
CODEMAP Types Module

Contains core data structures for the CODEMAP generator:
- IgnoreRules: Pattern matching for files/directories to exclude
- FileRecord: Metadata for indexed files

This module is the lowest-level dependency in the codemap package
to prevent circular imports.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import List, Optional, Set


@dataclass
class IgnoreRules:
    """
    Pattern matching rules for excluding files and directories.

    Supports three types of patterns:
    - dir_names: Exact directory name matches (e.g., 'node_modules', '.git')
    - file_globs: Glob patterns for file names (e.g., '*.pyc', '*.log')
    - gitignore_like_patterns: .gitignore-style patterns with ** and anchoring

    Attributes:
        dir_names: Set of directory names to exclude
        file_globs: Set of glob patterns for files to exclude
        gitignore_like_patterns: List of .gitignore-style patterns
    """

    dir_names: Set[str]
    file_globs: Set[str]
    gitignore_like_patterns: List[str]

    def matches(self, root: Path, path: Path, is_dir: bool) -> bool:
        """
        Check if a path should be excluded based on ignore rules.

        Args:
            root: Repository root directory
            path: Path to check
            is_dir: Whether the path is a directory

        Returns:
            True if the path should be excluded, False otherwise
        """
        name = path.name

        if is_dir and name in self.dir_names:
            return True

        # Compute POSIX-style relative path (inlined to avoid circular import)
        rel = path.relative_to(root).as_posix()

        for g in self.file_globs:
            if fnmatch(name, g) or fnmatch(rel, g):
                return True

        for pat in self.gitignore_like_patterns:
            if self._match_gitignore_style(rel, name, pat, is_dir):
                return True

        return False

    @staticmethod
    def _match_gitignore_style(rel: str, name: str, pat: str, is_dir: bool) -> bool:
        """
        Match a path against a .gitignore-style pattern.

        Supports:
        - Anchored patterns starting with /
        - Directory-only patterns ending with /
        - ** for matching any path components
        - * for matching within a single path component
        - ? for matching a single character

        Args:
            rel: POSIX-style relative path
            name: File/directory name (basename)
            pat: .gitignore-style pattern
            is_dir: Whether the path is a directory

        Returns:
            True if the pattern matches, False otherwise
        """
        pat = pat.strip()
        if not pat or pat.startswith("#"):
            return False
        if pat.startswith("!"):
            pat = pat[1:].strip()
            if not pat:
                return False

        anchored = pat.startswith("/")
        if anchored:
            pat = pat[1:]

        dir_only = pat.endswith("/")
        if dir_only:
            pat = pat[:-1]

        pat = pat.replace("\\", "/")
        target = rel

        regex = re.escape(pat)
        regex = regex.replace(r"\*\*", ".*")
        regex = regex.replace(r"\*", "[^/]*")
        regex = regex.replace(r"\?", "[^/]")
        regex = "^" + regex + "$"

        if dir_only and not is_dir:
            return False

        if anchored:
            return re.match(regex, target) is not None
        else:
            return re.match(regex, target) is not None or re.match(regex, name) is not None


@dataclass
class FileRecord:
    """
    Metadata record for an indexed file.

    Attributes:
        rel: POSIX-style relative path from repository root
        size: File size in bytes
        mtime_iso: Last modification time in ISO 8601 format (UTC)
        is_dir: Whether this record represents a directory
        sha256: Optional SHA-256 hash of file contents
    """

    rel: str
    size: int
    mtime_iso: str
    is_dir: bool
    sha256: Optional[str] = None
