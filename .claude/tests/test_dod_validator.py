"""
Tests for Definition of Done validator module.

Tests cover:
- Loading DoD criteria from file
- Running automated validation checks
- Generating actionable feedback
- Handling edge cases and errors
"""

import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from scripts.dod_validator import (
    ValidationResult,
    load_dod_criteria,
    check_tests_pass,
    check_codemap_updated,
    check_type_hints,
    check_docstrings,
    check_no_todos,
    validate_task_completion
)


class TestValidationResult(unittest.TestCase):
    """Tests for ValidationResult dataclass."""

    def test_validation_result_passed(self):
        """Test ValidationResult when all criteria met."""
        result = ValidationResult(
            passed=True,
            criteria_met=['Test 1', 'Test 2'],
            criteria_failed=[],
            failure_details={},
            suggestions=[]
        )

        self.assertTrue(result.passed)
        self.assertEqual(len(result.criteria_met), 2)
        self.assertEqual(len(result.criteria_failed), 0)
        self.assertIn("All 2 DoD criteria met", str(result))

    def test_validation_result_failed(self):
        """Test ValidationResult when some criteria failed."""
        result = ValidationResult(
            passed=False,
            criteria_met=['Test 1'],
            criteria_failed=['Test 2', 'Test 3'],
            failure_details={
                'Test 2': 'Reason 2',
                'Test 3': 'Reason 3'
            },
            suggestions=['Fix 2', 'Fix 3']
        )

        self.assertFalse(result.passed)
        self.assertEqual(len(result.criteria_met), 1)
        self.assertEqual(len(result.criteria_failed), 2)
        self.assertIn("2 criteria failed", str(result))


class TestLoadDodCriteria(unittest.TestCase):
    """Tests for load_dod_criteria function."""

    def test_load_dod_criteria_success(self):
        """Test successfully loading DoD criteria from file."""
        with tempfile.TemporaryDirectory() as tmp_path:
            dod_file = Path(tmp_path) / "dod.md"
            dod_file.write_text("""# Definition of Done

## Category 1: Tests

- [ ] All tests must pass
- [ ] Code coverage > 80%
- Unit tests exist

## Category 2: Documentation

- [ ] README updated
- Docstrings present
""")

            criteria = load_dod_criteria(str(dod_file))

            self.assertEqual(len(criteria), 2)
            self.assertIn('Category 1: Tests', criteria)
            self.assertIn('Category 2: Documentation', criteria)
            self.assertEqual(len(criteria['Category 1: Tests']), 3)
            self.assertEqual(len(criteria['Category 2: Documentation']), 2)

    def test_load_dod_criteria_file_not_found(self):
        """Test that FileNotFoundError is raised for missing file."""
        with self.assertRaises(FileNotFoundError):
            load_dod_criteria("nonexistent_dod.md")

    def test_load_dod_criteria_empty_file(self):
        """Test loading from empty file."""
        with tempfile.TemporaryDirectory() as tmp_path:
            dod_file = Path(tmp_path) / "empty_dod.md"
            dod_file.write_text("")

            criteria = load_dod_criteria(str(dod_file))

            self.assertEqual(len(criteria), 0)

    def test_load_dod_criteria_with_unicode(self):
        """Test loading DoD file with unicode check marks."""
        with tempfile.TemporaryDirectory() as tmp_path:
            dod_file = Path(tmp_path) / "dod.md"
            dod_file.write_text("""# Definition of Done

## Category 1 ✓

- [ ] Criterion 1
- [ ] Criterion 2
""", encoding='utf-8')

            criteria = load_dod_criteria(str(dod_file))

            self.assertEqual(len(criteria), 1)
            # Category name should include unicode
            category_names = list(criteria.keys())
            self.assertTrue(any('Category 1' in name for name in category_names))


