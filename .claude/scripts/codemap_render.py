"""
CODEMAP Render Module

Contains rendering functions for generating the CODEMAP markdown output:
- render_header: Render the document header section
- render_quick_navigation: Render the quick navigation section
- render_stack_signals: Render the stack signals section
- render_entrypoints: Render the entrypoints section
- render_dependencies: Render the dependencies section
- render_package_scripts: Render the package.json scripts section
- render_tree: Render the repository tree section
- render_snippets: Render the key file snippets section
- render_warnings: Render the warnings section
- render_codemap: Assembles all sections into markdown
- generate_codemap: Main entry point that orchestrates CODEMAP generation

This module depends on:
- codemap_format (for format_bytes, utc_now_iso, read_first_lines)
- codemap_detect (for collect_important_files, collect_entrypoints, detect_stack_signals, extract_package_json_scripts, extract_dependencies)
- codemap_fs (for sha256_file, walk_repo)
- codemap_ignore (for build_ignore_rules)
- codemap_tree (for build_tree)
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from codemap_detect import (
    collect_entrypoints,
    collect_important_files,
    detect_stack_signals,
    extract_dependencies,
    extract_package_json_scripts,
)
from codemap_format import format_bytes, read_first_lines, utc_now_iso
from codemap_fs import sha256_file, walk_repo
from codemap_ignore import build_ignore_rules
from codemap_tree import build_tree

def render_header(root: Path, total_bytes: int) -> List[str]:
    """
    Render the CODEMAP document header section.

    Includes the title, generation timestamp, root path, and total size.

    Args:
        root: Repository root directory
        total_bytes: Total size of all indexed files in bytes

    Returns:
        List of markdown lines for the header section
    """
    lines: List[str] = []
    lines.append(f"# CODEMAP — {root.name}")
    lines.append("")
    lines.append(f"- Generated: `{utc_now_iso()}`")
    lines.append(f"- Root: `{root.resolve().as_posix()}`")
    lines.append(f"- Total size: `{format_bytes(total_bytes)}`")
    lines.append("")
    return lines

def render_quick_navigation(important: List[str]) -> List[str]:
    """
    Render the quick navigation section with important files.

    Lists high-signal files like READMEs, manifests, and CI configurations.

    Args:
        important: List of relative paths for important files

    Returns:
        List of markdown lines for the quick navigation section
    """
    lines: List[str] = []
    lines.append("## Quick navigation")
    if important:
        for rel in important:
            lines.append(f"- `{rel}`")
    else:
        lines.append("- (none found)")
    lines.append("")
    return lines

def render_stack_signals(stacks: Dict[str, List[str]]) -> List[str]:
    """
    Render the stack signals section showing detected technologies.

    Lists each detected technology stack with its associated files.
    Limits each stack to 12 files with a "more" indicator.

    Args:
        stacks: Dictionary mapping stack names to lists of file paths

    Returns:
        List of markdown lines for the stack signals section
    """
    lines: List[str] = []
    lines.append("## Stack signals")
    if stacks:
        for stack in sorted(stacks.keys()):
            lines.append(f"- **{stack}**")
            for rel in stacks[stack][:12]:
                lines.append(f"  - `{rel}`")
            if len(stacks[stack]) > 12:
                lines.append(f"  - … (+{len(stacks[stack]) - 12} more)")
    else:
        lines.append("- (no strong signals detected)")
    lines.append("")
    return lines

def render_entrypoints(entrypoints: List[str]) -> List[str]:
    """
    Render the entrypoints section listing likely application entry points.

    Args:
        entrypoints: List of relative paths for detected entry points

    Returns:
        List of markdown lines for the entrypoints section
    """
    lines: List[str] = []
    lines.append("## Entrypoints (heuristic)")
    if entrypoints:
        for rel in entrypoints:
            lines.append(f"- `{rel}`")
    else:
        lines.append("- (none detected)")
    lines.append("")
    return lines

def render_dependencies(dependencies: Dict[str, List[str]]) -> List[str]:
    """
    Render the dependencies section showing detected package dependencies.

    Lists dependencies by ecosystem (Python, Node.js, etc.) with their versions.

    Args:
        dependencies: Dictionary mapping ecosystem names to lists of dependencies

    Returns:
        List of markdown lines for the dependencies section,
        or empty list if no dependencies
    """
    if not dependencies:
        return []

    lines: List[str] = []
    lines.append("## Dependencies")
    lines.append("")

    for ecosystem in sorted(dependencies.keys()):
        deps = dependencies[ecosystem]
        if deps:
            lines.append(f"- **{ecosystem}**")
            for dep in sorted(deps):
                lines.append(f"  - `{dep}`")

    lines.append("")
    return lines

def render_package_scripts(pkg_scripts: List[str]) -> List[str]:
    """
    Render the package.json scripts section.

    Only renders if there are scripts to display.

    Args:
        pkg_scripts: Formatted list of script entries from extract_package_json_scripts

    Returns:
        List of markdown lines for the package scripts section,
        or empty list if no scripts
    """
    if not pkg_scripts:
        return []
    lines: List[str] = []
    lines.append("## package.json scripts (if present)")
    lines.extend(pkg_scripts)
    lines.append("")
    return lines

def render_tree(root: Path, tree: str) -> List[str]:
    """
    Render the repository tree section.

    Displays the directory structure in a code block.

    Args:
        root: Repository root directory (for the root name)
        tree: Pre-built tree string from build_tree

    Returns:
        List of markdown lines for the tree section
    """
    lines: List[str] = []
    lines.append("## Repository tree")
    lines.append("")
    lines.append("```")
    lines.append(f"{root.name}/")
    lines.append(tree if tree.strip() else "(empty)")
    lines.append("```")
    lines.append("")
    return lines

def render_snippets(snippets: List[Tuple[str, str]]) -> List[str]:
    """
    Render the key file snippets section.

    Displays first lines of important files for quick reference.

    Args:
        snippets: List of (relative_path, content) tuples

    Returns:
        List of markdown lines for the snippets section,
        or empty list if no snippets
    """
    if not snippets:
        return []
    lines: List[str] = []
    lines.append("## Key file snippets (first lines)")
    lines.append("")
    for rel, content in snippets:
        lines.append(f"### `{rel}`")
        lines.append("")
        lines.append("```")
        lines.append(content)
        lines.append("```")
        lines.append("")
    return lines

def render_warnings(warnings: List[str]) -> List[str]:
    """
    Render the warnings section.

    Displays warnings generated during CODEMAP generation.
    Limits output to 50 warnings with a "more" indicator.

    Args:
        warnings: List of warning messages

    Returns:
        List of markdown lines for the warnings section,
        or empty list if no warnings
    """
    if not warnings:
        return []
    lines: List[str] = []
    lines.append("## Warnings")
    lines.append("")
    for w in warnings[:50]:
        lines.append(f"- {w}")
    if len(warnings) > 50:
        lines.append(f"- … (+{len(warnings) - 50} more)")
    lines.append("")
    return lines

def render_codemap(
    root: Path,
    total_bytes: int,
    important: List[str],
    stacks: Dict[str, List[str]],
    entrypoints: List[str],
    dependencies: Dict[str, List[str]],
    pkg_scripts: List[str],
    tree: str,
    snippets: Optional[List[Tuple[str, str]]] = None,
    warnings: Optional[List[str]] = None,
) -> str:
    """
    Render the complete CODEMAP markdown document.

    Assembles all sections into a single markdown document string.
    This is the main entry point for CODEMAP rendering.

    Args:
        root: Repository root directory
        total_bytes: Total size of all indexed files in bytes
        important: List of relative paths for important files
        stacks: Dictionary mapping stack names to lists of file paths
        entrypoints: List of relative paths for detected entry points
        dependencies: Dictionary mapping ecosystems to lists of dependencies
        pkg_scripts: Formatted list of script entries
        tree: Pre-built tree string from build_tree
        snippets: Optional list of (relative_path, content) tuples
        warnings: Optional list of warning messages

    Returns:
        Complete CODEMAP markdown document as a string
    """
    lines: List[str] = []

    lines.extend(render_header(root, total_bytes))
    lines.extend(render_quick_navigation(important))
    lines.extend(render_stack_signals(stacks))
    lines.extend(render_entrypoints(entrypoints))
    lines.extend(render_dependencies(dependencies))
    lines.extend(render_package_scripts(pkg_scripts))
    lines.extend(render_tree(root, tree))

    if snippets:
        lines.extend(render_snippets(snippets))

    if warnings:
        lines.extend(render_warnings(warnings))

    return "\n".join(lines).rstrip() + "\n"

def generate_codemap(
    root: Path,
    out_path: Path,
    max_depth: int,
    max_files: int,
    include_hidden: bool,
    include_gitignore: bool,
    include_hashes: bool,
    hash_max_bytes: Optional[int],
    include_snippets: bool,
) -> str:
    """
    Generate a CODEMAP markdown document for a repository.

    This is the main entry point for CODEMAP generation. It orchestrates:
    - Building ignore rules from .gitignore and .codemapignore
    - Walking the repository to collect file records
    - Optionally computing file hashes
    - Collecting important files, entrypoints, and stack signals
    - Extracting dependencies from package manifests
    - Building the directory tree representation
    - Extracting package.json scripts
    - Optionally reading file snippets
    - Rendering all collected data into markdown

    Args:
        root: Repository root directory
        out_path: Output path for the generated CODEMAP (used for relative paths)
        max_depth: Maximum depth for tree rendering
        max_files: Maximum number of files to index
        include_hidden: Whether to include hidden files/directories
        include_gitignore: Whether to read .gitignore patterns
        include_hashes: Whether to compute SHA-256 hashes for files
        hash_max_bytes: Maximum bytes to hash per file (None for full file)
        include_snippets: Whether to include first lines of key files

    Returns:
        Complete CODEMAP markdown document as a string
    """
    ignores = build_ignore_rules(root, include_gitignore=include_gitignore)
    records, warnings = walk_repo(
        root=root,
        ignores=ignores,
        include_hidden=include_hidden,
        max_files=max_files,
    )

    if include_hashes:
        for fr in records:
            p = root / fr.rel
            fr.sha256 = sha256_file(p, max_bytes=hash_max_bytes)

    important = collect_important_files(root, records)
    entrypoints = collect_entrypoints(root, records)
    stacks = detect_stack_signals(root, records)
    dependencies = extract_dependencies(root, records)

    files_rel = [fr.rel for fr in records]
    tree = build_tree(files_rel, max_depth=max_depth)

    total_bytes = sum(fr.size for fr in records)
    pkg_scripts = extract_package_json_scripts(root, records)

    snippets: List[Tuple[str, str]] = []
    if include_snippets:
        for rel in important[:12]:
            s = read_first_lines(root, rel, max_lines=24, max_chars=2000)
            if s:
                snippets.append((rel, s))

    return render_codemap(
        root=root,
        total_bytes=total_bytes,
        important=important,
        stacks=stacks,
        entrypoints=entrypoints,
        dependencies=dependencies,
        pkg_scripts=pkg_scripts,
        tree=tree,
        snippets=snippets if snippets else None,
        warnings=warnings if warnings else None,
    )