"""
Tests for codemap_detect module.

Tests the detection and collection functions:
- is_match_any: Pattern matching for paths
- collect_important_files: High-signal file collection
- collect_entrypoints: Entry point detection
- detect_stack_signals: Technology stack detection
- extract_package_json_scripts: npm scripts extraction
"""

import json
import sys
from pathlib import Path

import pytest

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from codemap_detect import (
    collect_entrypoints,
    collect_important_files,
    detect_stack_signals,
    extract_package_json_scripts,
    is_match_any,
)
from codemap_types import FileRecord


class TestIsMatchAny:
    """Tests for is_match_any function."""

    def test_matches_exact_filename(self) -> None:
        """Test matching exact filename."""
        assert is_match_any("README.md", ["README.md"]) is True
        assert is_match_any("src/README.md", ["README.md"]) is True

    def test_matches_glob_pattern(self) -> None:
        """Test matching glob patterns."""
        assert is_match_any("main.py", ["*.py"]) is True
        assert is_match_any("src/main.py", ["*.py"]) is True
        assert is_match_any("main.js", ["*.py"]) is False

    def test_matches_path_glob(self) -> None:
        """Test matching path-based glob patterns."""
        assert is_match_any("src/main.py", ["src/*.py"]) is True
        assert is_match_any("lib/main.py", ["src/*.py"]) is False

    def test_matches_double_star_glob(self) -> None:
        """Test matching ** glob patterns."""
        assert is_match_any(".github/workflows/ci.yml", [".github/workflows/*.yml"]) is True
        assert is_match_any(".github/workflows/deploy.yaml", [".github/workflows/*.yaml"]) is True

    def test_no_match_returns_false(self) -> None:
        """Test that non-matching paths return False."""
        assert is_match_any("main.rs", ["*.py", "*.js"]) is False

    def test_empty_patterns_returns_false(self) -> None:
        """Test that empty pattern list returns False."""
        assert is_match_any("anything.txt", []) is False

    def test_matches_any_of_multiple_patterns(self) -> None:
        """Test matching against multiple patterns."""
        patterns = ["README.md", "LICENSE", "*.toml"]
        assert is_match_any("README.md", patterns) is True
        assert is_match_any("LICENSE", patterns) is True
        assert is_match_any("pyproject.toml", patterns) is True
        assert is_match_any("main.py", patterns) is False


