"""
Tests for codemap_ignore module.

Tests the ignore pattern loading and building functions:
- load_patterns_file: Load patterns from .gitignore/.codemapignore files
- build_ignore_rules: Build IgnoreRules from patterns and defaults
"""

import sys
from pathlib import Path

import pytest

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from codemap_ignore import build_ignore_rules, load_patterns_file
from codemap_types import IgnoreRules


class TestLoadPatternsFile:
    """Tests for load_patterns_file function."""

    def test_load_patterns_basic(self, tmp_path: Path) -> None:
        """Test loading basic patterns from a file."""
        ignore_file = tmp_path / ".gitignore"
        ignore_file.write_text("node_modules\n*.pyc\nbuild/\n", encoding="utf-8")

        patterns = load_patterns_file(ignore_file)

        assert "node_modules" in patterns
        assert "*.pyc" in patterns
        assert "build/" in patterns
        assert len(patterns) == 3

    def test_load_patterns_strips_whitespace(self, tmp_path: Path) -> None:
        """Test that patterns are stripped of leading/trailing whitespace."""
        ignore_file = tmp_path / ".gitignore"
        ignore_file.write_text("  node_modules  \n  *.log\t\n", encoding="utf-8")

        patterns = load_patterns_file(ignore_file)

        assert "node_modules" in patterns
        assert "*.log" in patterns
        # Should not contain whitespace-padded versions
        assert "  node_modules  " not in patterns

    def test_load_patterns_skips_comments(self, tmp_path: Path) -> None:
        """Test that comment lines are skipped."""
        ignore_file = tmp_path / ".gitignore"
        ignore_file.write_text(
            "# This is a comment\nnode_modules\n# Another comment\n*.pyc\n",
            encoding="utf-8",
        )

        patterns = load_patterns_file(ignore_file)

        assert "# This is a comment" not in patterns
        assert "# Another comment" not in patterns
        assert "node_modules" in patterns
        assert "*.pyc" in patterns
        assert len(patterns) == 2

    def test_load_patterns_skips_empty_lines(self, tmp_path: Path) -> None:
        """Test that empty lines are skipped."""
        ignore_file = tmp_path / ".gitignore"
        ignore_file.write_text(
            "node_modules\n\n\n*.pyc\n   \n\nbuild/\n",
            encoding="utf-8",
        )

        patterns = load_patterns_file(ignore_file)

        assert len(patterns) == 3
        assert "" not in patterns

    def test_load_patterns_nonexistent_file(self, tmp_path: Path) -> None:
        """Test loading from a nonexistent file returns empty list."""
        nonexistent = tmp_path / "does_not_exist"

        patterns = load_patterns_file(nonexistent)

        assert patterns == []

    def test_load_patterns_empty_file(self, tmp_path: Path) -> None:
        """Test loading from an empty file returns empty list."""
        empty_file = tmp_path / ".gitignore"
        empty_file.write_text("", encoding="utf-8")

        patterns = load_patterns_file(empty_file)

        assert patterns == []

    def test_load_patterns_only_comments(self, tmp_path: Path) -> None:
        """Test loading from file with only comments returns empty list."""
        comments_only = tmp_path / ".gitignore"
        comments_only.write_text("# comment 1\n# comment 2\n", encoding="utf-8")

        patterns = load_patterns_file(comments_only)

        assert patterns == []

    def test_load_patterns_complex_patterns(self, tmp_path: Path) -> None:
        """Test loading complex gitignore-style patterns."""
        ignore_file = tmp_path / ".gitignore"
        ignore_file.write_text(
            "**/build/\n"
            "!important.txt\n"
            "/root_only.txt\n"
            "*.egg-info/\n"
            "coverage/**\n",
            encoding="utf-8",
        )

        patterns = load_patterns_file(ignore_file)

        assert "**/build/" in patterns
        assert "!important.txt" in patterns
        assert "/root_only.txt" in patterns
        assert "*.egg-info/" in patterns
        assert "coverage/**" in patterns

    def test_load_patterns_handles_encoding_errors(self, tmp_path: Path) -> None:
        """Test that encoding errors are handled gracefully."""
        ignore_file = tmp_path / ".gitignore"
        # Write bytes that are invalid UTF-8
        ignore_file.write_bytes(b"node_modules\n\xff\xfe*.pyc\n")

        patterns = load_patterns_file(ignore_file)

        # Should still load valid patterns
        assert "node_modules" in patterns


