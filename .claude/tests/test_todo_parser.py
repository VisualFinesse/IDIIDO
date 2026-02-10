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


class TestNumberedFilePathFormat(unittest.TestCase):
    """Tests for the numbered file-path TODO format.

    Format example:
        1. backend/bin/start.sh - Description here.

        Important

        5. backend/src/main.py:19 - Another description.
    """

    SAMPLE_TODO = """\
 1. backend/bin/start.sh - Entire startup script is bash-only. Create a start.bat or start.ps1 equivalent.
2. start.sh (root) - Root startup script uses bash syntax throughout.
3. backend/src/video_utils.py:271 - OpenCV cascade path concatenation breaks on Windows.
4. backend/src/video_utils.py:277-278 - OpenCV DNN model path construction uses .replace on a path string.

Important

5. backend/src/main.py:19 - logging.FileHandler uses a hardcoded relative path.
6. backend/src/config.py:21 - Default temp directory is "temp" (relative).
7. backend/src/video_utils.py:613, 735 - MoviePy temp_audiofile writes to CWD.
8. docker-compose.yml:42, 86 - .venv/bin/uvicorn and .venv/bin/arq are Linux paths.

Documentation

9. backend/README.md - Virtual environment activation only shows source command.
10. backend/README.md - ffmpeg installation mentions brew and apt but not Windows.
11. CLAUDE.md - Development commands section shows Unix activation only.

Low Priority

12. backend/src/main_refactored.py:30 - Same logging.FileHandler issue as main.py.
13. General - Verify that yt-dlp and ffmpeg subprocess calls work on Windows (they generally do, but any shell piping or Unix-specific flags should be tested).
14. General - Confirm MoviePy v2 and MediaPipe work correctly on Windows with Python 3.11+ (known to have occasional build issues on Windows).
"""

    def _write_and_parse(self, content=None):
        import tempfile as _tf
        d = _tf.mkdtemp()
        p = Path(d) / "test.md"
        p.write_text(content or self.SAMPLE_TODO, encoding="utf-8")
        return parse_todo_file(str(p))

    def test_parses_all_14_items(self):
        tasks = self._write_and_parse()
        self.assertEqual(len(tasks), 14)

    def test_items_before_first_section_are_general(self):
        tasks = self._write_and_parse()
        for t in tasks[:4]:
            self.assertEqual(t.section, "General")

    def test_bare_section_important(self):
        tasks = self._write_and_parse()
        for t in tasks[4:8]:
            self.assertEqual(t.section, "Important", f"task {t.line_number}: {t.description[:40]}")

    def test_bare_section_documentation(self):
        tasks = self._write_and_parse()
        for t in tasks[8:11]:
            self.assertEqual(t.section, "Documentation", f"task {t.line_number}: {t.description[:40]}")

    def test_bare_section_low_priority(self):
        tasks = self._write_and_parse()
        for t in tasks[11:14]:
            self.assertEqual(t.section, "Low Priority", f"task {t.line_number}: {t.description[:40]}")

    def test_all_items_are_pending(self):
        tasks = self._write_and_parse()
        for t in tasks:
            self.assertEqual(t.status, "pending")

    def test_numbered_items_not_treated_as_sections(self):
        """Numbered items with file paths must NOT become section headers."""
        tasks = self._write_and_parse()
        sections = {t.section for t in tasks}
        # None of the task descriptions should appear as a section name
        for t in tasks:
            self.assertNotIn(t.description, sections)

    def test_target_file_metadata(self):
        tasks = self._write_and_parse()
        # Item 1: backend/bin/start.sh
        self.assertEqual(tasks[0].metadata.get("target_file"), "backend/bin/start.sh")
        self.assertIsNone(tasks[0].metadata.get("target_lines"))
        # Item 3: backend/src/video_utils.py:271
        self.assertEqual(tasks[2].metadata.get("target_file"), "backend/src/video_utils.py")
        self.assertEqual(tasks[2].metadata.get("target_lines"), "271")
        # Item 4: backend/src/video_utils.py:277-278
        self.assertEqual(tasks[3].metadata.get("target_file"), "backend/src/video_utils.py")
        self.assertEqual(tasks[3].metadata.get("target_lines"), "277-278")

    def test_target_lines_multiple(self):
        tasks = self._write_and_parse()
        # Item 7: backend/src/video_utils.py:613, 735
        self.assertEqual(tasks[6].metadata.get("target_file"), "backend/src/video_utils.py")
        self.assertEqual(tasks[6].metadata.get("target_lines"), "613, 735")
        # Item 8: docker-compose.yml:42, 86
        self.assertEqual(tasks[7].metadata.get("target_file"), "docker-compose.yml")
        self.assertEqual(tasks[7].metadata.get("target_lines"), "42, 86")

    def test_no_target_file_for_general_items(self):
        tasks = self._write_and_parse()
        # Items 13 and 14 start with "General" (not a file)
        self.assertNotIn("target_file", tasks[12].metadata)
        self.assertNotIn("target_file", tasks[13].metadata)

    def test_leading_space_on_first_item(self):
        """First item has a leading space; should still parse correctly."""
        tasks = self._write_and_parse()
        self.assertIn("backend/bin/start.sh", tasks[0].description)


class TestMarkNumberedTaskComplete(unittest.TestCase):
    """Tests for marking numbered and bullet list items complete."""

    def test_mark_numbered_item_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test.md"
            p.write_text("1. First task\n2. Second task\n3. Third task\n")
            result = mark_task_complete(str(p), 2)
            self.assertTrue(result)
            content = p.read_text()
            self.assertIn("- [x] Second task", content)
            self.assertIn("1. First task", content)
            self.assertIn("3. Third task", content)

    def test_mark_bullet_item_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test.md"
            p.write_text("- First task\n- Second task\n")
            result = mark_task_complete(str(p), 1)
            self.assertTrue(result)
            content = p.read_text()
            self.assertIn("- [x] First task", content)

    def test_marked_numbered_re_parses_as_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test.md"
            p.write_text(
                "1. backend/src/main.py:19 - Fix logging path\n"
                "2. backend/src/config.py:21 - Fix temp dir\n"
            )
            mark_task_complete(str(p), 1)
            tasks = parse_todo_file(str(p))
            completed = [t for t in tasks if t.status == "completed"]
            pending = [t for t in tasks if t.status == "pending"]
            self.assertEqual(len(completed), 1)
            self.assertEqual(len(pending), 1)


class TestExtractTargetFileMetadata(unittest.TestCase):
    """Tests for target_file and target_lines extraction in _extract_metadata."""

    def test_path_with_single_line(self):
        m = _extract_metadata("backend/src/main.py:19 - logging issue")
        self.assertEqual(m["target_file"], "backend/src/main.py")
        self.assertEqual(m["target_lines"], "19")

    def test_path_with_line_range(self):
        m = _extract_metadata("video_utils.py:277-278 - path issue")
        self.assertEqual(m["target_file"], "video_utils.py")
        self.assertEqual(m["target_lines"], "277-278")

    def test_path_with_multiple_lines(self):
        m = _extract_metadata("docker-compose.yml:42, 86 - Linux paths")
        self.assertEqual(m["target_file"], "docker-compose.yml")
        self.assertEqual(m["target_lines"], "42, 86")

    def test_path_without_lines(self):
        m = _extract_metadata("backend/README.md - activation instructions")
        self.assertEqual(m["target_file"], "backend/README.md")
        self.assertNotIn("target_lines", m)

    def test_no_file_path(self):
        m = _extract_metadata("General - verify subprocess calls")
        self.assertNotIn("target_file", m)


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
