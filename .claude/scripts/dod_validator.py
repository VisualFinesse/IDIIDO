"""
Definition of Done Validator - Automated task completion validation.

This module provides functionality to:
- Load and parse definition-of-done.md criteria
- Run automated checks against task completion
- Validate tests pass, CODEMAP updated, code quality maintained
- Generate actionable feedback for incomplete criteria

REFERENCE: Part of TODO execution system for validation before task completion
"""

import subprocess
import re
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """
    Result of validating a task against Definition of Done criteria.

    Attributes:
        passed: Whether all criteria were met
        criteria_met: List of criteria that passed
        criteria_failed: List of criteria that failed
        failure_details: Details about each failure
        suggestions: Actionable suggestions to fix failures
    """
    passed: bool
    criteria_met: List[str] = field(default_factory=list)
    criteria_failed: List[str] = field(default_factory=list)
    failure_details: Dict[str, str] = field(default_factory=dict)
    suggestions: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        """Human-readable representation."""
        if self.passed:
            return f"[PASS] All {len(self.criteria_met)} DoD criteria met"
        else:
            return f"[FAIL] {len(self.criteria_failed)} criteria failed (of {len(self.criteria_met) + len(self.criteria_failed)})"


def _resolve_default_dod_path() -> Path:
    claude_root = Path(__file__).resolve().parent.parent
    repo_root = claude_root.parent

    candidates = [
        repo_root / "docs" / "definition-of-done.md",
        claude_root / "definition-of-done.md",
        repo_root / "definition-of-done.md",
    ]
    for cand in candidates:
        if cand.exists():
            return cand
    return candidates[0]


def load_dod_criteria(dod_file: Optional[str] = None) -> Dict[str, List[str]]:
    """
    Parse definition-of-done.md and extract criteria categories.

    Args:
        dod_file: Path to definition-of-done.md (optional)

    Returns:
        Dictionary mapping category names to lists of criteria

    Raises:
        FileNotFoundError: If DoD file does not exist
    """
    path = Path(dod_file) if dod_file else _resolve_default_dod_path()
    if not path.exists():
        raise FileNotFoundError(f"Definition of Done file not found: {path}")

    criteria: Dict[str, List[str]] = {}
    current_category = None

    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip()

            # Category headers (## Category Name)
            if line.startswith('## '):
                current_category = line[3:].strip()
                criteria[current_category] = []
                continue

            # Criteria items (- [ ] Item or - Item)
            if current_category and (line.startswith('- [ ]') or line.startswith('- ')):
                criterion = line.lstrip('- [ ] ').strip()
                if criterion:
                    criteria[current_category].append(criterion)

    logger.info(f"Loaded {len(criteria)} DoD categories from {path}")
    return criteria


def _check_dod_criteria(dod_file: Optional[str]) -> Tuple[bool, str]:
    try:
        criteria = load_dod_criteria(dod_file)
    except FileNotFoundError as e:
        return False, str(e)

    if not criteria:
        return False, "Definition of Done file is empty or missing criteria"

    total = sum(len(items) for items in criteria.values())
    if total == 0:
        return False, "Definition of Done file has no checklist items"

    return True, f"Loaded {len(criteria)} DoD categories ({total} criteria)"


