"""
CODEMAP Detection Module

Handles detection and collection logic for the CODEMAP generator:
- is_match_any: Check if a path matches any of a set of patterns
- collect_important_files: Find high-signal files (manifests, configs, docs)
- collect_entrypoints: Identify likely application entry points
- detect_stack_signals: Detect technology stack from manifest files
- extract_package_json_scripts: Parse npm scripts from package.json files
- extract_dependencies: Extract dependencies from package manifests

This module depends on:
- codemap_types (for FileRecord)
- codemap_config (for IMPORTANT_FILES, ENTRYPOINT_HINTS, MANIFEST_STACK_SIGNALS)
- codemap_fs (for is_probably_binary)
"""

from __future__ import annotations

import json
from fnmatch import fnmatch
from pathlib import Path
from typing import Dict, List, Sequence

from codemap_config import (
    ENTRYPOINT_HINTS,
    IMPORTANT_FILES,
    MANIFEST_STACK_SIGNALS,
)
from codemap_fs import is_probably_binary
from codemap_types import FileRecord

import re

def extract_dependencies(root: Path, files: List[FileRecord]) -> Dict[str, List[str]]:
    """
    Extract dependencies from package manifests.

    Parses requirements.txt, package.json, and setup.py files to extract dependency information.

    Args:
        root: Repository root directory
        files: List of FileRecord objects from walk_repo

    Returns:
        Dictionary mapping dependency types to lists of dependencies
    """
    dependencies: Dict[str, List[str]] = {
        "Python": [],
        "Node.js": [],
    }

    # Extract Python dependencies from requirements.txt
    req_files = [fr.rel for fr in files if fr.rel.endswith("requirements.txt")]
    for rel in req_files:
        p = root / rel
        if is_probably_binary(p):
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    # Simple parsing - extract package name (first token)
                    package = line.split()[0] if line.split() else line
                    if package and package not in dependencies["Python"]:
                        dependencies["Python"].append(package)
        except Exception:
            continue

    # Extract Python dependencies from setup.py
    setup_files = [fr.rel for fr in files if fr.rel.endswith("setup.py")]
    for rel in setup_files:
        p = root / rel
        if is_probably_binary(p):
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            # Look for pattern: install_requires=[...]
            pos = content.find("install_requires")
            if pos != -1:
                start = content.find("[", pos)
                end = content.find("]", start)
                if start != -1 and end != -1:
                    deps_section = content[start+1:end]
                    # Use regex to extract quoted dependencies
                    deps = re.findall(r'["\']([^"\']+)["\']', deps_section)
                    for dep in deps:
                        dep = dep.strip()
                        if dep and dep not in dependencies["Python"]:
                            dependencies["Python"].append(dep)
        except Exception:
            continue

    # Extract Node.js dependencies from package.json
    pkg_files = [fr.rel for fr in files if fr.rel.endswith("package.json")]
    for rel in pkg_files:
        p = root / rel
        if is_probably_binary(p):
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
            if "dependencies" in data:
                for dep, version in data["dependencies"].items():
                    dependencies["Node.js"].append(f"{dep}@{version}")
            if "devDependencies" in data:
                for dep, version in data["devDependencies"].items():
                    dependencies["Node.js"].append(f"{dep}@{version} (dev)")
        except Exception:
            continue

    return dependencies

def is_match_any(path_posix: str, patterns: Sequence[str]) -> bool:
    """
    Check if a path matches any of the given patterns.

    Matches against both the full POSIX-style path and the filename (basename).
    Uses fnmatch for glob-style pattern matching.

    Args:
        path_posix: POSIX-style relative path to check
        patterns: Sequence of glob patterns to match against

    Returns:
        True if the path matches any pattern, False otherwise
    """
    for p in patterns:
        if fnmatch(path_posix, p) or fnmatch(Path(path_posix).name, p):
            return True
    return False

def collect_important_files(root: Path, files: List[FileRecord]) -> List[str]:
    """
    Collect high-signal files from the repository.

    Identifies files matching IMPORTANT_FILES patterns, which include:
    - Documentation (README, LICENSE, CHANGELOG)
    - CI/CD configurations (GitHub Actions, GitLab CI, etc.)
    - Package manifests (package.json, pyproject.toml, etc.)
    - Docker configurations
    - Build tool configurations

    Args:
        root: Repository root directory (unused but kept for API consistency)
        files: List of FileRecord objects from walk_repo

    Returns:
        Sorted list of unique relative paths for important files
    """
    important: List[str] = []
    for fr in files:
        if is_match_any(fr.rel, IMPORTANT_FILES):
            important.append(fr.rel)
    return sorted(set(important))

def collect_entrypoints(root: Path, files: List[FileRecord]) -> List[str]:
    """
    Identify likely application entry points in the repository.

    Uses heuristics based on common naming conventions (main.py, index.js, etc.)
    to find files that are likely entry points. Results are sorted by depth
    (shallower paths first) and limited to 50 entries.

    Args:
        root: Repository root directory (unused but kept for API consistency)
        files: List of FileRecord objects from walk_repo

    Returns:
        List of relative paths for likely entry points, sorted by depth,
        limited to 50 entries
    """
    entrypoints: List[str] = []
    for fr in files:
        if is_match_any(fr.rel, ENTRYPOINT_HINTS):
            entrypoints.append(fr.rel)
    entrypoints.sort(key=lambda s: (s.count("/"), s))
    return entrypoints[:50]

def detect_stack_signals(root: Path, files: List[FileRecord]) -> Dict[str, List[str]]:
    """
    Detect technology stack from manifest files in the repository.

    Scans files for patterns matching known stack indicators (package.json
    for Node.js, Cargo.toml for Rust, etc.). Returns a mapping of stack
    names to the files that indicate that stack.

    Args:
        root: Repository root directory (unused but kept for API consistency)
        files: List of FileRecord objects from walk_repo

    Returns:
        Dictionary mapping stack names to sorted lists of matching file paths.
        Only stacks with at least one matching file are included.
    """
    by_stack: Dict[str, List[str]] = {}
    for stack, pats in MANIFEST_STACK_SIGNALS.items():
        matches: List[str] = []
        for pat in pats:
            for fr in files:
                if fnmatch(fr.rel, pat) or fnmatch(Path(fr.rel).name, pat):
                    matches.append(fr.rel)
        if matches:
            by_stack[stack] = sorted(set(matches))
    return by_stack

def extract_package_json_scripts(root: Path, files: List[FileRecord]) -> List[str]:
    """
    Extract npm scripts from package.json files in the repository.

    Parses up to 5 package.json files and extracts their scripts section.
    Script commands longer than 120 characters are truncated.

    Args:
        root: Repository root directory (used to read file contents)
        files: List of FileRecord objects from walk_repo

    Returns:
        List of formatted strings describing scripts, e.g.:
        - `package.json`
          - `build`: webpack --mode production
          - `test`: jest
    """
    candidates = [fr.rel for fr in files if fr.rel.endswith("package.json")]
    if not candidates:
        return []

    scripts_out: List[str] = []
    for rel in candidates[:5]:
        p = root / rel
        if is_probably_binary(p):
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
            scripts = data.get("scripts") or {}
            if isinstance(scripts, dict) and scripts:
                scripts_out.append(f"- `{rel}`")
                for k in sorted(scripts.keys()):
                    v = str(scripts[k])
                    if len(v) > 120:
                        v = v[:117] + "..."
                    scripts_out.append(f"  - `{k}`: {v}")
        except Exception:
            continue
    return scripts_out