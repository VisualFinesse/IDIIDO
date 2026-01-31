#!/usr/bin/env python3
"""
CODEMAP Generator (stack + language agnostic)

Generates CODEMAP.md for any repository:
- High-signal inventory (manifests, CI/CD, infra, scripts, docs)
- Tech/stack signals (heuristic)
- Entry points (heuristic)
- Repo tree (bounded)
- Optional per-file metadata (size, modified time, hash)

Usage:
  python tools/codemap.py
  python tools/codemap.py --root . --out CODEMAP.md --max-depth 6

This module is kept thin: it only contains CLI argument parsing and main().
All generation logic is in codemap_render.generate_codemap().
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from codemap_render import generate_codemap


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate CODEMAP.md for any repository.")
    p.add_argument("--root", type=str, default=".", help="Repository root directory.")
    p.add_argument("--out", type=str, default="CODEMAP.md", help="Output markdown file.")
    p.add_argument("--max-depth", type=int, default=6, help="Max tree depth.")
    p.add_argument("--max-files", type=int, default=5000, help="Max files to index.")
    p.add_argument("--include-hidden", action="store_true", help="Include hidden files/dirs (dotfiles).")
    p.add_argument("--no-gitignore", action="store_true", help="Do not read .gitignore patterns.")
    p.add_argument("--hash", action="store_true", help="Include SHA-256 hashes in the file index.")
    p.add_argument("--hash-max-bytes", type=int, default=2_000_000, help="Max bytes hashed per file (0 = full file).")
    p.add_argument("--snippets", action="store_true", help="Include first lines of key files (bounded).")
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve()
    out_path = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out).resolve()

    if not root.exists() or not root.is_dir():
        print(f"error: root not found or not a directory: {root}", file=sys.stderr)
        return 2

    include_hashes = bool(args.hash)
    hash_max_bytes = None if args.hash_max_bytes == 0 else int(args.hash_max_bytes)

    md = generate_codemap(
        root=root,
        out_path=out_path,
        max_depth=max(1, int(args.max_depth)),
        max_files=max(1, int(args.max_files)),
        include_hidden=bool(args.include_hidden),
        include_gitignore=not bool(args.no_gitignore),
        include_hashes=include_hashes,
        hash_max_bytes=hash_max_bytes,
        include_snippets=bool(args.snippets),
    )

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md, encoding="utf-8")
    except Exception as e:
        print(f"error: failed to write {out_path}: {e}", file=sys.stderr)
        return 3

    print(f"codemap generated successfully: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