def check_tests_pass() -> tuple[bool, str]:
    """
    Run test suite and verify it passes.

    Returns:
        Tuple of (passed: bool, details: str)
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest"],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )

        if result.returncode == 0:
            return True, "Tests passed (exit code 0)"
        return False, f"Tests failed (exit code {result.returncode})\n{result.stdout}\n{result.stderr}"

    except subprocess.TimeoutExpired:
        return False, "Tests timed out after 5 minutes"
    except Exception as e:
        return False, f"Error running tests: {str(e)}"


def _resolve_codemap_path(base_dir: Optional[Path] = None) -> Path:
    if base_dir is None:
        claude_root = Path(__file__).resolve().parent.parent
        repo_root = claude_root.parent
    else:
        base_dir = Path(base_dir).resolve()
        if base_dir.name == ".claude":
            claude_root = base_dir
            repo_root = base_dir.parent
        else:
            repo_root = base_dir
            claude_root = base_dir / ".claude"

    claude_codemap = claude_root / "CODEMAP.md"
    repo_codemap = repo_root / "CODEMAP.md"

    if claude_codemap.exists():
        return claude_codemap
    if repo_codemap.exists():
        return repo_codemap
    return claude_codemap


def check_codemap_updated(base_dir: Optional[Path] = None) -> tuple[bool, str]:
    """
    Verify CODEMAP.md exists and has recent modification time.

    Returns:
        Tuple of (passed: bool, details: str)
    """
    codemap_path = _resolve_codemap_path(base_dir)

    if not codemap_path.exists():
        return False, f"CODEMAP.md does not exist at {codemap_path}"

    # Check if modified recently (within last 5 minutes)
    import time
    mtime = codemap_path.stat().st_mtime
    age_seconds = time.time() - mtime

    if age_seconds > 300:  # 5 minutes
        return False, (
            f"CODEMAP.md at {codemap_path} was last modified "
            f"{int(age_seconds/60)} minutes ago (should be regenerated)"
        )

    return True, f"CODEMAP.md at {codemap_path} updated recently ({int(age_seconds)} seconds ago)"


def check_type_hints(changed_files: List[str]) -> tuple[bool, str]:
    """
    Verify Python files have type hints on functions.

    Args:
        changed_files: List of file paths that were modified

    Returns:
        Tuple of (passed: bool, details: str)
    """
    python_files = [f for f in changed_files if f.endswith('.py')]

    if not python_files:
        return True, "No Python files to check"

    files_without_hints = []

    for file_path in python_files:
        path = Path(file_path)
        if not path.exists():
            continue

        try:
            content = path.read_text(encoding='utf-8')

            # Find function definitions
            func_defs = re.findall(r'^(\s*)def\s+(\w+)\s*\(([^)]*)\)', content, re.MULTILINE)

            for indent, func_name, params in func_defs:
                # Skip private functions (start with _)
                if func_name.startswith('_') and func_name != '__init__':
                    continue

                # Check if function has return type hint
                # Look for -> in the function signature
                func_pattern = rf'def\s+{re.escape(func_name)}\s*\([^)]*\)\s*->'
                if not re.search(func_pattern, content):
                    files_without_hints.append(f"{file_path}:{func_name}")

        except Exception as e:
            logger.warning(f"Error checking type hints in {file_path}: {e}")

    if files_without_hints:
        return False, f"Missing type hints in: {', '.join(files_without_hints[:5])}"

    return True, f"All {len(python_files)} Python files have type hints"


def check_docstrings(changed_files: List[str]) -> tuple[bool, str]:
    """
    Verify Python files have docstrings on new functions.

    Args:
        changed_files: List of file paths that were modified

    Returns:
        Tuple of (passed: bool, details: str)
    """
    python_files = [f for f in changed_files if f.endswith('.py')]

    if not python_files:
        return True, "No Python files to check"

    files_without_docstrings = []

    for file_path in python_files:
        path = Path(file_path)
        if not path.exists():
            continue

        try:
            content = path.read_text(encoding='utf-8')

            # Find function definitions
            func_defs = re.findall(r'(^|\n)([ ]*)def\s+(\w+)\s*\([^)]*\).*?:\s*\n([ ]*)("""|\'\'\')(.*?)\5',
                                   content, re.DOTALL | re.MULTILINE)

            # Also find functions without docstrings
            all_funcs = re.findall(r'^(\s*)def\s+(\w+)\s*\(', content, re.MULTILINE)
            funcs_with_docs = [match[2] for match in func_defs]

            for indent, func_name in all_funcs:
                # Skip private functions
                if func_name.startswith('_') and func_name != '__init__':
                    continue

                if func_name not in funcs_with_docs:
                    files_without_docstrings.append(f"{file_path}:{func_name}")

        except Exception as e:
            logger.warning(f"Error checking docstrings in {file_path}: {e}")

    if files_without_docstrings:
        return False, f"Missing docstrings in: {', '.join(files_without_docstrings[:5])}"

    return True, f"All {len(python_files)} Python files have docstrings"


def check_no_todos(changed_files: List[str]) -> tuple[bool, str]:
    """
    Verify no untracked TODO comments in code.

    Args:
        changed_files: List of file paths that were modified

    Returns:
        Tuple of (passed: bool, details: str)
    """
    todos_found = []

    for file_path in changed_files:
        path = Path(file_path)
        if not path.exists() or not path.suffix in ['.py', '.js', '.ts', '.go', '.java']:
            continue

        try:
            content = path.read_text(encoding='utf-8')
            lines = content.split('\n')

            for line_num, line in enumerate(lines, 1):
                # Look for TODO comments (but not in TODO.md files)
                if re.search(r'#\s*TODO[^:]|//\s*TODO[^:]|/\*\s*TODO[^:]', line, re.IGNORECASE):
                    todos_found.append(f"{file_path}:{line_num}")

        except Exception as e:
            logger.warning(f"Error checking TODOs in {file_path}: {e}")

    if todos_found:
        return False, f"Untracked TODOs found: {', '.join(todos_found[:5])}"

    return True, "No untracked TODO comments"


