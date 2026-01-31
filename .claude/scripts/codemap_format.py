"""
CODEMAP Format Module

Contains formatting and utility functions for the CODEMAP generator:
- utc_now_iso: Get current UTC time in ISO 8601 format
- format_bytes: Human-readable byte size formatting
- read_first_lines: Read initial lines from a file for snippets

This module depends on codemap_fs (for is_probably_binary).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from codemap_fs import is_probably_binary


def utc_now_iso() -> str:
    """
    Get the current UTC time in ISO 8601 format.

    Returns:
        Current UTC timestamp as string in format: YYYY-MM-DDTHH:MM:SSZ
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_bytes(n: int) -> str:
    """
    Format a byte count as a human-readable string.

    Uses binary units (1 KB = 1024 bytes) with appropriate suffixes.

    Args:
        n: Number of bytes to format

    Returns:
        Human-readable string with appropriate unit (e.g., "1.5 MB", "256 B")
    """
    units = ["B", "KB", "MB", "GB", "TB"]
    x = float(n)
    for u in units:
        if x < 1024 or u == units[-1]:
            if u == "B":
                return f"{int(x)} {u}"
            return f"{x:.1f} {u}"
        x /= 1024
    return f"{n} B"


def read_first_lines(
    root: Path,
    rel: str,
    max_lines: int = 24,
    max_chars: int = 2000,
) -> str:
    """
    Read the first lines of a file for snippet display.

    Reads up to max_lines from a file, truncating at max_chars total.
    Skips binary files and handles encoding errors gracefully.

    Args:
        root: Repository root directory
        rel: Relative path from root to the file
        max_lines: Maximum number of lines to read (default: 24)
        max_chars: Maximum total characters to return (default: 2000)

    Returns:
        Stripped string containing the first lines of the file,
        or empty string if the file cannot be read or is binary.
    """
    p = root / rel
    if not p.exists() or not p.is_file():
        return ""
    if is_probably_binary(p):
        return ""
    try:
        txt = p.read_text(encoding="utf-8", errors="ignore")
        lines = txt.splitlines()[:max_lines]
        out = "\n".join(lines)
        out = out[:max_chars]
        return out.strip()
    except Exception:
        return ""