class TestCheckTypeHints(unittest.TestCase):
    """Tests for check_type_hints function."""

    def test_check_type_hints_all_present(self):
        """Test with file that has all type hints."""
        with tempfile.TemporaryDirectory() as tmp_path:
            test_file = Path(tmp_path) / "test.py"
            test_file.write_text("""
def function_with_hints(x: int, y: str) -> bool:
    return True

def another_function(a: float) -> int:
    return 42
""")

            passed, details = check_type_hints([str(test_file)])

            self.assertTrue(passed)
            self.assertIn("have type hints", details)

    def test_check_type_hints_missing(self):
        """Test with file missing type hints."""
        with tempfile.TemporaryDirectory() as tmp_path:
            test_file = Path(tmp_path) / "test.py"
            test_file.write_text("""
def function_without_hints(x, y):
    return True

def another_function(a):
    return 42
""")

            passed, details = check_type_hints([str(test_file)])

            self.assertFalse(passed)
            self.assertIn("Missing type hints", details)

    def test_check_type_hints_private_functions_skipped(self):
        """Test that private functions are skipped."""
        with tempfile.TemporaryDirectory() as tmp_path:
            test_file = Path(tmp_path) / "test.py"
            test_file.write_text("""
def _private_function(x, y):
    # Private functions can skip type hints
    return True

def public_function(a: int) -> str:
    return "hello"
""")

            passed, details = check_type_hints([str(test_file)])

            self.assertTrue(passed)

    def test_check_type_hints_no_python_files(self):
        """Test with no Python files."""
        passed, details = check_type_hints(["file.txt", "file.md"])

        self.assertTrue(passed)
        self.assertIn("No Python files", details)


class TestCheckDocstrings(unittest.TestCase):
    """Tests for check_docstrings function."""

    def test_check_docstrings_all_present(self):
        """Test with file that has all docstrings."""
        with tempfile.TemporaryDirectory() as tmp_path:
            test_file = Path(tmp_path) / "test.py"
            test_file.write_text('''
def function_with_docstring(x: int) -> bool:
    """This function has a docstring."""
    return True

def another_function(a: float) -> int:
    """This too."""
    return 42
''')

            passed, details = check_docstrings([str(test_file)])

            self.assertTrue(passed)

    def test_check_docstrings_missing(self):
        """Test with file missing docstrings."""
        with tempfile.TemporaryDirectory() as tmp_path:
            test_file = Path(tmp_path) / "test.py"
            test_file.write_text('''
def function_without_docstring(x: int) -> bool:
    return True

def another_function(a: float) -> int:
    return 42
''')

            passed, details = check_docstrings([str(test_file)])

            self.assertFalse(passed)
            self.assertIn("Missing docstrings", details)

    def test_check_docstrings_no_python_files(self):
        """Test with no Python files."""
        passed, details = check_docstrings(["file.txt"])

        self.assertTrue(passed)
        self.assertIn("No Python files", details)


class TestCheckNoTodos(unittest.TestCase):
    """Tests for check_no_todos function."""

    def test_check_no_todos_clean(self):
        """Test with file that has no TODO comments."""
        with tempfile.TemporaryDirectory() as tmp_path:
            test_file = Path(tmp_path) / "test.py"
            test_file.write_text("""
def function():
    # This is a normal comment
    return True
""")

            passed, details = check_no_todos([str(test_file)])

            self.assertTrue(passed)
            self.assertIn("No untracked TODO", details)

    def test_check_no_todos_found(self):
        """Test with file containing TODO comments."""
        with tempfile.TemporaryDirectory() as tmp_path:
            test_file = Path(tmp_path) / "test.py"
            test_file.write_text("""
def function():
    # TODO Fix this later
    return True
""")

            passed, details = check_no_todos([str(test_file)])

            self.assertFalse(passed)
            self.assertIn("Untracked TODOs found", details)

    def test_check_no_todos_non_code_files_skipped(self):
        """Test that non-code files are skipped."""
        passed, details = check_no_todos(["README.md", "config.json"])

        self.assertTrue(passed)


class TestCheckCodemapUpdated(unittest.TestCase):
    """Tests for check_codemap_updated function."""

    def test_check_codemap_updated_recent(self):
        """Test with recently updated CODEMAP.md."""
        with tempfile.TemporaryDirectory() as tmp_path:
            # Create CODEMAP.md in temp directory
            claude_dir = Path(tmp_path) / ".claude"
            claude_dir.mkdir(parents=True, exist_ok=True)
            codemap = claude_dir / "CODEMAP.md"
            codemap.write_text("# Codemap")

            passed, details = check_codemap_updated(tmp_path)
            self.assertTrue(passed)
            self.assertIn("updated recently", details)

    def test_check_codemap_not_exists(self):
        """Test with missing CODEMAP.md."""
        with tempfile.TemporaryDirectory() as tmp_path:
            passed, details = check_codemap_updated(tmp_path)
            self.assertFalse(passed)
            self.assertIn("does not exist", details)


