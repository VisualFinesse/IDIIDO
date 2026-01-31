"""
CODEMAP Tree Module

Handles tree rendering for the CODEMAP generator:
- build_tree: Convert list of file paths into a visual tree structure

This module has no dependencies on other codemap modules.
"""

from __future__ import annotations

from typing import Dict, List, Tuple


def build_tree(files: List[str], max_depth: int) -> str:
    """
    Build a visual tree representation from a list of file paths.

    Creates an ASCII tree structure from POSIX-style file paths, with support
    for depth limiting. Paths exceeding max_depth are truncated with an ellipsis.

    Args:
        files: List of POSIX-style relative file paths (e.g., "src/main.py")
        max_depth: Maximum depth of tree to render (paths beyond this show "...")

    Returns:
        String containing the rendered tree with box-drawing characters.
        Empty string if no files provided.

    Example:
        >>> build_tree(["src/main.py", "src/utils/helper.py", "README.md"], 3)
        '├── README.md\\n└── src\\n    ├── main.py\\n    └── utils\\n        └── helper.py'
    """
    tree: Dict[str, dict] = {}

    def insert(parts: List[str]) -> None:
        """Insert a path (as list of parts) into the tree structure."""
        cur = tree
        for i, part in enumerate(parts):
            if i >= max_depth:
                cur.setdefault("…", {})
                return
            cur = cur.setdefault(part, {})

    for f in files:
        insert(f.split("/"))

    def sort_key(name: str) -> Tuple[int, str]:
        """
        Generate sort key for tree items.

        Sorting priority:
        1. Double underscore prefix (e.g., __init__.py)
        2. Single underscore prefix (e.g., _private.py)
        3. Numeric prefix (e.g., 01_setup.py)
        4. Everything else (alphabetical)
        """
        n = name.lower()
        if n.startswith("__"):
            return (0, n)
        if n.startswith("_"):
            return (1, n)
        if n and n[0].isdigit():
            return (2, n)
        return (3, n)

    def is_leaf(node: dict) -> bool:
        """Check if a tree node is a leaf (has no children)."""
        return len(node) == 0

    def render(node: dict, prefix: str = "") -> List[str]:
        """
        Recursively render tree nodes to ASCII art.

        Args:
            node: Dictionary representing tree structure
            prefix: Current indentation prefix for this level

        Returns:
            List of lines representing the rendered tree
        """
        lines: List[str] = []
        items = sorted(node.items(), key=lambda kv: sort_key(kv[0]))
        for idx, (name, sub) in enumerate(items):
            last = idx == len(items) - 1
            branch = "└── " if last else "├── "
            lines.append(f"{prefix}{branch}{name}")
            if sub and not is_leaf(sub):
                extension = "    " if last else "│   "
                lines.extend(render(sub, prefix + extension))
        return lines

    return "\n".join(render(tree))
