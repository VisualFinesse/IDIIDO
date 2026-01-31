#!/usr/bin/env python3
"""
Pre-prompt hook: Inject next TODO task context before each Claude prompt.

This hook runs before every user message is sent to Claude.
It finds the next pending TODO task and injects its context.
"""
import sys
import os
from pathlib import Path

# Add scripts directory to path for local imports
scripts_dir = Path(__file__).parent.parent / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

# Project root is two levels up from .claude/hooks/
project_root = Path(__file__).parent.parent.parent.resolve()

from todo_parser import get_next_pending_task, get_task_context


def main() -> int:
    """
    Main entry point for pre-prompt hook.

    Returns:
        0 on success
    """
    os.chdir(project_root)
    # Check both TODO files
    todo_files = [
        project_root / "TODO.md",
    ]

    for todo_file in todo_files:
        if not todo_file.exists():
            continue

        task = get_next_pending_task(str(todo_file))
        if task:
            # Inject task context as system message
            context = get_task_context(task)
            print("<task-context>")
            print(context)
            print("</task-context>")
            return 0

    # No pending tasks
    print("<task-context>")
    print("All TODO tasks complete! No further work required.")
    print("</task-context>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
