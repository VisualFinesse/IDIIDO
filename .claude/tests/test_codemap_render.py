"""
Tests for codemap_render module.

Tests the rendering functions for generating CODEMAP markdown output:
- render_header: Document header section
- render_quick_navigation: Quick navigation section
- render_stack_signals: Stack signals section
- render_entrypoints: Entrypoints section
- render_package_scripts: Package.json scripts section
- render_tree: Repository tree section
- render_snippets: Key file snippets section
- render_warnings: Warnings section
- render_codemap: Complete document assembly
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from codemap_render import (
    render_codemap,
    render_entrypoints,
    render_header,
    render_package_scripts,
    render_quick_navigation,
    render_snippets,
    render_stack_signals,
    render_tree,
    render_warnings,
)


class TestRenderHeader:
    """Tests for render_header function."""

    def test_includes_title_with_root_name(self, tmp_path: Path) -> None:
        """Test that header includes title with root directory name."""
        result = render_header(tmp_path, 1024)
        assert f"# CODEMAP — {tmp_path.name}" in result[0]

    def test_includes_generated_timestamp(self, tmp_path: Path) -> None:
        """Test that header includes generation timestamp."""
        result = render_header(tmp_path, 1024)
        timestamp_line = [line for line in result if "Generated:" in line][0]
        assert "Generated:" in timestamp_line
        assert "`" in timestamp_line  # Wrapped in backticks

    def test_includes_root_path(self, tmp_path: Path) -> None:
        """Test that header includes root path."""
        result = render_header(tmp_path, 1024)
        root_line = [line for line in result if "Root:" in line][0]
        assert "Root:" in root_line
        assert tmp_path.name in root_line

    def test_includes_total_size(self, tmp_path: Path) -> None:
        """Test that header includes total size."""
        result = render_header(tmp_path, 1024)
        size_line = [line for line in result if "Total size:" in line][0]
        assert "Total size:" in size_line
        assert "1.0 KB" in size_line

    def test_formats_large_sizes(self, tmp_path: Path) -> None:
        """Test that large sizes are formatted correctly."""
        result = render_header(tmp_path, 1024 * 1024 * 5)  # 5 MB
        size_line = [line for line in result if "Total size:" in line][0]
        assert "5.0 MB" in size_line

    def test_ends_with_blank_line(self, tmp_path: Path) -> None:
        """Test that header ends with blank line."""
        result = render_header(tmp_path, 1024)
        assert result[-1] == ""


class TestRenderQuickNavigation:
    """Tests for render_quick_navigation function."""

    def test_includes_section_header(self) -> None:
        """Test that section header is included."""
        result = render_quick_navigation(["README.md"])
        assert "## Quick navigation" in result

    def test_lists_important_files(self) -> None:
        """Test that important files are listed."""
        files = ["README.md", "package.json", "Dockerfile"]
        result = render_quick_navigation(files)
        for f in files:
            assert any(f"`{f}`" in line for line in result)

    def test_shows_none_found_when_empty(self) -> None:
        """Test that empty list shows none found."""
        result = render_quick_navigation([])
        assert any("(none found)" in line for line in result)

    def test_ends_with_blank_line(self) -> None:
        """Test that section ends with blank line."""
        result = render_quick_navigation(["README.md"])
        assert result[-1] == ""


class TestRenderStackSignals:
    """Tests for render_stack_signals function."""

    def test_includes_section_header(self) -> None:
        """Test that section header is included."""
        result = render_stack_signals({"Python": ["pyproject.toml"]})
        assert "## Stack signals" in result

    def test_lists_stacks_with_files(self) -> None:
        """Test that stacks are listed with their files."""
        stacks = {
            "Python": ["pyproject.toml", "requirements.txt"],
            "Node.js": ["package.json"],
        }
        result = render_stack_signals(stacks)
        assert any("**Python**" in line for line in result)
        assert any("**Node.js**" in line for line in result)
        assert any("`pyproject.toml`" in line for line in result)
        assert any("`package.json`" in line for line in result)

    def test_stacks_sorted_alphabetically(self) -> None:
        """Test that stacks are sorted alphabetically."""
        stacks = {"Rust": ["Cargo.toml"], "Go": ["go.mod"], "Python": ["setup.py"]}
        result = render_stack_signals(stacks)
        stack_lines = [line for line in result if "**" in line and line.startswith("-")]
        assert "**Go**" in stack_lines[0]
        assert "**Python**" in stack_lines[1]
        assert "**Rust**" in stack_lines[2]

    def test_truncates_at_12_files(self) -> None:
        """Test that file list is truncated at 12 entries."""
        files = [f"file{i}.py" for i in range(20)]
        stacks = {"Python": files}
        result = render_stack_signals(stacks)
        # Should have 12 file entries plus "more" indicator
        file_lines = [line for line in result if line.startswith("  - `")]
        assert len(file_lines) == 12
        assert any("+8 more" in line for line in result)

    def test_shows_no_signals_when_empty(self) -> None:
        """Test that empty dict shows no signals detected."""
        result = render_stack_signals({})
        assert any("(no strong signals detected)" in line for line in result)

    def test_ends_with_blank_line(self) -> None:
        """Test that section ends with blank line."""
        result = render_stack_signals({"Python": ["setup.py"]})
        assert result[-1] == ""


class TestRenderEntrypoints:
    """Tests for render_entrypoints function."""

    def test_includes_section_header(self) -> None:
        """Test that section header is included."""
        result = render_entrypoints(["main.py"])
        assert "## Entrypoints (heuristic)" in result

    def test_lists_entrypoints(self) -> None:
        """Test that entrypoints are listed."""
        entrypoints = ["main.py", "src/index.ts", "__main__.py"]
        result = render_entrypoints(entrypoints)
        for ep in entrypoints:
            assert any(f"`{ep}`" in line for line in result)

    def test_shows_none_detected_when_empty(self) -> None:
        """Test that empty list shows none detected."""
        result = render_entrypoints([])
        assert any("(none detected)" in line for line in result)

    def test_ends_with_blank_line(self) -> None:
        """Test that section ends with blank line."""
        result = render_entrypoints(["main.py"])
        assert result[-1] == ""


class TestRenderPackageScripts:
    """Tests for render_package_scripts function."""

    def test_includes_section_header_when_present(self) -> None:
        """Test that section header is included when scripts exist."""
        scripts = ["- `package.json`", "  - `build`: webpack"]
        result = render_package_scripts(scripts)
        assert "## package.json scripts (if present)" in result

    def test_includes_scripts(self) -> None:
        """Test that scripts are included."""
        scripts = ["- `package.json`", "  - `build`: webpack", "  - `test`: jest"]
        result = render_package_scripts(scripts)
        for script in scripts:
            assert script in result

    def test_returns_empty_when_no_scripts(self) -> None:
        """Test that empty list returns empty result."""
        result = render_package_scripts([])
        assert result == []

    def test_ends_with_blank_line_when_present(self) -> None:
        """Test that section ends with blank line when scripts exist."""
        scripts = ["- `package.json`", "  - `build`: webpack"]
        result = render_package_scripts(scripts)
        assert result[-1] == ""


class TestRenderTree:
    """Tests for render_tree function."""

    def test_includes_section_header(self, tmp_path: Path) -> None:
        """Test that section header is included."""
        result = render_tree(tmp_path, "├── src/")
        assert "## Repository tree" in result

    def test_includes_root_name(self, tmp_path: Path) -> None:
        """Test that root directory name is included."""
        result = render_tree(tmp_path, "├── src/")
        assert any(f"{tmp_path.name}/" in line for line in result)

    def test_wraps_tree_in_code_block(self, tmp_path: Path) -> None:
        """Test that tree is wrapped in code block."""
        result = render_tree(tmp_path, "├── src/")
        assert "```" in result
        # Should have opening and closing code blocks
        assert result.count("```") == 2

    def test_shows_empty_when_tree_is_whitespace(self, tmp_path: Path) -> None:
        """Test that whitespace-only tree shows (empty)."""
        result = render_tree(tmp_path, "   \n  ")
        assert any("(empty)" in line for line in result)

    def test_ends_with_blank_line(self, tmp_path: Path) -> None:
        """Test that section ends with blank line."""
        result = render_tree(tmp_path, "├── src/")
        assert result[-1] == ""


class TestRenderSnippets:
    """Tests for render_snippets function."""

    def test_includes_section_header_when_present(self) -> None:
        """Test that section header is included when snippets exist."""
        snippets = [("README.md", "# Hello World")]
        result = render_snippets(snippets)
        assert "## Key file snippets (first lines)" in result

    def test_includes_file_headers(self) -> None:
        """Test that file headers are included."""
        snippets = [("README.md", "# Hello"), ("main.py", "print('hi')")]
        result = render_snippets(snippets)
        assert any("### `README.md`" in line for line in result)
        assert any("### `main.py`" in line for line in result)

    def test_includes_snippet_content(self) -> None:
        """Test that snippet content is included."""
        snippets = [("README.md", "# Hello World\n\nThis is a test.")]
        result = render_snippets(snippets)
        assert any("# Hello World" in line for line in result)

    def test_wraps_snippets_in_code_blocks(self) -> None:
        """Test that snippets are wrapped in code blocks."""
        snippets = [("main.py", "print('hello')")]
        result = render_snippets(snippets)
        assert result.count("```") == 2

    def test_returns_empty_when_no_snippets(self) -> None:
        """Test that empty list returns empty result."""
        result = render_snippets([])
        assert result == []


class TestRenderWarnings:
    """Tests for render_warnings function."""

    def test_includes_section_header_when_present(self) -> None:
        """Test that section header is included when warnings exist."""
        warnings = ["Warning: file too large"]
        result = render_warnings(warnings)
        assert "## Warnings" in result

    def test_lists_warnings(self) -> None:
        """Test that warnings are listed."""
        warnings = ["Warning 1", "Warning 2", "Warning 3"]
        result = render_warnings(warnings)
        for w in warnings:
            assert any(w in line for line in result)

    def test_truncates_at_50_warnings(self) -> None:
        """Test that warnings are truncated at 50 entries."""
        warnings = [f"Warning {i}" for i in range(100)]
        result = render_warnings(warnings)
        warning_lines = [line for line in result if line.startswith("- ") and "more" not in line]
        assert len(warning_lines) == 50
        assert any("+50 more" in line for line in result)

    def test_returns_empty_when_no_warnings(self) -> None:
        """Test that empty list returns empty result."""
        result = render_warnings([])
        assert result == []

    def test_ends_with_blank_line_when_present(self) -> None:
        """Test that section ends with blank line when warnings exist."""
        warnings = ["Warning: something happened"]
        result = render_warnings(warnings)
        assert result[-1] == ""


class TestRenderCodemap:
    """Tests for render_codemap function."""

    def test_assembles_all_sections(self, tmp_path: Path) -> None:
        """Test that all sections are assembled."""
        with patch("codemap_render.utc_now_iso", return_value="2026-01-24T12:00:00Z"):
            result = render_codemap(
                root=tmp_path,
                total_bytes=1024,
                important=["README.md"],
                stacks={"Python": ["setup.py"]},
                entrypoints=["main.py"],
                pkg_scripts=["- `package.json`"],
                tree="├── src/",
            )

        assert f"# CODEMAP — {tmp_path.name}" in result
        assert "## Quick navigation" in result
        assert "## Stack signals" in result
        assert "## Entrypoints (heuristic)" in result
        assert "## package.json scripts (if present)" in result
        assert "## Repository tree" in result

    def test_includes_optional_snippets(self, tmp_path: Path) -> None:
        """Test that optional snippets are included when provided."""
        with patch("codemap_render.utc_now_iso", return_value="2026-01-24T12:00:00Z"):
            result = render_codemap(
                root=tmp_path,
                total_bytes=1024,
                important=[],
                stacks={},
                entrypoints=[],
                pkg_scripts=[],
                tree="",
                snippets=[("README.md", "# Hello")],
            )

        assert "## Key file snippets (first lines)" in result

    def test_includes_optional_warnings(self, tmp_path: Path) -> None:
        """Test that optional warnings are included when provided."""
        with patch("codemap_render.utc_now_iso", return_value="2026-01-24T12:00:00Z"):
            result = render_codemap(
                root=tmp_path,
                total_bytes=1024,
                important=[],
                stacks={},
                entrypoints=[],
                pkg_scripts=[],
                tree="",
                warnings=["File too large"],
            )

        assert "## Warnings" in result
        assert "File too large" in result

    def test_excludes_snippets_when_none(self, tmp_path: Path) -> None:
        """Test that snippets section is excluded when None."""
        with patch("codemap_render.utc_now_iso", return_value="2026-01-24T12:00:00Z"):
            result = render_codemap(
                root=tmp_path,
                total_bytes=1024,
                important=[],
                stacks={},
                entrypoints=[],
                pkg_scripts=[],
                tree="",
                snippets=None,
            )

        assert "## Key file snippets" not in result

    def test_excludes_warnings_when_none(self, tmp_path: Path) -> None:
        """Test that warnings section is excluded when None."""
        with patch("codemap_render.utc_now_iso", return_value="2026-01-24T12:00:00Z"):
            result = render_codemap(
                root=tmp_path,
                total_bytes=1024,
                important=[],
                stacks={},
                entrypoints=[],
                pkg_scripts=[],
                tree="",
                warnings=None,
            )

        assert "## Warnings" not in result

    def test_ends_with_single_newline(self, tmp_path: Path) -> None:
        """Test that result ends with exactly one newline."""
        with patch("codemap_render.utc_now_iso", return_value="2026-01-24T12:00:00Z"):
            result = render_codemap(
                root=tmp_path,
                total_bytes=1024,
                important=[],
                stacks={},
                entrypoints=[],
                pkg_scripts=[],
                tree="",
            )

        assert result.endswith("\n")
        assert not result.endswith("\n\n")

    def test_returns_string(self, tmp_path: Path) -> None:
        """Test that result is a string."""
        with patch("codemap_render.utc_now_iso", return_value="2026-01-24T12:00:00Z"):
            result = render_codemap(
                root=tmp_path,
                total_bytes=1024,
                important=[],
                stacks={},
                entrypoints=[],
                pkg_scripts=[],
                tree="",
            )

        assert isinstance(result, str)


class TestIntegration:
    """Integration tests for render module."""

    def test_full_render_workflow(self, tmp_path: Path) -> None:
        """Test complete rendering workflow with realistic data."""
        with patch("codemap_render.utc_now_iso", return_value="2026-01-24T12:00:00Z"):
            result = render_codemap(
                root=tmp_path,
                total_bytes=1024 * 1024 * 10,  # 10 MB
                important=["README.md", "package.json", "Dockerfile"],
                stacks={
                    "Python": ["pyproject.toml", "requirements.txt"],
                    "Node.js": ["package.json"],
                    "Docker": ["Dockerfile", "docker-compose.yml"],
                },
                entrypoints=["main.py", "src/index.ts"],
                pkg_scripts=[
                    "- `package.json`",
                    "  - `build`: webpack --mode production",
                    "  - `test`: jest --coverage",
                ],
                tree="├── src/\n│   ├── main.py\n│   └── index.ts\n└── tests/",
                snippets=[("README.md", "# My Project\n\nA great project.")],
                warnings=["Large file skipped: data.bin (500 MB)"],
            )

        # Verify all major sections are present
        assert "# CODEMAP" in result
        assert "## Quick navigation" in result
        assert "## Stack signals" in result
        assert "## Entrypoints (heuristic)" in result
        assert "## package.json scripts" in result
        assert "## Repository tree" in result
        assert "## Key file snippets" in result
        assert "## Warnings" in result

        # Verify content is correct
        assert "README.md" in result
        assert "**Python**" in result
        assert "main.py" in result
        assert "webpack" in result
        assert "My Project" in result
        assert "Large file skipped" in result
        assert "10.0 MB" in result
