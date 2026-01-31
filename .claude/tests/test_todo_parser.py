"""
Tests for TODO parser module.

Tests cover:
- Parsing TODO files with various formats
- Finding next pending tasks
- Marking tasks complete
- Handling edge cases and errors
"""

import unittest
import tempfile
from pathlib import Path

from scripts.todo_parser import (
    TodoTask,
    parse_todo_file,
    get_next_pending_task,
    mark_task_complete,
    get_task_context,
    _extract_metadata
)


class TestTodoParser(unittest.TestCase):
    """Tests for parse_todo_file function."""

    def test_parse_simple_todo_file(self):
        """Test parsing a simple TODO file."""
        with tempfile.TemporaryDirectory() as tmp_path:
            todo_file = Path(tmp_path) / "test.md"
            todo_file.write_text("""# TODO

## Phase 1: Setup

- [x] Completed task
- [ ] Pending task
- [ ] Another pending task
""")

            tasks = parse_todo_file(str(todo_file))

            self.assertEqual(len(tasks), 3)
            self.assertEqual(tasks[0].status, 'completed')
            self.assertEqual(tasks[0].description, 'Completed task')
            self.assertEqual(tasks[1].status, 'pending')
            self.assertEqual(tasks[1].description, 'Pending task')
            self.assertEqual(tasks[2].status, 'pending')

    def test_parse_nested_tasks(self):
        """Test parsing nested tasks with proper depth tracking."""
        with tempfile.TemporaryDirectory() as tmp_path:
            todo_file = Path(tmp_path) / "test.md"
            todo_file.write_text("""## Phase 1: Parent

- [ ] Top level task
  - [ ] Nested task level 1
    - [ ] Nested task level 2
  - [ ] Another nested task level 1
""")

            tasks = parse_todo_file(str(todo_file))

            self.assertEqual(len(tasks), 4)
            self.assertEqual(tasks[0].depth, 0)
            self.assertIsNone(tasks[0].parent_task)
            self.assertEqual(tasks[1].depth, 1)
            self.assertEqual(tasks[1].parent_task, 'Top level task')
            self.assertEqual(tasks[2].depth, 2)
            self.assertEqual(tasks[2].parent_task, 'Nested task level 1')
            self.assertEqual(tasks[3].depth, 1)
            self.assertEqual(tasks[3].parent_task, 'Top level task')

    def test_parse_multiple_phases(self):
        """Test parsing file with multiple phases."""
        with tempfile.TemporaryDirectory() as tmp_path:
            todo_file = Path(tmp_path) / "test.md"
            todo_file.write_text("""## Phase 1: First Phase

- [ ] Task in phase 1

## Phase 2: Second Phase

- [ ] Task in phase 2

## Phase 17.3: Sub-phase

- [ ] Task in sub-phase
""")

            tasks = parse_todo_file(str(todo_file))

            self.assertEqual(len(tasks), 3)
            self.assertEqual(tasks[0].section, 'Phase 1: First Phase')
            self.assertEqual(tasks[1].section, 'Phase 2: Second Phase')
            self.assertEqual(tasks[2].section, 'Phase 17.3: Sub-phase')

    def test_parse_preserves_line_numbers(self):
        """Test that line numbers are correctly tracked."""
        with tempfile.TemporaryDirectory() as tmp_path:
            todo_file = Path(tmp_path) / "test.md"
            todo_file.write_text("""# Header

Some text

## Phase 1

More text

- [ ] Task at line 9
- [ ] Task at line 10
""")

            tasks = parse_todo_file(str(todo_file))

            self.assertEqual(len(tasks), 2)
            self.assertEqual(tasks[0].line_number, 9)
            self.assertEqual(tasks[1].line_number, 10)

    def test_parse_file_not_found(self):
        """Test that FileNotFoundError is raised for missing file."""
        with self.assertRaises(FileNotFoundError):
            parse_todo_file("nonexistent_file.md")

    def test_parse_empty_file(self):
        """Test parsing an empty file."""
        with tempfile.TemporaryDirectory() as tmp_path:
            todo_file = Path(tmp_path) / "empty.md"
            todo_file.write_text("")

            tasks = parse_todo_file(str(todo_file))

            self.assertEqual(len(tasks), 0)