def check_imports() -> tuple[bool, str]:
    """
    Basic check for circular imports (attempts to import all Python files).

    Returns:
        Tuple of (passed: bool, details: str)
    """
    # Simple check: try to import all modules in src/
    src_path = Path("src")
    if not src_path.exists():
        return True, "No src/ directory to check"

    try:
        # Use Python to check for import errors
        result = subprocess.run(
            ["python", "-c", "import sys; sys.path.insert(0, '.'); import src"],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            return True, "No import errors detected"
        else:
            return False, f"Import check failed: {result.stderr}"

    except subprocess.TimeoutExpired:
        return False, "Import check timed out"
    except Exception as e:
        return False, f"Error checking imports: {str(e)}"


def validate_task_completion(
    changed_files: Optional[List[str]] = None,
    skip_tests: bool = False,
    codemap_base_dir: Optional[Path] = None,
    check_codemap: bool = True,
    dod_file: Optional[str] = None,
) -> ValidationResult:
    """
    Validate that a task meets all Definition of Done criteria.

    Args:
        changed_files: List of file paths that were modified (optional, for file-specific checks)
        skip_tests: Skip running tests (useful for testing the validator itself)
        check_codemap: Enable CODEMAP freshness check
    Returns:
        ValidationResult with pass/fail and details
    """
    if changed_files is None:
        changed_files = []

    result = ValidationResult(passed=True)

    # Run all automated checks
    checks = {
        "DoD Criteria Loaded": lambda: _check_dod_criteria(dod_file),
        "Tests Pass": check_tests_pass if not skip_tests else lambda: (True, "Tests skipped"),
        "CODEMAP Updated": (
            lambda: check_codemap_updated(codemap_base_dir)
            if check_codemap
            else (True, "CODEMAP check skipped")
        ),
        "Type Hints Present": lambda: check_type_hints(changed_files),
        "Docstrings Present": lambda: check_docstrings(changed_files),
        "No Untracked TODOs": lambda: check_no_todos(changed_files),
        "No Import Errors": check_imports,
    }

    for criterion_name, check_func in checks.items():
        try:
            passed, details = check_func()

            if passed:
                result.criteria_met.append(criterion_name)
                logger.debug(f"[PASS] {criterion_name}: {details}")
            else:
                result.criteria_failed.append(criterion_name)
                result.failure_details[criterion_name] = details
                result.passed = False
                logger.warning(f"[FAIL] {criterion_name}: {details}")

        except Exception as e:
            result.criteria_failed.append(criterion_name)
            result.failure_details[criterion_name] = f"Check failed with error: {str(e)}"
            result.passed = False
            logger.error(f"[ERROR] {criterion_name}: {str(e)}")

    # Generate suggestions based on failures
    if "Tests Pass" in result.criteria_failed:
        result.suggestions.append("Run tests locally: python -m pytest")
        result.suggestions.append("Fix failing tests before marking task complete")

    if "DoD Criteria Loaded" in result.criteria_failed:
        result.suggestions.append("Ensure definition-of-done.md exists and has checklist items")

    if "CODEMAP Updated" in result.criteria_failed:
        result.suggestions.append("Regenerate CODEMAP: python .claude/scripts/codemap.py")

    if "Type Hints Present" in result.criteria_failed:
        result.suggestions.append("Add type hints to function signatures: def func(...) -> ReturnType:")

    if "Docstrings Present" in result.criteria_failed:
        result.suggestions.append("Add docstrings to public functions using triple quotes")

    if "No Untracked TODOs" in result.criteria_failed:
        result.suggestions.append("Remove TODO comments or add them to TODO.md")

    logger.info(f"Validation result: {result}")
    return result


# Example usage
if __name__ == "__main__":
    import sys
    import io

    # Configure logging
    logging.basicConfig(level=logging.INFO)

    # Fix encoding for Windows console
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    # Test DoD validation
    print("\n=== Definition of Done Validation ===\n")

    try:
        # Load DoD criteria
        criteria = load_dod_criteria()
        print(f"Loaded {len(criteria)} DoD categories:")
        for category in criteria:
            # Remove unicode characters for safer printing
            safe_category = category.replace('\u2713', '[OK]')
            print(f"  - {safe_category} ({len(criteria[category])} criteria)")

        # Run validation
        print("\n=== Running Automated Checks ===\n")
        validation = validate_task_completion(skip_tests=True)

        print(f"\n{validation}")
        print(f"\nCriteria met: {', '.join(validation.criteria_met)}")

        if validation.criteria_failed:
            print(f"\nCriteria failed: {', '.join(validation.criteria_failed)}")
            print("\nFailure details:")
            for criterion, details in validation.failure_details.items():
                print(f"  - {criterion}: {details}")

            print("\nSuggestions:")
            for suggestion in validation.suggestions:
                print(f"  - {suggestion}")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
