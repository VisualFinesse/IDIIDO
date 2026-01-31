"""
TODO Parser - Extract and manage tasks from markdown TODO files.

This module provides functionality to:
- Parse TODO.md
- Extract pending tasks with full context (section, hierarchy, metadata)
- Mark tasks as complete while preserving formatting
- Track task relationships and dependencies

REFERENCE: Part of TODO execution system for sequential task processing
"""

from __future__ import annotations

import argparse
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any, Literal

logger = logging.getLogger(__name__)

TodoResolveMode = Literal["cwd", "project"]


@dataclass
class TodoTask:
    file_path: str
    line_number: int
    section: str
    description: str
    depth: int
    status: str  # 'pending' or 'completed'
    parent_task: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw_line: str = ""

    def __str__(self) -> str:
        status_symbol = "✓" if self.status == "completed" else " "
        return f"[{status_symbol}] {self.section}: {self.description[:60]}..."


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_todo_path(
    file_path: Optional[str] = None,
    *,
    mode: TodoResolveMode = "project",
) -> Path:
    root = _project_root()
    cwd = Path.cwd()

    if file_path:
        p = Path(file_path)
        if p.is_absolute():
            return p
        return (cwd / p).resolve() if mode == "cwd" else (root / p).resolve()

    return (cwd / "TODO.md") if mode == "cwd" else (root / "TODO.md")


def _depth_from_indent(indent: str) -> int:
    return len(indent.replace("\t", "  ")) // 2


def _extract_list_item(description: str) -> str:
    return description.strip()


def _task_from_match(
    *,
    path: Path,
    line_num: int,
    raw_line: str,
    current_section: str,
    seen_section: bool,
    parent_stack: List[str],
    indent_str: str,
    status: str,
    description: str,
) -> TodoTask:
    depth = _depth_from_indent(indent_str)

    while len(parent_stack) > depth:
        parent_stack.pop()
    parent_task = parent_stack[-1] if parent_stack else None

    description = _extract_list_item(description)
    metadata = _extract_metadata(description)

    task = TodoTask(
        file_path=str(path),
        line_number=line_num,
        section=current_section if seen_section or current_section else "General",
        description=description,
        depth=depth,
        status=status,
        parent_task=parent_task,
        metadata=metadata,
        raw_line=raw_line,
    )

    if len(parent_stack) <= depth:
        parent_stack.append(description)
    else:
        parent_stack[depth] = description

    return task


def parse_todo_file(
    file_path: Optional[str],
    *,
    resolve_mode: TodoResolveMode = "project",
) -> List[TodoTask]:
    path = resolve_todo_path(file_path, mode=resolve_mode)
    if not path.exists():
        raise FileNotFoundError(f"TODO file not found: {path}")

    tasks: List[TodoTask] = []
    current_section = "General"
    seen_section = False
    parent_stack: List[str] = []

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line_num, line in enumerate(lines, start=1):
        line_stripped = line.strip()

        # Markdown headings
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line_stripped)
        if heading_match:
            current_section = heading_match.group(2).strip()
            seen_section = True
            parent_stack = []
            continue

        # "Section N" standalone
        section_only_match = re.match(r"^Section\s+(\d+)\s*$", line_stripped, re.IGNORECASE)
        if section_only_match:
            current_section = f"Section {section_only_match.group(1)}"
            seen_section = True
            parent_stack = []
            continue

        # "1) Title" / "1. Title" / "1 - Title" section headers (not list items)
        section_match = re.match(r"^(?:Section\s+)?(\d+)\s*(?:[)\.]|-)\s*(.*)$", line_stripped, re.IGNORECASE)
        if section_match and not line_stripped.startswith("- [") and not re.match(r"^\s*\d+[\.)]\s+\[", line):
            section_num = section_match.group(1)
            section_title = section_match.group(2).strip()
            current_section = f"Section {section_num}: {section_title}" if section_title else f"Section {section_num}"
            seen_section = True
            parent_stack = []
            continue

        # Checkbox tasks: "- [ ] ..." / "- [x] ..."
        checkbox_match = re.match(r"^(\s*)- \[([ xX])\]\s+(.+)$", line)
        if checkbox_match:
            indent_str = checkbox_match.group(1)
            status_char = checkbox_match.group(2)
            description = checkbox_match.group(3)
            status = "completed" if status_char.lower() == "x" else "pending"
            tasks.append(
                _task_from_match(
                    path=path,
                    line_num=line_num,
                    raw_line=line,
                    current_section=current_section,
                    seen_section=seen_section,
                    parent_stack=parent_stack,
                    indent_str=indent_str,
                    status=status,
                    description=description,
                )
            )
            continue

        # Numbered list tasks: "1. Task" / "2) Task"
        numbered_match = re.match(r"^(\s*)(\d+)[\.)]\s+(.+)$", line)
        if numbered_match:
            indent_str = numbered_match.group(1)
            description = numbered_match.group(3)
            # Treat numbered list items as tasks (pending by default)
            tasks.append(
                _task_from_match(
                    path=path,
                    line_num=line_num,
                    raw_line=line,
                    current_section=current_section,
                    seen_section=seen_section,
                    parent_stack=parent_stack,
                    indent_str=indent_str,
                    status="pending",
                    description=description,
                )
            )
            continue

        # Hyphen list tasks without checkbox: "- Task"
        bullet_match = re.match(r"^(\s*)-\s+(.+)$", line)
        if bullet_match:
            indent_str = bullet_match.group(1)
            description = bullet_match.group(2)
            # Skip separators like "- ---" if any
            if description.strip() in ("---", "--", "-"):
                continue
            tasks.append(
                _task_from_match(
                    path=path,
                    line_num=line_num,
                    raw_line=line,
                    current_section=current_section,
                    seen_section=seen_section,
                    parent_stack=parent_stack,
                    indent_str=indent_str,
                    status="pending",
                    description=description,
                )
            )
            continue

    logger.info(f"Parsed {len(tasks)} tasks from {path}")
    return tasks