class TestCollectImportantFiles:
    """Tests for collect_important_files function."""

    def test_collects_readme(self, tmp_path: Path) -> None:
        """Test that README files are collected."""
        files = [
            FileRecord(rel="README.md", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
            FileRecord(rel="src/main.py", size=200, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
        ]
        result = collect_important_files(tmp_path, files)
        assert "README.md" in result

    def test_collects_package_manifests(self, tmp_path: Path) -> None:
        """Test that package manifest files are collected."""
        files = [
            FileRecord(rel="package.json", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
            FileRecord(rel="pyproject.toml", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
            FileRecord(rel="Cargo.toml", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
        ]
        result = collect_important_files(tmp_path, files)
        assert "package.json" in result
        assert "pyproject.toml" in result
        assert "Cargo.toml" in result

    def test_collects_ci_files(self, tmp_path: Path) -> None:
        """Test that CI/CD configuration files are collected."""
        files = [
            FileRecord(rel=".github/workflows/ci.yml", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
            FileRecord(rel=".gitlab-ci.yml", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
        ]
        result = collect_important_files(tmp_path, files)
        assert ".github/workflows/ci.yml" in result
        assert ".gitlab-ci.yml" in result

    def test_returns_sorted_unique(self, tmp_path: Path) -> None:
        """Test that results are sorted and unique."""
        files = [
            FileRecord(rel="package.json", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
            FileRecord(rel="README.md", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
            FileRecord(rel="LICENSE", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
        ]
        result = collect_important_files(tmp_path, files)
        assert result == sorted(result)

    def test_empty_files_returns_empty(self, tmp_path: Path) -> None:
        """Test that empty file list returns empty result."""
        result = collect_important_files(tmp_path, [])
        assert result == []

    def test_no_matches_returns_empty(self, tmp_path: Path) -> None:
        """Test that files not matching patterns returns empty result."""
        files = [
            FileRecord(rel="random.txt", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
            FileRecord(rel="unknown.xyz", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
        ]
        result = collect_important_files(tmp_path, files)
        assert result == []


class TestCollectEntrypoints:
    """Tests for collect_entrypoints function."""

    def test_collects_main_py(self, tmp_path: Path) -> None:
        """Test that main.py is detected as entry point."""
        files = [
            FileRecord(rel="main.py", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
        ]
        result = collect_entrypoints(tmp_path, files)
        assert "main.py" in result

    def test_collects_index_js(self, tmp_path: Path) -> None:
        """Test that index.js is detected as entry point."""
        files = [
            FileRecord(rel="index.js", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
            FileRecord(rel="src/index.ts", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
        ]
        result = collect_entrypoints(tmp_path, files)
        assert "index.js" in result
        assert "src/index.ts" in result

    def test_collects_dunder_main(self, tmp_path: Path) -> None:
        """Test that __main__.py is detected as entry point."""
        files = [
            FileRecord(rel="mypackage/__main__.py", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
        ]
        result = collect_entrypoints(tmp_path, files)
        assert "mypackage/__main__.py" in result

    def test_sorted_by_depth(self, tmp_path: Path) -> None:
        """Test that results are sorted by depth (shallower first)."""
        files = [
            FileRecord(rel="deep/nested/main.py", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
            FileRecord(rel="main.py", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
            FileRecord(rel="src/main.py", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
        ]
        result = collect_entrypoints(tmp_path, files)
        assert result[0] == "main.py"
        assert result[1] == "src/main.py"
        assert result[2] == "deep/nested/main.py"

    def test_limited_to_50(self, tmp_path: Path) -> None:
        """Test that results are limited to 50 entries."""
        files = [
            FileRecord(rel=f"pkg{i}/main.py", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False)
            for i in range(100)
        ]
        result = collect_entrypoints(tmp_path, files)
        assert len(result) == 50

    def test_empty_files_returns_empty(self, tmp_path: Path) -> None:
        """Test that empty file list returns empty result."""
        result = collect_entrypoints(tmp_path, [])
        assert result == []


class TestDetectStackSignals:
    """Tests for detect_stack_signals function."""

    def test_detects_python(self, tmp_path: Path) -> None:
        """Test Python stack detection."""
        files = [
            FileRecord(rel="pyproject.toml", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
            FileRecord(rel="requirements.txt", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
        ]
        result = detect_stack_signals(tmp_path, files)
        assert "Python" in result
        assert "pyproject.toml" in result["Python"]
        assert "requirements.txt" in result["Python"]

    def test_detects_nodejs(self, tmp_path: Path) -> None:
        """Test Node.js stack detection."""
        files = [
            FileRecord(rel="package.json", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
            FileRecord(rel="package-lock.json", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
        ]
        result = detect_stack_signals(tmp_path, files)
        assert "Node.js" in result
        assert "package.json" in result["Node.js"]

    def test_detects_rust(self, tmp_path: Path) -> None:
        """Test Rust stack detection."""
        files = [
            FileRecord(rel="Cargo.toml", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
        ]
        result = detect_stack_signals(tmp_path, files)
        assert "Rust" in result

    def test_detects_docker(self, tmp_path: Path) -> None:
        """Test Docker stack detection."""
        files = [
            FileRecord(rel="Dockerfile", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
            FileRecord(rel="docker-compose.yml", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
        ]
        result = detect_stack_signals(tmp_path, files)
        assert "Docker" in result

    def test_detects_multiple_stacks(self, tmp_path: Path) -> None:
        """Test detection of multiple stacks."""
        files = [
            FileRecord(rel="package.json", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
            FileRecord(rel="pyproject.toml", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
            FileRecord(rel="Dockerfile", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
        ]
        result = detect_stack_signals(tmp_path, files)
        assert "Node.js" in result
        assert "Python" in result
        assert "Docker" in result

    def test_results_sorted_and_unique(self, tmp_path: Path) -> None:
        """Test that stack file lists are sorted and unique."""
        files = [
            FileRecord(rel="pyproject.toml", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
            FileRecord(rel="requirements.txt", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
        ]
        result = detect_stack_signals(tmp_path, files)
        python_files = result["Python"]
        assert python_files == sorted(set(python_files))

    def test_no_matches_returns_empty(self, tmp_path: Path) -> None:
        """Test that no matching files returns empty dict."""
        files = [
            FileRecord(rel="random.xyz", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
        ]
        result = detect_stack_signals(tmp_path, files)
        assert result == {}

    def test_empty_files_returns_empty(self, tmp_path: Path) -> None:
        """Test that empty file list returns empty dict."""
        result = detect_stack_signals(tmp_path, [])
        assert result == {}


class TestExtractPackageJsonScripts:
    """Tests for extract_package_json_scripts function."""

    def test_extracts_scripts(self, tmp_path: Path) -> None:
        """Test extraction of npm scripts."""
        pkg_json = tmp_path / "package.json"
        pkg_json.write_text(json.dumps({
            "name": "test-package",
            "scripts": {
                "build": "webpack",
                "test": "jest",
            }
        }))
        files = [
            FileRecord(rel="package.json", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
        ]
        result = extract_package_json_scripts(tmp_path, files)
        assert any("package.json" in line for line in result)
        assert any("build" in line for line in result)
        assert any("test" in line for line in result)

    def test_truncates_long_scripts(self, tmp_path: Path) -> None:
        """Test that long script values are truncated."""
        long_cmd = "a" * 150
        pkg_json = tmp_path / "package.json"
        pkg_json.write_text(json.dumps({
            "scripts": {
                "long": long_cmd,
            }
        }))
        files = [
            FileRecord(rel="package.json", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
        ]
        result = extract_package_json_scripts(tmp_path, files)
        long_line = [line for line in result if "long" in line][0]
        assert "..." in long_line
        assert len(long_line) < len(long_cmd) + 50  # Some margin for formatting

    def test_no_package_json_returns_empty(self, tmp_path: Path) -> None:
        """Test that no package.json returns empty list."""
        files = [
            FileRecord(rel="main.py", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
        ]
        result = extract_package_json_scripts(tmp_path, files)
        assert result == []

    def test_package_json_without_scripts(self, tmp_path: Path) -> None:
        """Test package.json without scripts section."""
        pkg_json = tmp_path / "package.json"
        pkg_json.write_text(json.dumps({
            "name": "test-package",
            "version": "1.0.0",
        }))
        files = [
            FileRecord(rel="package.json", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
        ]
        result = extract_package_json_scripts(tmp_path, files)
        assert result == []

    def test_handles_invalid_json(self, tmp_path: Path) -> None:
        """Test handling of invalid JSON in package.json."""
        pkg_json = tmp_path / "package.json"
        pkg_json.write_text("{ invalid json }")
        files = [
            FileRecord(rel="package.json", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
        ]
        result = extract_package_json_scripts(tmp_path, files)
        assert result == []

    def test_limits_to_5_package_jsons(self, tmp_path: Path) -> None:
        """Test that only up to 5 package.json files are processed."""
        for i in range(10):
            subdir = tmp_path / f"pkg{i}"
            subdir.mkdir()
            pkg_json = subdir / "package.json"
            pkg_json.write_text(json.dumps({
                "scripts": {"script": f"cmd{i}"}
            }))
        files = [
            FileRecord(rel=f"pkg{i}/package.json", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False)
            for i in range(10)
        ]
        result = extract_package_json_scripts(tmp_path, files)
        # Count how many package.json file references are in the result
        pkg_refs = [line for line in result if "package.json" in line and line.startswith("-")]
        assert len(pkg_refs) <= 5

    def test_scripts_sorted_alphabetically(self, tmp_path: Path) -> None:
        """Test that scripts are sorted alphabetically."""
        pkg_json = tmp_path / "package.json"
        pkg_json.write_text(json.dumps({
            "scripts": {
                "zebra": "echo zebra",
                "alpha": "echo alpha",
                "beta": "echo beta",
            }
        }))
        files = [
            FileRecord(rel="package.json", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
        ]
        result = extract_package_json_scripts(tmp_path, files)
        script_lines = [line for line in result if line.startswith("  -")]
        script_names = [line.split("`")[1] for line in script_lines]
        assert script_names == sorted(script_names)


class TestIntegration:
    """Integration tests for detect module with real filesystem."""

    def test_full_detection_workflow(self, tmp_path: Path) -> None:
        """Test complete detection workflow with realistic project structure."""
        # Create a realistic project structure
        (tmp_path / "README.md").write_text("# Test Project")
        (tmp_path / "package.json").write_text(json.dumps({
            "name": "test",
            "scripts": {"test": "jest", "build": "webpack"}
        }))
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "index.ts").write_text("export default {}")
        (tmp_path / "Dockerfile").write_text("FROM node:18")

        files = [
            FileRecord(rel="README.md", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
            FileRecord(rel="package.json", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
            FileRecord(rel="src/index.ts", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
            FileRecord(rel="Dockerfile", size=100, mtime_iso="2026-01-24T00:00:00Z", is_dir=False),
        ]

        # Test all detection functions
        important = collect_important_files(tmp_path, files)
        assert "README.md" in important
        assert "package.json" in important
        assert "Dockerfile" in important

        entrypoints = collect_entrypoints(tmp_path, files)
        assert "src/index.ts" in entrypoints

        stacks = detect_stack_signals(tmp_path, files)
        assert "Node.js" in stacks
        assert "Docker" in stacks

        scripts = extract_package_json_scripts(tmp_path, files)
        assert len(scripts) > 0
        assert any("test" in line for line in scripts)
        assert any("build" in line for line in scripts)
