#!/usr/bin/env python3
"""
Post-completion hook: Validate DoD before marking task complete.

This hook runs when the agent believes a task is done.
It validates against definition-of-done.md criteria.
"""
import sys
import os
import argparse
from pathlib import Path

# Add scripts directory to path for local imports
scripts_dir = Path(__file__).parent.parent / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

# Project root is two levels up from .claude/hooks/
project_root = Path(__file__).parent.parent.parent.resolve()

from scripts.todo_parser import get_next_pending_task, mark_task_complete
from scripts.dod_validator import validate_task_completion


def main() -> int:
    """
    Main entry point for post-completion hook.

    Returns:
        0 if task validation passed, 1 if failed
    """
    parser = argparse.ArgumentParser(description="Post-completion hook: DoD validation")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate DoD without marking the TODO item complete",
    )
    args = parser.parse_args()

    os.chdir(project_root)
    # Get current task
    todo_files = [
        project_root / "TODO.md",
    ]

    for todo_file in todo_files:
        if not todo_file.exists():
            continue

        task = get_next_pending_task(str(todo_file))
        if task:
            # Validate against DoD
            print("\n=== Validating Definition of Done ===\n")
            validation = validate_task_completion(skip_tests=False)

            if validation.passed:
                if not args.validate_only:
                    # Mark complete
                    mark_task_complete(str(todo_file), task.line_number)
                print(f"\n[PASS] Task completed: {task.description}")
                print(f"  All DoD criteria met ({len(validation.criteria_met)} checks passed)")
                return 0
            else:
                # Report failures
                print(f"\n[FAIL] Task NOT complete: {task.description}")
                print(f"\nFailed criteria ({len(validation.criteria_failed)}):")
                for criterion in validation.criteria_failed:
                    print(f"  - {criterion}")
                    if criterion in validation.failure_details:
                        details = validation.failure_details[criterion]
                        # Truncate long details
                        if len(details) > 200:
                            details = details[:200] + "..."
                        print(f"    {details}")

                if validation.suggestions:
                    print(f"\nSuggestions:")
                    for suggestion in validation.suggestions:
                        print(f"  - {suggestion}")

                return 1

    # No pending tasks
    print("\n[INFO] No pending TODO tasks to validate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
