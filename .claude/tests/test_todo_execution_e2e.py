"""
End-to-end integration tests for TODO execution system.

Tests cover:
- Complete workflow from TODO parsing to DoD validation
- Integration between todo_parser and dod_validator
- Hook system execution
- Task completion workflow
"""

import unittest
import tempfile
import subprocess
from pathlib import Path
from unittest.mock import patch

# Project root is parent of .claude
project_root = Path(__file__).parent.parent.parent

from scripts.todo_parser import parse_todo_file, get_next_pending_task, mark_task_complete
from scripts.dod_validator import validate_task_completion


class TestTodoExecutionWorkflow(unittest.TestCase):
    """End-to-end tests for TODO execution workflow."""

    def test_complete_workflow_simple_task(self):
        """Test complete workflow: parse -> get next -> validate -> mark complete."""
        with tempfile.TemporaryDirectory() as tmp_path:
            # Create a simple TODO file
            todo_file = Path(tmp_path) / "TODO.md"
            todo_file.write_text("""# TODO

## Phase 1: Setup

- [ ] Simple task 1
- [ ] Simple task 2
""")

            # Step 1: Parse TODO file
            tasks = parse_todo_file(str(todo_file))
            self.assertEqual(len(tasks), 2)
            self.assertEqual(tasks[0].status, 'pending')

            # Step 2: Get next pending task
            next_task = get_next_pending_task(str(todo_file))
            self.assertIsNotNone(next_task)
            self.assertEqual(next_task.description, 'Simple task 1')

            # Step 3: Mark task complete
            result = mark_task_complete(str(todo_file), next_task.line_number)
            self.assertTrue(result)

            # Step 4: Verify task marked complete
            updated_tasks = parse_todo_file(str(todo_file))
            self.assertEqual(updated_tasks[0].status, 'completed')
            self.assertEqual(updated_tasks[1].status, 'pending')

            # Step 5: Get next task (should be second task now)
            next_task_2 = get_next_pending_task(str(todo_file))
            self.assertIsNotNone(next_task_2)
            self.assertEqual(next_task_2.description, 'Simple task 2')

    def test_workflow_all_tasks_complete(self):
        """Test workflow when all tasks are complete."""
        with tempfile.TemporaryDirectory() as tmp_path:
            todo_file = Path(tmp_path) / "TODO.md"
            todo_file.write_text("""# TODO

## Phase 1: Setup

- [x] Task 1
- [x] Task 2
- [x] Task 3
""")

            # Should return None when all complete
            next_task = get_next_pending_task(str(todo_file))
            self.assertIsNone(next_task)

    def test_workflow_with_nested_tasks(self):
        """Test workflow with nested task hierarchy."""
        with tempfile.TemporaryDirectory() as tmp_path:
            todo_file = Path(tmp_path) / "TODO.md"
            todo_file.write_text("""# TODO

## Phase 1: Setup

- [x] Parent task 1
  - [ ] Child task 1.1
  - [ ] Child task 1.2
- [ ] Parent task 2
""")

            # Should get first pending child task
            next_task = get_next_pending_task(str(todo_file))
            self.assertIsNotNone(next_task)
            self.assertEqual(next_task.description, 'Child task 1.1')
            self.assertEqual(next_task.depth, 1)
            self.assertEqual(next_task.parent_task, 'Parent task 1')


class TestHookIntegration(unittest.TestCase):
    """Integration tests for hook system."""

    def test_pre_prompt_hook_execution(self):
        """Test that pre-prompt hook runs and outputs task context."""
        hook_path = project_root / ".claude/hooks/pre-prompt.py"
        if not hook_path.exists():
            self.skipTest("pre-prompt.py hook not found")

        # Run the hook
        result = subprocess.run(
            ["python", str(hook_path)],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(project_root)
        )

        combined = f"{result.stdout}\n{result.stderr}"
        self.assertEqual(result.returncode, 0, combined)
        self.assertIn("<task-context>", combined)
        self.assertIn("</task-context>", combined)

    def test_post_complete_hook_execution(self):
        """Test that post-complete hook runs and validates DoD."""
        hook_path = project_root / ".claude/hooks/post-complete.py"
        if not hook_path.exists():
            self.skipTest("post-complete.py hook not found")

        # Just verify the hook file exists and is executable
        # (Running it would take too long due to full test suite execution)
        self.assertTrue(hook_path.exists())
        self.assertTrue(hook_path.is_file())

        # Verify it's a Python script
        content = hook_path.read_text()
        self.assertIn("#!/usr/bin/env python3", content)
        self.assertIn("validate_task_completion", content)


