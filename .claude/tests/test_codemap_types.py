"""
Tests for codemap_types module.

Tests the core data structures:
- IgnoreRules: Pattern matching for file/directory exclusion
- FileRecord: File metadata dataclass

Note: rel_posix tests have been moved to test_codemap_fs.py since
the function now lives in codemap_fs.py.
"""

import sys
from pathlib import Path

import pytest

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from codemap_fs import rel_posix
from codemap_types import FileRecord, IgnoreRules


class TestRelPosix:
    """Tests for rel_posix function."""

    def test_rel_posix_basic(self, tmp_path: Path) -> None:
        """Test basic relative path conversion."""
        subdir = tmp_path / "subdir" / "file.txt"
        result = rel_posix(tmp_path, subdir)
        assert result == "subdir/file.txt"

    def test_rel_posix_same_directory(self, tmp_path: Path) -> None:
        """Test file in same directory."""
        file_path = tmp_path / "file.txt"
        result = rel_posix(tmp_path, file_path)
        assert result == "file.txt"

    def test_rel_posix_deep_nesting(self, tmp_path: Path) -> None:
        """Test deeply nested path."""
        deep_path = tmp_path / "a" / "b" / "c" / "d" / "file.txt"
        result = rel_posix(tmp_path, deep_path)
        assert result == "a/b/c/d/file.txt"

    def test_rel_posix_uses_forward_slashes(self, tmp_path: Path) -> None:
        """Ensure result uses forward slashes (POSIX style)."""
        nested = tmp_path / "dir1" / "dir2" / "file.py"
        result = rel_posix(tmp_path, nested)
        assert "\\" not in result
        assert "/" in result


class TestIgnoreRulesMatches:
    """Tests for IgnoreRules.matches method."""

    def test_matches_dir_by_name(self, tmp_path: Path) -> None:
        """Test directory matching by exact name."""
        rules = IgnoreRules(
            dir_names={"node_modules", ".git"},
            file_globs=set(),
            gitignore_like_patterns=[],
        )
        node_modules = tmp_path / "node_modules"
        assert rules.matches(tmp_path, node_modules, is_dir=True) is True

    def test_does_not_match_file_with_dir_name(self, tmp_path: Path) -> None:
        """Directory name patterns should not match files."""
        rules = IgnoreRules(
            dir_names={"node_modules"},
            file_globs=set(),
            gitignore_like_patterns=[],
        )
        file_path = tmp_path / "node_modules"
        # File with same name as dir pattern should not match if is_dir=False
        assert rules.matches(tmp_path, file_path, is_dir=False) is False

    def test_matches_file_by_glob(self, tmp_path: Path) -> None:
        """Test file matching by glob pattern."""
        rules = IgnoreRules(
            dir_names=set(),
            file_globs={"*.pyc", "*.log"},
            gitignore_like_patterns=[],
        )
        pyc_file = tmp_path / "module.pyc"
        log_file = tmp_path / "debug.log"
        py_file = tmp_path / "main.py"

        assert rules.matches(tmp_path, pyc_file, is_dir=False) is True
        assert rules.matches(tmp_path, log_file, is_dir=False) is True
        assert rules.matches(tmp_path, py_file, is_dir=False) is False

    def test_matches_nested_file_by_glob(self, tmp_path: Path) -> None:
        """Test glob matching on nested file paths."""
        rules = IgnoreRules(
            dir_names=set(),
            file_globs={"*.pyc"},
            gitignore_like_patterns=[],
        )
        nested_pyc = tmp_path / "src" / "module.pyc"
        assert rules.matches(tmp_path, nested_pyc, is_dir=False) is True

    def test_no_match_when_no_rules(self, tmp_path: Path) -> None:
        """Test that nothing matches when no rules defined."""
        rules = IgnoreRules(
            dir_names=set(),
            file_globs=set(),
            gitignore_like_patterns=[],
        )
        any_file = tmp_path / "anything.txt"
        any_dir = tmp_path / "anydir"
        assert rules.matches(tmp_path, any_file, is_dir=False) is False
        assert rules.matches(tmp_path, any_dir, is_dir=True) is False