class TestValidateTaskCompletion(unittest.TestCase):
    """Tests for validate_task_completion function."""

    @patch('scripts.dod_validator.check_tests_pass')
    @patch('scripts.dod_validator.check_codemap_updated')
    @patch('scripts.dod_validator.check_type_hints')
    @patch('scripts.dod_validator.check_docstrings')
    @patch('scripts.dod_validator.check_no_todos')
    @patch('scripts.dod_validator.check_imports')
    def test_validate_task_completion_all_pass(
        self,
        mock_imports,
        mock_todos,
        mock_docstrings,
        mock_hints,
        mock_codemap,
        mock_tests
    ):
        """Test validation when all checks pass."""
        # Mock all checks to pass
        mock_tests.return_value = (True, "Tests passed")
        mock_codemap.return_value = (True, "CODEMAP updated")
        mock_hints.return_value = (True, "Type hints present")
        mock_docstrings.return_value = (True, "Docstrings present")
        mock_todos.return_value = (True, "No TODOs")
        mock_imports.return_value = (True, "No import errors")

        result = validate_task_completion(skip_tests=False)

        self.assertTrue(result.passed)
        self.assertEqual(len(result.criteria_met), 7)
        self.assertEqual(len(result.criteria_failed), 0)
        self.assertEqual(len(result.suggestions), 0)

    @patch('scripts.dod_validator.check_tests_pass')
    @patch('scripts.dod_validator.check_codemap_updated')
    @patch('scripts.dod_validator.check_type_hints')
    @patch('scripts.dod_validator.check_docstrings')
    @patch('scripts.dod_validator.check_no_todos')
    @patch('scripts.dod_validator.check_imports')
    def test_validate_task_completion_some_fail(
        self,
        mock_imports,
        mock_todos,
        mock_docstrings,
        mock_hints,
        mock_codemap,
        mock_tests
    ):
        """Test validation when some checks fail."""
        # Mock some checks to fail
        mock_tests.return_value = (False, "Tests failed")
        mock_codemap.return_value = (False, "CODEMAP not updated")
        mock_hints.return_value = (True, "Type hints present")
        mock_docstrings.return_value = (True, "Docstrings present")
        mock_todos.return_value = (True, "No TODOs")
        mock_imports.return_value = (True, "No import errors")

        result = validate_task_completion(skip_tests=False)

        self.assertFalse(result.passed)
        self.assertEqual(len(result.criteria_met), 5)
        self.assertEqual(len(result.criteria_failed), 2)
        self.assertGreater(len(result.suggestions), 0)
        self.assertIn("Tests Pass", result.criteria_failed)
        self.assertIn("CODEMAP Updated", result.criteria_failed)

    def test_validate_task_completion_skip_tests(self):
        """Test validation with skip_tests flag."""
        result = validate_task_completion(skip_tests=True)

        # Should not run tests but should run other checks
        # Exact results depend on system state, just verify it runs
        self.assertIsInstance(result, ValidationResult)
        self.assertIn("Tests Pass", result.criteria_met)  # Should be marked as met when skipped

    @patch('scripts.dod_validator.check_imports')
    def test_validate_task_completion_with_exception(self, mock_imports):
        """Test validation handles exceptions gracefully."""
        # Mock one check to raise exception
        mock_imports.side_effect = Exception("Test exception")

        result = validate_task_completion(skip_tests=True)

        # Should handle exception and mark as failed
        self.assertFalse(result.passed)
        self.assertIn("No Import Errors", result.criteria_failed)
        self.assertIn("Check failed with error", result.failure_details["No Import Errors"])


class TestIntegrationWithRealDoD(unittest.TestCase):
    """Integration tests with real DoD file."""

    def test_load_real_dod_file(self):
        """Test loading the actual definition-of-done.md file."""
        dod_file = Path("docs/definition-of-done.md")
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