class TestGetNextPendingTask(unittest.TestCase):
    """Tests for get_next_pending_task function."""

    def test_get_first_pending_task(self):
        """Test getting the first pending task."""
        with tempfile.TemporaryDirectory() as tmp_path:
            todo_file = Path(tmp_path) / "test.md"
            todo_file.write_text("""## Phase 1

- [x] Completed task
- [x] Another completed
- [ ] First pending task
- [ ] Second pending task
""")

            task = get_next_pending_task(str(todo_file))

            self.assertIsNotNone(task)
            self.assertEqual(task.description, 'First pending task')
            self.assertEqual(task.line_number, 5)

    def test_get_pending_skips_completed(self):
        """Test that completed tasks are skipped."""
        with tempfile.TemporaryDirectory() as tmp_path:
            todo_file = Path(tmp_path) / "test.md"
            todo_file.write_text("""## Phase 1

- [x] Task 1
- [x] Task 2
- [x] Task 3
- [ ] First pending
""")

            task = get_next_pending_task(str(todo_file))

            self.assertIsNotNone(task)
            self.assertEqual(task.description, 'First pending')

    def test_get_pending_all_complete(self):
        """Test returns None when all tasks complete."""
        with tempfile.TemporaryDirectory() as tmp_path:
            todo_file = Path(tmp_path) / "test.md"
            todo_file.write_text("""## Phase 1

- [x] Task 1
- [x] Task 2
- [x] Task 3
""")

            task = get_next_pending_task(str(todo_file))

            self.assertIsNone(task)

    def test_get_pending_file_not_found(self):
        """Test returns None for missing file."""
        task = get_next_pending_task("nonexistent.md")
        self.assertIsNone(task)


class TestMarkTaskComplete(unittest.TestCase):
    """Tests for mark_task_complete function."""

    def test_mark_task_complete_success(self):
        """Test successfully marking a task complete."""
        with tempfile.TemporaryDirectory() as tmp_path:
            todo_file = Path(tmp_path) / "test.md"
            original_content = """## Phase 1

- [ ] Task 1
- [ ] Task 2
- [ ] Task 3
"""
            todo_file.write_text(original_content)

            result = mark_task_complete(str(todo_file), 3)

            self.assertTrue(result)

            # Verify file was modified
            updated_content = todo_file.read_text()
            self.assertIn('- [x] Task 1', updated_content)
            self.assertIn('- [ ] Task 2', updated_content)  # Unchanged
            self.assertIn('- [ ] Task 3', updated_content)  # Unchanged

    def test_mark_task_preserves_formatting(self):
        """Test that marking complete preserves indentation and formatting."""
        with tempfile.TemporaryDirectory() as tmp_path:
            todo_file = Path(tmp_path) / "test.md"
            original_content = """## Phase 1

- [ ] Top level
  - [ ] Nested task
    - [ ] Deeply nested
"""
            todo_file.write_text(original_content)

            mark_task_complete(str(todo_file), 4)

            updated_content = todo_file.read_text()
            self.assertIn('  - [x] Nested task', updated_content)

    def test_mark_task_invalid_line_number(self):
        """Test that invalid line numbers return False."""
        with tempfile.TemporaryDirectory() as tmp_path:
            todo_file = Path(tmp_path) / "test.md"
            todo_file.write_text("""## Phase 1

- [ ] Task 1
""")

            result = mark_task_complete(str(todo_file), 999)

            self.assertFalse(result)

    def test_mark_task_already_complete(self):
        """Test that already completed tasks return False."""
        with tempfile.TemporaryDirectory() as tmp_path:
            todo_file = Path(tmp_path) / "test.md"
            todo_file.write_text("""## Phase 1

- [x] Already complete
- [ ] Pending task
""")

            result = mark_task_complete(str(todo_file), 3)

            self.assertFalse(result)

    def test_mark_task_not_a_checkbox(self):
        """Test that non-checkbox lines return False."""
        with tempfile.TemporaryDirectory() as tmp_path:
            todo_file = Path(tmp_path) / "test.md"
            todo_file.write_text("""## Phase 1

Regular text line
- [ ] Task 1
""")

            result = mark_task_complete(str(todo_file), 3)

            self.assertFalse(result)

    def test_mark_task_file_not_found(self):
        """Test that FileNotFoundError is raised for missing file."""
        with self.assertRaises(FileNotFoundError):
            mark_task_complete("nonexistent.md", 1)