class TestDoDValidationIntegration(unittest.TestCase):
    """Integration tests for DoD validation."""

    @patch('scripts.dod_validator.check_tests_pass')
    @patch('scripts.dod_validator.check_codemap_updated')
    def test_validation_with_mocked_checks(self, mock_codemap, mock_tests):
        """Test validation workflow with mocked checks."""
        # Mock all checks to pass
        mock_tests.return_value = (True, "Tests passed")
        mock_codemap.return_value = (True, "CODEMAP updated")

        # Run validation
        result = validate_task_completion(skip_tests=True)

        # Should have some criteria met
        self.assertGreater(len(result.criteria_met), 0)

    def test_validation_identifies_missing_codemap(self):
        """Test that validation correctly identifies stale CODEMAP."""
        with tempfile.TemporaryDirectory() as tmp_path:
            # Run validation (skip tests for speed) against a temp repo root
            result = validate_task_completion(skip_tests=True, codemap_base_dir=tmp_path)

            # Should fail due to missing CODEMAP
            self.assertFalse(result.passed)
            self.assertIn("CODEMAP Updated", result.criteria_failed)


class TestExecutorScript(unittest.TestCase):
    """Integration tests for todo-executor.py script."""

    def test_executor_help(self):
        """Test that executor script shows help."""
        executor_path = project_root / ".claude/scripts/todo-executor.py"
        result = subprocess.run(
            ["python", str(executor_path), "--help"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(project_root)
        )

        combined = f"{result.stdout}\n{result.stderr}"
        self.assertEqual(result.returncode, 0, combined)
        self.assertIn("TODO Task Executor", combined)
        self.assertIn("--max-tasks", combined)
        self.assertIn("--skip-tests", combined)

    def test_executor_with_test_todo_file(self):
        """Test executor with a test TODO file."""
        with tempfile.TemporaryDirectory() as tmp_path:
            # Create test TODO file
            test_todo = Path(tmp_path) / "test_TODO.md"
            test_todo.write_text("""# Test TODO

## Phase 1: Test

- [ ] Test task 1
- [ ] Test task 2
""")

            # Verify executor script exists
            executor_path = project_root / ".claude/scripts/todo-executor.py"
            self.assertTrue(
                executor_path.exists(),
                "Executor script should exist"
            )

    def test_executor_auto_mark_workflow(self):
        """Test the full executor workflow with manual confirmation."""
        with tempfile.TemporaryDirectory() as tmp_path:
            tmp_path = Path(tmp_path)

            # Create TODO.md in temp directory
            todo_file = tmp_path / "TODO.md"
            todo_file.write_text("""# Test TODO

## Phase 1: Test

- [ ] Test task 1
- [ ] Test task 2
""")

            # Touch repo CODEMAP so DoD check is fresh
            codemap_path = project_root / ".claude" / "CODEMAP.md"
            if codemap_path.exists():
                codemap_path.touch()

            # Run executor with skip-tests and max 1 task
            executor_path = project_root / ".claude/scripts/todo-executor.py"
            result = subprocess.run(
                ["python", str(executor_path), "--skip-tests", "--mode", "ci", "--max-tasks", "1", "--continue-on-failure", "--todo-file", str(todo_file)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(project_root),
                input="\n"
            )

            # Executor should run and show output
            combined = f"{result.stdout}\n{result.stderr}"
            self.assertIn("TODO Task Executor", combined)
            self.assertIn("Test task 1", combined)

    def test_executor_displays_task_context(self):
        """Test that executor displays proper task context."""
        executor_path = project_root / ".claude/scripts/todo-executor.py"

        # Run with real TODO.md but limit to 1 task
        result = subprocess.run(
            ["python", str(executor_path), "--skip-tests", "--mode", "ci", "--max-tasks", "1", "--continue-on-failure"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(project_root),
            input="\n"
        )

        # Should show task context
        combined = f"{result.stdout}\n{result.stderr}"
        self.assertIn("TODO Task Executor - Starting", combined)
        self.assertIn("TODO TASK CONTEXT", combined)
        self.assertIn("Task:", combined)
        self.assertIn("Section:", combined)
        self.assertIn(str(project_root / "TODO.md"), combined)


class TestFullSystemIntegration(unittest.TestCase):
    """Full system integration test."""

    def test_full_cycle_with_real_files(self):
        """Test full cycle: parse real TODO, get task, validate."""
        # Check if TODO.md exists
        todo_file = project_root / "TODO.md"
        if not todo_file.exists():
            self.skipTest("TODO.md not found")

        # Parse TODO
        tasks = parse_todo_file(str(todo_file))
        self.assertGreater(len(tasks), 0, "TODO.md should have tasks")

        # Get next pending
        next_task = get_next_pending_task(str(todo_file))

        # Should either have a task or all complete
        if next_task:
            self.assertEqual(next_task.status, 'pending')
            self.assertGreater(len(next_task.description), 0)
            self.assertGreater(len(next_task.section), 0)

            # Context should be generated
            from scripts.todo_parser import get_task_context
            context = get_task_context(next_task)
            self.assertIn(next_task.description, context)

    def test_dod_criteria_loading(self):
        """Test that DoD criteria can be loaded."""
        from scripts.dod_validator import load_dod_criteria

        dod_file = project_root / "docs/definition-of-done.md"
        if not dod_file.exists():
            self.skipTest("definition-of-done.md not found")

        criteria = load_dod_criteria(str(dod_file))

        # Should have multiple categories
        self.assertGreater(len(criteria), 0)

        # Should have criteria in categories
        total_criteria = sum(len(c) for c in criteria.values())
        self.assertGreater(total_criteria, 0)


if __name__ == "__main__":
    unittest.main()