class TestBuildIgnoreRules:
    """Tests for build_ignore_rules function."""

    def test_build_ignore_rules_with_gitignore(self, tmp_path: Path) -> None:
        """Test building rules including .gitignore patterns."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("custom_ignore/\n*.custom\n", encoding="utf-8")

        rules = build_ignore_rules(tmp_path, include_gitignore=True)

        assert isinstance(rules, IgnoreRules)
        # Should include patterns from .gitignore
        assert "custom_ignore/" in rules.gitignore_like_patterns
        assert "*.custom" in rules.gitignore_like_patterns

    def test_build_ignore_rules_without_gitignore(self, tmp_path: Path) -> None:
        """Test building rules without .gitignore patterns."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("custom_ignore/\n", encoding="utf-8")

        rules = build_ignore_rules(tmp_path, include_gitignore=False)

        assert isinstance(rules, IgnoreRules)
        # Should NOT include patterns from .gitignore
        assert "custom_ignore/" not in rules.gitignore_like_patterns

    def test_build_ignore_rules_with_codemapignore(self, tmp_path: Path) -> None:
        """Test building rules with .codemapignore patterns."""
        codemapignore = tmp_path / ".codemapignore"
        codemapignore.write_text("special_dir/\n*.special\n", encoding="utf-8")

        rules = build_ignore_rules(tmp_path, include_gitignore=False)

        # Should include patterns from .codemapignore
        assert "special_dir/" in rules.gitignore_like_patterns
        assert "*.special" in rules.gitignore_like_patterns

    def test_build_ignore_rules_includes_default_dirs(self, tmp_path: Path) -> None:
        """Test that default directory excludes are included."""
        rules = build_ignore_rules(tmp_path, include_gitignore=False)

        # Should include common default excludes
        assert "node_modules" in rules.dir_names
        assert ".git" in rules.dir_names

    def test_build_ignore_rules_includes_default_globs(self, tmp_path: Path) -> None:
        """Test that default file glob excludes are included."""
        rules = build_ignore_rules(tmp_path, include_gitignore=False)

        # Should include common default file patterns
        assert "*.pyc" in rules.file_globs

    def test_build_ignore_rules_no_ignore_files(self, tmp_path: Path) -> None:
        """Test building rules when no ignore files exist."""
        rules = build_ignore_rules(tmp_path, include_gitignore=True)

        assert isinstance(rules, IgnoreRules)
        # Should still have default excludes
        assert len(rules.dir_names) > 0
        assert len(rules.file_globs) > 0

    def test_build_ignore_rules_combines_sources(self, tmp_path: Path) -> None:
        """Test that patterns from all sources are combined."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("from_git/\n", encoding="utf-8")

        codemapignore = tmp_path / ".codemapignore"
        codemapignore.write_text("from_codemap/\n", encoding="utf-8")

        rules = build_ignore_rules(tmp_path, include_gitignore=True)

        # Should include patterns from both files
        assert "from_git/" in rules.gitignore_like_patterns
        assert "from_codemap/" in rules.gitignore_like_patterns


class TestBuildIgnoreRulesIntegration:
    """Integration tests for build_ignore_rules with file matching."""

    def test_built_rules_match_files(self, tmp_path: Path) -> None:
        """Test that built rules correctly match files."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.log\nbuild/\n", encoding="utf-8")

        rules = build_ignore_rules(tmp_path, include_gitignore=True)

        # Create test files
        log_file = tmp_path / "debug.log"
        build_dir = tmp_path / "build"
        src_file = tmp_path / "main.py"

        # Test matching
        assert rules.matches(tmp_path, log_file, is_dir=False) is True
        assert rules.matches(tmp_path, build_dir, is_dir=True) is True
        assert rules.matches(tmp_path, src_file, is_dir=False) is False

    def test_built_rules_match_default_excludes(self, tmp_path: Path) -> None:
        """Test that built rules match default excludes."""
        rules = build_ignore_rules(tmp_path, include_gitignore=False)

        node_modules = tmp_path / "node_modules"
        git_dir = tmp_path / ".git"
        pyc_file = tmp_path / "module.pyc"

        assert rules.matches(tmp_path, node_modules, is_dir=True) is True
        assert rules.matches(tmp_path, git_dir, is_dir=True) is True
        assert rules.matches(tmp_path, pyc_file, is_dir=False) is True