class TestIgnoreRulesGitignoreStyle:
    """Tests for IgnoreRules._match_gitignore_style method."""

    def test_comment_pattern_no_match(self) -> None:
        """Comments should not match."""
        assert IgnoreRules._match_gitignore_style("file.py", "file.py", "# comment", False) is False

    def test_empty_pattern_no_match(self) -> None:
        """Empty patterns should not match."""
        assert IgnoreRules._match_gitignore_style("file.py", "file.py", "", False) is False
        assert IgnoreRules._match_gitignore_style("file.py", "file.py", "   ", False) is False

    def test_simple_pattern_matches(self) -> None:
        """Simple pattern matches filename."""
        assert IgnoreRules._match_gitignore_style("file.py", "file.py", "file.py", False) is True
        assert IgnoreRules._match_gitignore_style("other.py", "other.py", "file.py", False) is False

    def test_wildcard_pattern(self) -> None:
        """Single * matches within path component."""
        assert IgnoreRules._match_gitignore_style("test.log", "test.log", "*.log", False) is True
        assert IgnoreRules._match_gitignore_style("test.txt", "test.txt", "*.log", False) is False

    def test_double_wildcard_pattern(self) -> None:
        """Double ** matches across path components."""
        assert IgnoreRules._match_gitignore_style("src/foo/bar.py", "bar.py", "**/bar.py", False) is True
        assert IgnoreRules._match_gitignore_style("deep/nested/bar.py", "bar.py", "**/bar.py", False) is True

    def test_anchored_pattern(self) -> None:
        """Patterns starting with / are anchored to root."""
        # Anchored pattern should match at root only
        assert IgnoreRules._match_gitignore_style("file.py", "file.py", "/file.py", False) is True
        # Anchored pattern should not match nested files (unless the pattern matches full path)
        assert IgnoreRules._match_gitignore_style("src/file.py", "file.py", "/file.py", False) is False

    def test_dir_only_pattern(self) -> None:
        """Patterns ending with / only match directories."""
        # Dir-only pattern should not match files
        assert IgnoreRules._match_gitignore_style("build", "build", "build/", False) is False
        # Dir-only pattern should match directories
        assert IgnoreRules._match_gitignore_style("build", "build", "build/", True) is True

    def test_question_mark_wildcard(self) -> None:
        """? matches single character."""
        assert IgnoreRules._match_gitignore_style("file1.py", "file1.py", "file?.py", False) is True
        assert IgnoreRules._match_gitignore_style("fileAB.py", "fileAB.py", "file?.py", False) is False

    def test_negation_pattern_stripped(self) -> None:
        """Negation patterns (!) have the ! stripped for matching."""
        # The ! is stripped, so "!file.py" becomes "file.py"
        assert IgnoreRules._match_gitignore_style("file.py", "file.py", "!file.py", False) is True


class TestFileRecord:
    """Tests for FileRecord dataclass."""

    def test_file_record_creation(self) -> None:
        """Test basic FileRecord creation."""
        record = FileRecord(
            rel="src/main.py",
            size=1024,
            mtime_iso="2026-01-24T12:00:00Z",
            is_dir=False,
        )
        assert record.rel == "src/main.py"
        assert record.size == 1024
        assert record.mtime_iso == "2026-01-24T12:00:00Z"
        assert record.is_dir is False
        assert record.sha256 is None

    def test_file_record_with_hash(self) -> None:
        """Test FileRecord with SHA-256 hash."""
        record = FileRecord(
            rel="config.json",
            size=256,
            mtime_iso="2026-01-24T10:30:00Z",
            is_dir=False,
            sha256="abc123def456",
        )
        assert record.sha256 == "abc123def456"

    def test_file_record_directory(self) -> None:
        """Test FileRecord representing a directory."""
        record = FileRecord(
            rel="src/components",
            size=0,
            mtime_iso="2026-01-24T09:00:00Z",
            is_dir=True,
        )
        assert record.is_dir is True

    def test_file_record_equality(self) -> None:
        """Test FileRecord equality (dataclass default)."""
        record1 = FileRecord(
            rel="file.py",
            size=100,
            mtime_iso="2026-01-24T00:00:00Z",
            is_dir=False,
        )
        record2 = FileRecord(
            rel="file.py",
            size=100,
            mtime_iso="2026-01-24T00:00:00Z",
            is_dir=False,
        )
        assert record1 == record2

    def test_file_record_different_hash(self) -> None:
        """Test FileRecords with different hashes are not equal."""
        record1 = FileRecord(
            rel="file.py",
            size=100,
            mtime_iso="2026-01-24T00:00:00Z",
            is_dir=False,
            sha256="hash1",
        )
        record2 = FileRecord(
            rel="file.py",
            size=100,
            mtime_iso="2026-01-24T00:00:00Z",
            is_dir=False,
            sha256="hash2",
        )
        assert record1 != record2


class TestIgnoreRulesIntegration:
    """Integration tests for IgnoreRules with real file system."""

    def test_full_matching_workflow(self, tmp_path: Path) -> None:
        """Test complete matching workflow with multiple rule types."""
        rules = IgnoreRules(
            dir_names={"node_modules", "__pycache__"},
            file_globs={"*.pyc", "*.log", ".DS_Store"},
            gitignore_like_patterns=["*.egg-info/", "build/", "**/test_*.py"],
        )

        # Create test structure
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").touch()
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "app.pyc").touch()
        (tmp_path / "debug.log").touch()

        # Test directory exclusions
        assert rules.matches(tmp_path, tmp_path / "node_modules", is_dir=True) is True
        assert rules.matches(tmp_path, tmp_path / "__pycache__", is_dir=True) is True
        assert rules.matches(tmp_path, tmp_path / "src", is_dir=True) is False

        # Test file glob exclusions
        assert rules.matches(tmp_path, tmp_path / "app.pyc", is_dir=False) is True
        assert rules.matches(tmp_path, tmp_path / "debug.log", is_dir=False) is True
        assert rules.matches(tmp_path, tmp_path / "src" / "main.py", is_dir=False) is False

    def test_gitignore_pattern_priority(self, tmp_path: Path) -> None:
        """Test that gitignore patterns work alongside other rules."""
        rules = IgnoreRules(
            dir_names=set(),
            file_globs=set(),
            gitignore_like_patterns=["*.min.js", "dist/"],
        )

        min_js = tmp_path / "app.min.js"
        dist_dir = tmp_path / "dist"

        assert rules.matches(tmp_path, min_js, is_dir=False) is True
        assert rules.matches(tmp_path, dist_dir, is_dir=True) is True