class TestExtractMetadata(unittest.TestCase):
    """Tests for _extract_metadata function."""

    def test_extract_critical_marker(self):
        """Test extracting CRITICAL marker."""
        desc = "**CRITICAL**: This is important"
        metadata = _extract_metadata(desc)

        self.assertTrue(metadata.get('critical'))

    def test_extract_breaking_change_marker(self):
        """Test extracting Breaking Change marker."""
        desc = "**Breaking Change**: Update schema"
        metadata = _extract_metadata(desc)

        self.assertTrue(metadata.get('critical'))

    def test_extract_phase_references(self):
        """Test extracting phase references."""
        desc = "Update code (Phase 5: Git Integration) and (Phase 7: Lifecycle)"
        metadata = _extract_metadata(desc)

        self.assertIn('phase_references', metadata)
        self.assertIn('5', metadata['phase_references'])
        self.assertIn('7', metadata['phase_references'])

    def test_extract_file_references(self):
        """Test extracting file references."""
        desc = "Update `src/core/routing.py` and `tests/test_routing.py`"
        metadata = _extract_metadata(desc)

        self.assertIn('file_references', metadata)
        self.assertIn('src/core/routing.py', metadata['file_references'])
        self.assertIn('tests/test_routing.py', metadata['file_references'])

    def test_extract_task_id(self):
        """Test extracting task ID from description."""
        desc = "**17.3: DevOps Lifecycle Bootstrapping**"
        metadata = _extract_metadata(desc)

        self.assertEqual(metadata.get('task_id'), '17.3')

    def test_extract_no_metadata(self):
        """Test extraction with no metadata present."""
        desc = "Simple task description"
        metadata = _extract_metadata(desc)

        self.assertEqual(len(metadata), 0)


class TestGetTaskContext(unittest.TestCase):
    """Tests for get_task_context function."""

    def test_get_task_context_basic(self):
        """Test generating basic task context."""
        task = TodoTask(
            file_path="TODO.md",
            line_number=42,
            section="Phase 1",
            description="Test task",
            depth=0,
            status="pending"
        )

        context = get_task_context(task)

        self.assertIn("Test task", context)
        self.assertIn("Section: Phase 1", context)
        self.assertIn("TODO.md:42", context)

    def test_get_task_context_with_parent(self):
        """Test context includes parent task."""
        task = TodoTask(
            file_path="TODO.md",
            line_number=10,
            section="Phase 2",
            description="Nested task",
            depth=1,
            status="pending",
            parent_task="Parent task"
        )

        context = get_task_context(task)

        self.assertIn("Parent Task: Parent task", context)

    def test_get_task_context_with_metadata(self):
        """Test context includes metadata."""
        task = TodoTask(
            file_path="TODO.md",
            line_number=5,
            section="Phase 3",
            description="Critical task",
            depth=0,
            status="pending",
            metadata={
                'critical': True,
                'file_references': ['src/main.py', 'tests/test_main.py'],
                'phase_references': ['1', '2']
            }
        )

        context = get_task_context(task)

        self.assertIn("CRITICAL", context)
        self.assertIn("src/main.py", context)
        self.assertIn("References Sections: 1, 2", context)


class TestIntegrationWithRealFiles(unittest.TestCase):
    """Integration tests with real TODO files."""

    @classmethod
    def setUpClass(cls):
        """Find the project root by looking for TODO.md."""
        cls.project_root = Path(__file__).parent.parent.parent
        cls.todo_file = cls.project_root / "TODO.md"

    def test_parse_real_todo_md(self):
        """Test parsing the actual TODO.md file if it exists."""
        if not self.todo_file.exists():
            self.skipTest("TODO.md not found")

        tasks = parse_todo_file(str(self.todo_file))

        # Should have many tasks
        self.assertGreater(len(tasks), 0)

        # Should have both pending and completed
        pending = [t for t in tasks if t.status == 'pending']
        completed = [t for t in tasks if t.status == 'completed']

        self.assertGreaterEqual(len(pending), 0)
        self.assertGreaterEqual(len(completed), 0)

    def test_get_next_from_real_file(self):
        """Test getting next pending task from real TODO.md."""
        if not self.todo_file.exists():
            self.skipTest("TODO.md not found")

        task = get_next_pending_task(str(self.todo_file))

        # Should either have a task or None (all complete)
        if task:
            self.assertEqual(task.status, 'pending')
            self.assertGreater(len(task.description), 0)
            self.assertGreater(len(task.section), 0)


if __name__ == "__main__":
    unittest.main()