def get_next_pending_task(
    file_path: Optional[str],
    *,
    resolve_mode: TodoResolveMode = "project",
) -> Optional[TodoTask]:
    try:
        tasks = parse_todo_file(file_path, resolve_mode=resolve_mode)
    except FileNotFoundError:
        resolved = resolve_todo_path(file_path, mode=resolve_mode)
        logger.warning(f"TODO file not found: {resolved}")
        return None

    for task in tasks:
        if task.status == "pending":
            logger.info(f"Next pending task: {task}")
            return task

    logger.info(f"No pending tasks in {resolve_todo_path(file_path, mode=resolve_mode)}")
    return None


def mark_task_complete(
    file_path: Optional[str],
    line_number: int,
    *,
    resolve_mode: TodoResolveMode = "project",
) -> bool:
    path = resolve_todo_path(file_path, mode=resolve_mode)
    if not path.exists():
        raise FileNotFoundError(f"TODO file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    if line_number < 1 or line_number > len(lines):
        logger.error(f"Invalid line number: {line_number} (file has {len(lines)} lines)")
        return False

    idx = line_number - 1
    original = lines[idx]

    # Checkbox pending: "- [ ]"
    if re.match(r"^(\s*)- \[ \]\s+", original):
        lines[idx] = re.sub(r"^(\s*)- \[ \]\s+", r"\1- [x] ", original)
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        logger.info(f"Marked checkbox task complete at line {line_number}: {original.strip()}")
        return True

    # If it’s a non-checkbox list item (numbered or bullet), do not mutate format implicitly.
    logger.warning(f"Line {line_number} is not a pending checkbox task: {original.strip()}")
    return False


def ensure_task_pending(
    file_path: Optional[str],
    line_number: int,
    *,
    resolve_mode: TodoResolveMode = "project",
) -> bool:
    path = resolve_todo_path(file_path, mode=resolve_mode)
    if not path.exists():
        raise FileNotFoundError(f"TODO file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    if line_number < 1 or line_number > len(lines):
        logger.error(f"Invalid line number: {line_number} (file has {len(lines)} lines)")
        return False

    idx = line_number - 1
    original = lines[idx]

    if re.match(r"^(\s*)- \[[xX]\]\s+", original):
        lines[idx] = re.sub(r"^(\s*)- \[[xX]\]\s+", r"\1- [ ] ", original)
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        logger.info(f"Reset task to pending at line {line_number}: {original.strip()}")
        return True

    return False


def _extract_metadata(description: str) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}

    if "**CRITICAL**" in description or "**Breaking Change**" in description:
        metadata["critical"] = True

    phase_refs = re.findall(r"\(Phase\s+(\d+(?:\.\d+)?)", description)
    if phase_refs:
        metadata["phase_references"] = phase_refs

    file_refs = re.findall(r"`([^`]+\.(?:py|md|yml|yaml|json|ps1))`", description)
    if file_refs:
        metadata["file_references"] = file_refs

    task_id_match = re.match(r"^\*\*(\d+\.\d+)[:\s]+", description)
    if task_id_match:
        metadata["task_id"] = task_id_match.group(1)

    return metadata


def get_task_context(task: TodoTask) -> str:
    context_lines = [
        "=" * 80,
        "TODO TASK CONTEXT",
        "=" * 80,
        f"Task: {task.description}",
        f"Section: {task.section}",
        f"File: {task.file_path}:{task.line_number}",
    ]

    if task.parent_task:
        context_lines.append(f"Parent Task: {task.parent_task}")

    if task.metadata.get("critical"):
        context_lines.append("⚠️  CRITICAL TASK")

    if task.metadata.get("file_references"):
        context_lines.append(f"Referenced Files: {', '.join(task.metadata['file_references'])}")

    if task.metadata.get("phase_references"):
        context_lines.append(f"References Sections: {', '.join(task.metadata['phase_references'])}")

    context_lines.append("=" * 80)
    return "\n".join(context_lines)


def _build_cli_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Parse and inspect markdown TODO files.")
    p.add_argument(
        "todo_file",
        nargs="?",
        default=None,
        help="Optional path to TODO file. If omitted, uses TODO.md based on --todo-scope.",
    )
    p.add_argument(
        "--todo-scope",
        choices=["cwd", "project"],
        default="cwd",
        help="Where to resolve TODO.md from when no explicit path is provided.",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return p


if __name__ == "__main__":
    cli = _build_cli_parser()
    args = cli.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    resolved = resolve_todo_path(args.todo_file, mode=args.todo_scope)
    print(f"\n=== Parsing {resolved} ===\n")

    try:
        tasks = parse_todo_file(args.todo_file, resolve_mode=args.todo_scope)
        print(f"Found {len(tasks)} total tasks")

        pending_tasks = [t for t in tasks if t.status == "pending"]
        completed_tasks = [t for t in tasks if t.status == "completed"]

        print(f"  Pending: {len(pending_tasks)}")
        print(f"  Completed: {len(completed_tasks)}")

        next_task = get_next_pending_task(args.todo_file, resolve_mode=args.todo_scope)
        if next_task:
            print("\n=== Next Pending Task ===\n")
            print(get_task_context(next_task))
        else:
            print("\n✓ All tasks complete!")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        raise SystemExit(1)
