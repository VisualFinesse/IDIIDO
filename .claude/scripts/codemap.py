#!/usr/bin/env python3
"""
CodeMap - Universal Code Structure Documentation Generator

Generates clean, hierarchical code documentation optimized for LLM consumption.
Works with any tech stack and any architecture. Zero external dependencies.

- Python files: exact analysis via built-in `ast` module
- All other languages: regex-based extraction of classes, functions, methods, imports
- Supports: Python, TypeScript, JavaScript, Go, Rust, Java, C#, C/C++, Ruby, PHP,
  Kotlin, Swift, Scala, Dart, Lua, Elixir, Zig, Vue, Svelte

Usage:
    python codemap.py                           # analyze current directory
    python codemap.py --root /path/to/project   # analyze specific directory
    python codemap.py --out CODEMAP.md          # custom output filename
    python codemap.py --no-outline              # skip detailed code outline
    python codemap.py --max-depth 8             # deeper tree rendering
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class FunctionInfo:
    """A function or method extracted from source code."""
    name: str
    parameters: str = ""
    return_type: str = ""
    is_async: bool = False
    is_static: bool = False
    is_private: bool = False
    is_constructor: bool = False
    is_property: bool = False
    decorators: List[str] = field(default_factory=list)
    line_number: int = 0


@dataclass
class VariableInfo:
    """A class field, constant, or variable."""
    name: str
    type_hint: str = ""
    is_constant: bool = False
    line_number: int = 0


@dataclass
class ClassInfo:
    """A class, interface, struct, enum, or trait."""
    name: str
    kind: str = "class"  # class, interface, struct, enum, trait, type
    bases: List[str] = field(default_factory=list)
    implements: List[str] = field(default_factory=list)
    methods: List[FunctionInfo] = field(default_factory=list)
    variables: List[VariableInfo] = field(default_factory=list)
    line_number: int = 0


@dataclass
class ImportInfo:
    """An import statement."""
    source: str
    names: List[str] = field(default_factory=list)
    is_local: bool = False


@dataclass
class FileAnalysis:
    """Complete analysis of a single source file."""
    path: str
    language: str = ""
    doc_comment: str = ""
    imports: List[ImportInfo] = field(default_factory=list)
    classes: List[ClassInfo] = field(default_factory=list)
    functions: List[FunctionInfo] = field(default_factory=list)
    constants: List[VariableInfo] = field(default_factory=list)
    has_entry_point: bool = False
    line_count: int = 0


# ============================================================================
# Language Registry & Configuration
# ============================================================================

LANG_MAP: Dict[str, str] = {
    ".py": "python",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".mts": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin", ".kts": "kotlin",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".hpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hxx": "cpp",
    ".scala": "scala",
    ".dart": "dart",
    ".lua": "lua",
    ".ex": "elixir", ".exs": "elixir",
    ".zig": "zig",
    ".vue": "vue",
    ".svelte": "svelte",
    ".r": "r", ".R": "r",
    ".jl": "julia",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell",
    ".ps1": "powershell", ".psm1": "powershell",
}

SOURCE_EXTENSIONS: Set[str] = set(LANG_MAP.keys())

BINARY_EXTENSIONS: Set[str] = {
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib", ".exe", ".obj", ".o",
    ".a", ".lib", ".class", ".jar", ".war", ".ear",
    ".zip", ".tar", ".gz", ".7z", ".rar", ".bz2", ".xz",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".svg",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".mp4", ".mov", ".avi", ".mkv", ".mp3", ".wav", ".flac", ".ogg",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".sqlite", ".db", ".mdb",
    ".min.js", ".min.css", ".map",
}

DEFAULT_DIR_EXCLUDES: Set[str] = {
    ".git", ".hg", ".svn", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".tox", ".venv", "venv", "env", ".env",
    ".idea", ".vscode", "node_modules", "dist", "build", "out", "target",
    ".next", ".nuxt", ".cache", ".turbo", ".parcel-cache", ".angular",
    ".gradle", ".terraform", ".terragrunt-cache", ".sass-cache",
    ".expo", ".yarn", ".pnpm-store", "vendor", "coverage",
    ".output", ".vercel", ".serverless", "bin", "obj",
    "__mocks__", ".docusaurus",
}

DEFAULT_FILE_EXCLUDES: Set[str] = {
    "*.pyc", "*.pyo", "*.pyd", "*.so", "*.dll", "*.dylib", "*.exe",
    "*.obj", "*.o", "*.a", "*.lib", "*.class", "*.jar",
    "*.zip", "*.tar", "*.gz", "*.7z", "*.rar",
    "*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp", "*.ico", "*.bmp",
    "*.pdf", "*.mp4", "*.mov", "*.mp3", "*.wav",
    "*.ttf", "*.otf", "*.woff", "*.woff2",
    "*.DS_Store", "*.lock", "package-lock.json", "yarn.lock",
    "pnpm-lock.yaml", "Cargo.lock", "poetry.lock", "Pipfile.lock",
    "composer.lock", "Gemfile.lock", "go.sum",
    "*.min.js", "*.min.css", "*.map", "*.chunk.*",
    "*.sqlite", "*.db",
}

# Functional categories for Quick Navigation
CATEGORIES: Dict[str, List[str]] = {
    "Authentication & Authorization": [
        "auth", "login", "session", "token", "credential", "oauth",
        "jwt", "passport", "identity", "sso", "saml", "permission",
    ],
    "API/Endpoints/Routes": [
        "api", "endpoint", "route", "controller", "handler",
        "middleware", "router", "graphql", "resolver", "gateway",
    ],
    "Database/Models/ORM": [
        "db", "database", "model", "schema", "repository",
        "migration", "entity", "dao", "seed",
    ],
    "Services/Business Logic": [
        "service", "provider", "manager", "engine", "processor",
        "worker", "job", "task", "queue", "pipeline",
    ],
    "UI/Components": [
        "component", "view", "page", "layout", "widget",
        "template", "screen", "modal", "dialog",
    ],
    "State Management": [
        "store", "state", "reducer", "action", "slice",
        "context", "atom", "selector", "effect",
    ],
    "Configuration/Settings": [
        "config", "settings", "env", "constant", "options",
        "preferences", "feature_flag",
    ],
    "Utilities/Helpers": [
        "util", "helper", "tool", "common", "shared",
        "lib", "support", "misc", "core",
    ],
    "Types/Interfaces": [
        "type", "interface", "dto", "enum", "contract",
        "protocol", "schema",
    ],
    "Tests": [
        "test", "spec", "__tests__", "e2e", "integration",
        "fixture", "mock", "stub", "fake",
    ],
    "CLI/Scripts": [
        "cli", "script", "command", "cmd",
    ],
    "Infrastructure/DevOps": [
        "docker", "k8s", "terraform", "deploy", "ci",
        "cd", "pipeline", "infra", "helm", "ansible",
    ],
}

ENTRYPOINT_PATTERNS: List[str] = [
    "main.py", "__main__.py", "app.py", "server.py", "manage.py",
    "wsgi.py", "asgi.py", "cli.py",
    "main.ts", "main.js", "index.ts", "index.js",
    "server.ts", "server.js", "app.ts", "app.js",
    "src/main.*", "src/index.*", "src/app.*",
    "cmd/*/main.go", "main.go",
    "Program.cs", "src/Program.cs",
    "src/main.rs", "src/lib.rs",
    "main.kt", "Application.kt",
    "main.swift", "AppDelegate.swift",
    "main.dart", "lib/main.dart",
]

ENTRY_FUNCTION_NAMES: Set[str] = {
    "main", "run", "start", "execute", "cli", "app", "serve",
    "boot", "init", "launch", "handle",
}


# ============================================================================
# Python Analyzer (ast-based)
# ============================================================================

class PythonAnalyzer:
    """Analyze Python files using the built-in ast module for exact parsing."""

    STDLIB_MODULES: Set[str] = {
        "__future__",
        "abc", "aifc", "argparse", "array", "ast", "asyncio", "atexit",
        "base64", "bisect", "builtins", "calendar", "cgi", "cmath",
        "cmd", "codecs", "collections", "colorsys", "concurrent",
        "configparser", "contextlib", "contextvars", "copy", "copyreg",
        "csv", "ctypes", "curses", "dataclasses", "datetime", "dbm",
        "decimal", "difflib", "dis", "distutils", "email", "encodings",
        "enum", "errno", "faulthandler", "fcntl", "filecmp", "fileinput",
        "fnmatch", "fractions", "ftplib", "functools", "gc", "getpass",
        "gettext", "glob", "gzip", "hashlib", "heapq", "hmac", "html",
        "http", "imaplib", "importlib", "inspect", "io", "ipaddress",
        "itertools", "json", "keyword", "linecache", "locale", "logging",
        "lzma", "mailbox", "math", "mimetypes", "mmap", "multiprocessing",
        "numbers", "operator", "os", "pathlib", "pdb", "pickle",
        "pkgutil", "platform", "plistlib", "poplib", "posixpath", "pprint",
        "profile", "pstats", "pty", "pwd", "py_compile", "pydoc",
        "queue", "quopri", "random", "re", "readline", "reprlib",
        "resource", "rlcompleter", "runpy", "sched", "secrets",
        "select", "selectors", "shelve", "shlex", "shutil", "signal",
        "site", "smtplib", "socket", "socketserver", "sqlite3",
        "ssl", "stat", "statistics", "string", "struct", "subprocess",
        "sunau", "symtable", "sys", "sysconfig", "syslog", "tabnanny",
        "tarfile", "tempfile", "test", "textwrap", "threading", "time",
        "timeit", "tkinter", "token", "tokenize", "tomllib", "trace",
        "traceback", "tracemalloc", "tty", "turtle", "types", "typing",
        "unicodedata", "unittest", "urllib", "uuid", "venv", "warnings",
        "wave", "weakref", "webbrowser", "winreg", "winsound", "wsgiref",
        "xdrlib", "xml", "xmlrpc", "zipapp", "zipfile", "zipimport", "zlib",
    }

    @staticmethod
    def analyze(filepath: Path, relative_path: str) -> Optional[FileAnalysis]:
        """Analyze a Python file using the ast module."""
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return None

        analysis = FileAnalysis(
            path=relative_path,
            language="python",
            line_count=len(content.splitlines()),
        )

        # Module docstring
        doc = ast.get_docstring(tree)
        if doc:
            first_line = doc.split("\n")[0].strip()
            analysis.doc_comment = first_line[:120]

        # Walk top-level nodes
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                analysis.classes.append(PythonAnalyzer._extract_class(node))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                analysis.functions.append(PythonAnalyzer._extract_function(node))
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        analysis.constants.append(VariableInfo(
                            name=target.id, is_constant=True, line_number=node.lineno
                        ))
            elif isinstance(node, ast.If):
                if (isinstance(node.test, ast.Compare) and
                    isinstance(node.test.left, ast.Name) and
                    node.test.left.id == "__name__"):
                    analysis.has_entry_point = True
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                imp = PythonAnalyzer._extract_import(node)
                if imp:
                    analysis.imports.append(imp)

        # Also walk for imports inside functions/classes
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if not any(n is node for n in tree.body):
                    imp = PythonAnalyzer._extract_import(node)
                    if imp and not any(
                        i.source == imp.source for i in analysis.imports
                    ):
                        analysis.imports.append(imp)

        return analysis

    @staticmethod
    def _extract_class(node: ast.ClassDef) -> ClassInfo:
        """Extract class information from an AST ClassDef node."""
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(PythonAnalyzer._get_dotted_name(base))
            elif isinstance(base, ast.Subscript):
                if isinstance(base.value, ast.Name):
                    bases.append(base.value.id)

        cls = ClassInfo(
            name=node.name,
            kind="class",
            bases=bases,
            line_number=node.lineno,
        )

        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func = PythonAnalyzer._extract_function(item, is_method=True)
                if any(d in func.decorators for d in ["property", "cached_property"]):
                    func.is_property = True
                cls.methods.append(func)
            elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                type_str = PythonAnalyzer._get_annotation_str(item.annotation)
                cls.variables.append(VariableInfo(
                    name=item.target.id, type_hint=type_str, line_number=item.lineno
                ))
            elif isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        is_const = target.id.isupper()
                        cls.variables.append(VariableInfo(
                            name=target.id, is_constant=is_const, line_number=item.lineno
                        ))

        return cls

    @staticmethod
    def _extract_function(node, is_method: bool = False) -> FunctionInfo:
        """Extract function/method info from an AST node."""
        params = []
        args = node.args
        start_idx = 1 if is_method and args.args else 0

        for arg in args.args[start_idx:]:
            param = arg.arg
            if arg.annotation:
                param += f": {PythonAnalyzer._get_annotation_str(arg.annotation)}"
            params.append(param)
        if args.vararg:
            params.append(f"*{args.vararg.arg}")
        if args.kwarg:
            params.append(f"**{args.kwarg.arg}")

        decorators = []
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name):
                decorators.append(dec.id)
            elif isinstance(dec, ast.Attribute):
                decorators.append(dec.attr)
            elif isinstance(dec, ast.Call):
                if isinstance(dec.func, ast.Name):
                    decorators.append(dec.func.id)
                elif isinstance(dec.func, ast.Attribute):
                    decorators.append(dec.func.attr)

        return_type = ""
        if node.returns:
            return_type = PythonAnalyzer._get_annotation_str(node.returns)

        return FunctionInfo(
            name=node.name,
            parameters=", ".join(params),
            return_type=return_type,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            is_static="staticmethod" in decorators,
            is_private=node.name.startswith("_"),
            is_constructor=node.name == "__init__",
            is_property="property" in decorators or "cached_property" in decorators,
            decorators=decorators,
            line_number=node.lineno,
        )

    @staticmethod
    def _extract_import(node) -> Optional[ImportInfo]:
        """Extract import information from an AST node."""
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name.split(".")[0]
                return ImportInfo(
                    source=alias.name,
                    is_local=module not in PythonAnalyzer.STDLIB_MODULES and not module.startswith("."),
                )
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                source = "." * node.level + (node.module or "")
                names = [a.name for a in (node.names or [])]
                return ImportInfo(source=source, names=names, is_local=True)
            elif node.module:
                module = node.module.split(".")[0]
                names = [a.name for a in (node.names or [])]
                is_local = module not in PythonAnalyzer.STDLIB_MODULES
                return ImportInfo(source=node.module, names=names, is_local=is_local)
        return None

    @staticmethod
    def _get_annotation_str(node) -> str:
        """Convert an annotation AST node to a string."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.Attribute):
            return PythonAnalyzer._get_dotted_name(node)
        elif isinstance(node, ast.Subscript):
            base = PythonAnalyzer._get_annotation_str(node.value)
            if isinstance(node.slice, ast.Tuple):
                elts = ", ".join(PythonAnalyzer._get_annotation_str(e) for e in node.slice.elts)
                return f"{base}[{elts}]"
            else:
                sub = PythonAnalyzer._get_annotation_str(node.slice)
                return f"{base}[{sub}]"
        elif isinstance(node, (ast.List, ast.Tuple)):
            elts = ", ".join(PythonAnalyzer._get_annotation_str(e) for e in node.elts)
            return f"({elts})" if isinstance(node, ast.Tuple) else f"[{elts}]"
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            left = PythonAnalyzer._get_annotation_str(node.left)
            right = PythonAnalyzer._get_annotation_str(node.right)
            return f"{left} | {right}"
        return "Any"

    @staticmethod
    def _get_dotted_name(node) -> str:
        """Get a dotted name from an Attribute node."""
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
        return ".".join(reversed(parts))


# ============================================================================
# Regex-Based Analyzers (for non-Python languages)
# ============================================================================

class RegexAnalyzer:
    """Regex-based code analysis for non-Python languages."""

    @staticmethod
    def analyze(filepath: Path, relative_path: str, language: str) -> Optional[FileAnalysis]:
        """Analyze a source file using regex patterns."""
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None

        analysis = FileAnalysis(
            path=relative_path,
            language=language,
            line_count=len(content.splitlines()),
        )

        # Dispatch to language-specific analyzer
        extractors = {
            "typescript": RegexAnalyzer._analyze_typescript,
            "javascript": RegexAnalyzer._analyze_typescript,  # close enough
            "go": RegexAnalyzer._analyze_go,
            "rust": RegexAnalyzer._analyze_rust,
            "java": RegexAnalyzer._analyze_java,
            "kotlin": RegexAnalyzer._analyze_java,  # similar syntax
            "csharp": RegexAnalyzer._analyze_csharp,
            "ruby": RegexAnalyzer._analyze_ruby,
            "php": RegexAnalyzer._analyze_php,
            "swift": RegexAnalyzer._analyze_swift,
            "c": RegexAnalyzer._analyze_c_cpp,
            "cpp": RegexAnalyzer._analyze_c_cpp,
            "scala": RegexAnalyzer._analyze_scala,
            "dart": RegexAnalyzer._analyze_dart,
            "elixir": RegexAnalyzer._analyze_elixir,
            "lua": RegexAnalyzer._analyze_lua,
            "zig": RegexAnalyzer._analyze_zig,
            "vue": RegexAnalyzer._analyze_typescript,  # script section
            "svelte": RegexAnalyzer._analyze_typescript,
            "shell": RegexAnalyzer._analyze_shell,
            "powershell": RegexAnalyzer._analyze_powershell,
            "r": RegexAnalyzer._analyze_r,
            "julia": RegexAnalyzer._analyze_julia,
        }

        extractor = extractors.get(language, RegexAnalyzer._analyze_generic)
        extractor(content, analysis)

        # Detect entry points by content patterns
        if not analysis.has_entry_point:
            analysis.has_entry_point = RegexAnalyzer._detect_entry_point(content, language)

        return analysis

    # -- TypeScript / JavaScript --

    @staticmethod
    def _analyze_typescript(content: str, analysis: FileAnalysis) -> None:
        """Extract structure from TypeScript/JavaScript files."""
        lines = content.splitlines()

        # Imports
        for line in lines:
            m = re.match(r'''^\s*import\s+.*?from\s+['"](.+?)['"]''', line)
            if m:
                source = m.group(1)
                is_local = source.startswith(".") or source.startswith("@/")
                analysis.imports.append(ImportInfo(source=source, is_local=is_local))
                continue
            m = re.match(r'''^\s*(?:const|let|var)\s+.*?=\s*require\s*\(\s*['"](.+?)['"]\s*\)''', line)
            if m:
                source = m.group(1)
                is_local = source.startswith(".")
                analysis.imports.append(ImportInfo(source=source, is_local=is_local))

        # Classes and interfaces
        for m in re.finditer(
            r'^[ \t]*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?(class|interface)\s+(\w+)'
            r'(?:\s+extends\s+([\w.]+))?(?:\s+implements\s+([\w,\s.]+))?',
            content, re.MULTILINE
        ):
            kind = m.group(1)
            name = m.group(2)
            bases = [m.group(3)] if m.group(3) else []
            impls = [s.strip() for s in m.group(4).split(",")] if m.group(4) else []
            cls = ClassInfo(name=name, kind=kind, bases=bases, implements=impls)

            # Try to extract methods from the class body
            class_start = m.end()
            class_body = RegexAnalyzer._extract_brace_block(content, class_start)
            if class_body:
                for mm in re.finditer(
                    r'^[ \t]+(?:(static|private|protected|public|readonly|abstract|async|get|set)\s+)*'
                    r'(\w+)\s*(?:<[^>]*>)?\s*\(([^)]*)\)(?:\s*:\s*([^\n{]+?))?',
                    class_body, re.MULTILINE
                ):
                    modifiers = mm.group(1) or ""
                    fname = mm.group(2)
                    params = mm.group(3).strip()
                    ret = (mm.group(4) or "").strip().rstrip("{").strip()
                    if fname in ("if", "for", "while", "switch", "catch", "return"):
                        continue
                    cls.methods.append(FunctionInfo(
                        name=fname,
                        parameters=RegexAnalyzer._clean_params(params),
                        return_type=ret,
                        is_async="async" in modifiers,
                        is_static="static" in modifiers,
                        is_private="private" in modifiers or fname.startswith("_"),
                        is_constructor=fname == "constructor",
                        is_property="get" in modifiers or "set" in modifiers,
                    ))
            analysis.classes.append(cls)

        # Type aliases and enums
        for m in re.finditer(
            r'^[ \t]*(?:export\s+)?(type|enum)\s+(\w+)',
            content, re.MULTILINE
        ):
            kind = m.group(1)
            name = m.group(2)
            analysis.classes.append(ClassInfo(name=name, kind=kind))

        # Top-level functions
        for m in re.finditer(
            r'^(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)\s*'
            r'(?:<[^>]*>)?\s*\(([^)]*)\)(?:\s*:\s*([^\n{]+?))?',
            content, re.MULTILINE
        ):
            name = m.group(1)
            params = m.group(2).strip()
            ret = (m.group(3) or "").strip().rstrip("{").strip()
            is_async = "async" in content[max(0, m.start() - 20):m.start()]
            analysis.functions.append(FunctionInfo(
                name=name,
                parameters=RegexAnalyzer._clean_params(params),
                return_type=ret,
                is_async=is_async,
            ))

        # Arrow functions assigned to const/export
        for m in re.finditer(
            r'^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*'
            r'(?::\s*[\w<>\[\]|&,\s]+)?\s*=\s*(?:async\s+)?'
            r'(?:\([^)]*\)|[a-zA-Z_]\w*)\s*(?::\s*[^\n=]+?)?\s*=>',
            content, re.MULTILINE
        ):
            name = m.group(1)
            is_async = "async" in content[m.start():m.end()]
            analysis.functions.append(FunctionInfo(
                name=name, is_async=is_async,
            ))

        # Constants
        for m in re.finditer(
            r'^(?:export\s+)?const\s+([A-Z][A-Z0-9_]+)\s*(?::\s*(\w+))?\s*=',
            content, re.MULTILINE
        ):
            analysis.constants.append(VariableInfo(
                name=m.group(1), type_hint=m.group(2) or "", is_constant=True,
            ))

    # -- Go --

    @staticmethod
    def _analyze_go(content: str, analysis: FileAnalysis) -> None:
        """Extract structure from Go files."""
        # Package-level doc comment
        m = re.match(r'^\s*//\s*(.+)', content)
        if m:
            analysis.doc_comment = m.group(1).strip()[:120]

        # Imports
        for m in re.finditer(r'import\s+\(\s*([\s\S]*?)\s*\)', content):
            block = m.group(1)
            for line in block.splitlines():
                line = line.strip().strip('"')
                if line and not line.startswith("//"):
                    line = line.split('"')[1] if '"' in line else line
                    if line:
                        analysis.imports.append(ImportInfo(source=line, is_local="/" not in line))

        for m in re.finditer(r'import\s+"(.+?)"', content):
            analysis.imports.append(ImportInfo(source=m.group(1)))

        # Structs
        for m in re.finditer(r'^type\s+(\w+)\s+struct\s*\{', content, re.MULTILINE):
            analysis.classes.append(ClassInfo(name=m.group(1), kind="struct"))

        # Interfaces
        for m in re.finditer(r'^type\s+(\w+)\s+interface\s*\{', content, re.MULTILINE):
            analysis.classes.append(ClassInfo(name=m.group(1), kind="interface"))

        # Functions (not methods)
        for m in re.finditer(
            r'^func\s+(\w+)\s*\(([^)]*)\)\s*([^{]*?)\s*\{',
            content, re.MULTILINE
        ):
            name = m.group(1)
            params = m.group(2).strip()
            ret = m.group(3).strip()
            analysis.functions.append(FunctionInfo(
                name=name,
                parameters=RegexAnalyzer._clean_params(params),
                return_type=ret,
                is_private=name[0].islower() if name else False,
            ))

        # Methods (with receiver)
        for m in re.finditer(
            r'^func\s+\(\s*\w+\s+\*?(\w+)\s*\)\s+(\w+)\s*\(([^)]*)\)\s*([^{]*?)\s*\{',
            content, re.MULTILINE
        ):
            receiver = m.group(1)
            name = m.group(2)
            params = m.group(3).strip()
            ret = m.group(4).strip()
            # Find or create the class
            cls = next((c for c in analysis.classes if c.name == receiver), None)
            if not cls:
                cls = ClassInfo(name=receiver, kind="struct")
                analysis.classes.append(cls)
            cls.methods.append(FunctionInfo(
                name=name,
                parameters=RegexAnalyzer._clean_params(params),
                return_type=ret,
                is_private=name[0].islower() if name else False,
            ))

        # Constants
        for m in re.finditer(r'^\s*const\s+(\w+)\s*', content, re.MULTILINE):
            name = m.group(1)
            if name.isupper() or name[0].isupper():
                analysis.constants.append(VariableInfo(name=name, is_constant=True))

    # -- Rust --

    @staticmethod
    def _analyze_rust(content: str, analysis: FileAnalysis) -> None:
        """Extract structure from Rust files."""
        # Imports (use statements)
        for m in re.finditer(r'^\s*use\s+([\w:]+(?:::\{[^}]+\})?);', content, re.MULTILINE):
            source = m.group(1)
            is_local = source.startswith("crate::") or source.startswith("super::")
            analysis.imports.append(ImportInfo(source=source, is_local=is_local))

        # Structs
        for m in re.finditer(r'^(?:pub(?:\([^)]*\))?\s+)?struct\s+(\w+)', content, re.MULTILINE):
            analysis.classes.append(ClassInfo(name=m.group(1), kind="struct"))

        # Enums
        for m in re.finditer(r'^(?:pub(?:\([^)]*\))?\s+)?enum\s+(\w+)', content, re.MULTILINE):
            analysis.classes.append(ClassInfo(name=m.group(1), kind="enum"))

        # Traits
        for m in re.finditer(r'^(?:pub(?:\([^)]*\))?\s+)?trait\s+(\w+)', content, re.MULTILINE):
            analysis.classes.append(ClassInfo(name=m.group(1), kind="trait"))

        # Impl blocks
        for m in re.finditer(
            r'^impl(?:<[^>]*>)?\s+(?:(\w+)\s+for\s+)?(\w+)',
            content, re.MULTILINE
        ):
            trait_name = m.group(1)
            struct_name = m.group(2)
            cls = next((c for c in analysis.classes if c.name == struct_name), None)
            if not cls:
                cls = ClassInfo(name=struct_name, kind="struct")
                analysis.classes.append(cls)
            if trait_name:
                cls.implements.append(trait_name)

            # Extract methods from impl block
            block_start = m.end()
            block = RegexAnalyzer._extract_brace_block(content, block_start)
            if block:
                for fm in re.finditer(
                    r'(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+(\w+)\s*(?:<[^>]*>)?\s*\(([^)]*)\)(?:\s*->\s*(.+?))?(?:\s*(?:where|\{))',
                    block
                ):
                    fname = fm.group(1)
                    params = fm.group(2).strip()
                    # Remove &self, &mut self, self from params display
                    params = re.sub(r'&(?:mut\s+)?self\s*,?\s*', '', params).strip().strip(",").strip()
                    ret = (fm.group(3) or "").strip()
                    is_pub = "pub" in block[max(0, fm.start() - 10):fm.start()]
                    cls.methods.append(FunctionInfo(
                        name=fname,
                        parameters=RegexAnalyzer._clean_params(params),
                        return_type=ret,
                        is_async="async" in block[max(0, fm.start() - 20):fm.start()],
                        is_private=not is_pub,
                    ))

        # Free functions
        for m in re.finditer(
            r'^(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+(\w+)\s*(?:<[^>]*>)?\s*\(([^)]*)\)(?:\s*->\s*(.+?))?(?:\s*(?:where|\{))',
            content, re.MULTILINE
        ):
            name = m.group(1)
            # Skip if this is inside an impl block (crude check: not at column 0)
            line_start = content.rfind("\n", 0, m.start()) + 1
            indent = m.start() - line_start
            if indent > 0:
                continue
            params = m.group(2).strip()
            ret = (m.group(3) or "").strip()
            analysis.functions.append(FunctionInfo(
                name=name,
                parameters=RegexAnalyzer._clean_params(params),
                return_type=ret,
                is_async="async" in content[max(0, m.start() - 10):m.start()],
                is_private=not name[0].isupper() if name else False,
            ))

    # -- Java / Kotlin --

    @staticmethod
    def _analyze_java(content: str, analysis: FileAnalysis) -> None:
        """Extract structure from Java/Kotlin files."""
        # Imports
        for m in re.finditer(r'^\s*import\s+([\w.]+);?', content, re.MULTILINE):
            analysis.imports.append(ImportInfo(source=m.group(1)))

        # Classes, interfaces, enums
        for m in re.finditer(
            r'^[ \t]*(?:(?:public|private|protected|internal)\s+)?'
            r'(?:(?:static|abstract|final|sealed|data|open|inner)\s+)*'
            r'(class|interface|enum|object|annotation)\s+(\w+)'
            r'(?:\s*(?:extends|:)\s*([\w.]+))?'
            r'(?:\s*(?:implements|,)\s*([\w.,\s]+))?',
            content, re.MULTILINE
        ):
            kind = m.group(1)
            name = m.group(2)
            bases = [m.group(3)] if m.group(3) else []
            impls = [s.strip() for s in m.group(4).split(",")] if m.group(4) else []
            cls = ClassInfo(name=name, kind=kind, bases=bases, implements=impls)

            # Extract methods
            class_start = m.end()
            body = RegexAnalyzer._extract_brace_block(content, class_start)
            if body:
                for fm in re.finditer(
                    r'^[ \t]+(?:(?:public|private|protected|internal)\s+)?'
                    r'(?:(?:static|abstract|final|override|open|suspend|inline)\s+)*'
                    r'(?:fun\s+)?'
                    r'(?:(\w+(?:<[^>]*>)?)\s+)?(\w+)\s*\(([^)]*)\)'
                    r'(?:\s*:\s*(\w+))?',
                    body, re.MULTILINE
                ):
                    ret_type = fm.group(1) or fm.group(4) or ""
                    fname = fm.group(2)
                    params = fm.group(3).strip()
                    if fname in ("if", "for", "while", "switch", "catch", "return", "when"):
                        continue
                    is_private = "private" in body[max(0, fm.start() - 30):fm.start()]
                    cls.methods.append(FunctionInfo(
                        name=fname,
                        parameters=RegexAnalyzer._clean_params(params),
                        return_type=ret_type.strip(),
                        is_static="static" in body[max(0, fm.start() - 30):fm.start()],
                        is_private=is_private,
                        is_constructor=fname == name,
                    ))
            analysis.classes.append(cls)

    # -- C# --

    @staticmethod
    def _analyze_csharp(content: str, analysis: FileAnalysis) -> None:
        """Extract structure from C# files."""
        # Using statements
        for m in re.finditer(r'^\s*using\s+([\w.]+);', content, re.MULTILINE):
            analysis.imports.append(ImportInfo(source=m.group(1)))

        # Classes, interfaces, structs, enums, records
        for m in re.finditer(
            r'^[ \t]*(?:(?:public|private|protected|internal)\s+)?'
            r'(?:(?:static|abstract|sealed|partial)\s+)*'
            r'(class|interface|struct|enum|record)\s+(\w+)'
            r'(?:\s*:\s*([\w.,\s<>]+))?',
            content, re.MULTILINE
        ):
            kind = m.group(1)
            name = m.group(2)
            parents = [s.strip() for s in (m.group(3) or "").split(",") if s.strip()]
            cls = ClassInfo(name=name, kind=kind, bases=parents[:1], implements=parents[1:])

            body = RegexAnalyzer._extract_brace_block(content, m.end())
            if body:
                for fm in re.finditer(
                    r'^[ \t]+(?:(?:public|private|protected|internal)\s+)?'
                    r'(?:(?:static|virtual|override|abstract|async|new|sealed)\s+)*'
                    r'(\w+(?:<[^>]*>)?)\s+(\w+)\s*\(([^)]*)\)',
                    body, re.MULTILINE
                ):
                    ret = fm.group(1)
                    fname = fm.group(2)
                    params = fm.group(3).strip()
                    if fname in ("if", "for", "foreach", "while", "switch", "catch", "return"):
                        continue
                    is_private = "private" in body[max(0, fm.start() - 30):fm.start()]
                    is_async = "async" in body[max(0, fm.start() - 20):fm.start()]
                    cls.methods.append(FunctionInfo(
                        name=fname,
                        parameters=RegexAnalyzer._clean_params(params),
                        return_type=ret,
                        is_async=is_async,
                        is_static="static" in body[max(0, fm.start() - 30):fm.start()],
                        is_private=is_private,
                        is_constructor=fname == name,
                    ))
            analysis.classes.append(cls)

    # -- Ruby --

    @staticmethod
    def _analyze_ruby(content: str, analysis: FileAnalysis) -> None:
        """Extract structure from Ruby files."""
        # Requires
        for m in re.finditer(r'''^\s*require(?:_relative)?\s+['"](.+?)['"]''', content, re.MULTILINE):
            source = m.group(1)
            is_local = "require_relative" in content[m.start():m.end()]
            analysis.imports.append(ImportInfo(source=source, is_local=is_local))

        # Classes
        for m in re.finditer(r'^[ \t]*class\s+(\w+)(?:\s*<\s*(\w+))?', content, re.MULTILINE):
            name = m.group(1)
            bases = [m.group(2)] if m.group(2) else []
            cls = ClassInfo(name=name, kind="class", bases=bases)
            analysis.classes.append(cls)

        # Modules
        for m in re.finditer(r'^[ \t]*module\s+(\w+)', content, re.MULTILINE):
            analysis.classes.append(ClassInfo(name=m.group(1), kind="module"))

        # Methods
        for m in re.finditer(
            r'^[ \t]*def\s+(self\.)?(\w+[?!=]?)\s*(?:\(([^)]*)\))?',
            content, re.MULTILINE
        ):
            is_class_method = bool(m.group(1))
            name = m.group(2)
            params = (m.group(3) or "").strip()
            analysis.functions.append(FunctionInfo(
                name=name,
                parameters=params,
                is_static=is_class_method,
                is_private=name.startswith("_"),
            ))

    # -- PHP --

    @staticmethod
    def _analyze_php(content: str, analysis: FileAnalysis) -> None:
        """Extract structure from PHP files."""
        # Use statements
        for m in re.finditer(r'^\s*use\s+([\w\\]+)', content, re.MULTILINE):
            analysis.imports.append(ImportInfo(source=m.group(1).replace("\\", "/")))

        # Classes, interfaces, traits
        for m in re.finditer(
            r'^[ \t]*(?:(?:abstract|final)\s+)?(class|interface|trait|enum)\s+(\w+)'
            r'(?:\s+extends\s+(\w+))?(?:\s+implements\s+([\w,\s]+))?',
            content, re.MULTILINE
        ):
            kind = m.group(1)
            name = m.group(2)
            bases = [m.group(3)] if m.group(3) else []
            impls = [s.strip() for s in (m.group(4) or "").split(",") if s.strip()]
            analysis.classes.append(ClassInfo(name=name, kind=kind, bases=bases, implements=impls))

        # Functions
        for m in re.finditer(
            r'^[ \t]*(?:(?:public|private|protected)\s+)?(?:static\s+)?function\s+(\w+)\s*\(([^)]*)\)(?:\s*:\s*(\w+))?',
            content, re.MULTILINE
        ):
            analysis.functions.append(FunctionInfo(
                name=m.group(1),
                parameters=RegexAnalyzer._clean_params(m.group(2).strip()),
                return_type=m.group(3) or "",
            ))

    # -- Swift --

    @staticmethod
    def _analyze_swift(content: str, analysis: FileAnalysis) -> None:
        """Extract structure from Swift files."""
        # Imports
        for m in re.finditer(r'^\s*import\s+(\w+)', content, re.MULTILINE):
            analysis.imports.append(ImportInfo(source=m.group(1)))

        # Classes, structs, enums, protocols
        for m in re.finditer(
            r'^[ \t]*(?:(?:public|private|internal|open|fileprivate)\s+)?'
            r'(?:final\s+)?(class|struct|enum|protocol|actor)\s+(\w+)'
            r'(?:\s*:\s*([\w,\s]+))?',
            content, re.MULTILINE
        ):
            kind = m.group(1)
            name = m.group(2)
            parents = [s.strip() for s in (m.group(3) or "").split(",") if s.strip()]
            analysis.classes.append(ClassInfo(name=name, kind=kind, bases=parents))

        # Functions
        for m in re.finditer(
            r'^[ \t]*(?:(?:public|private|internal|open|fileprivate)\s+)?'
            r'(?:(?:static|class|override|mutating)\s+)?func\s+(\w+)\s*\(([^)]*)\)'
            r'(?:\s*(?:throws\s+)?->\s*(.+?))?(?:\s*\{)',
            content, re.MULTILINE
        ):
            analysis.functions.append(FunctionInfo(
                name=m.group(1),
                parameters=RegexAnalyzer._clean_params(m.group(2).strip()),
                return_type=(m.group(3) or "").strip(),
                is_static="static" in content[max(0, m.start() - 20):m.start()],
            ))

    # -- C/C++ --

    @staticmethod
    def _analyze_c_cpp(content: str, analysis: FileAnalysis) -> None:
        """Extract structure from C/C++ files."""
        # Includes
        for m in re.finditer(r'^\s*#include\s+[<"](.+?)[>"]', content, re.MULTILINE):
            source = m.group(1)
            is_local = '"' in content[m.start():m.end()]
            analysis.imports.append(ImportInfo(source=source, is_local=is_local))

        # Classes/structs
        for m in re.finditer(
            r'^[ \t]*(class|struct)\s+(\w+)(?:\s*:\s*(?:public|private|protected)\s+(\w+))?',
            content, re.MULTILINE
        ):
            kind = m.group(1)
            name = m.group(2)
            bases = [m.group(3)] if m.group(3) else []
            analysis.classes.append(ClassInfo(name=name, kind=kind, bases=bases))

        # Enums
        for m in re.finditer(r'^[ \t]*enum\s+(?:class\s+)?(\w+)', content, re.MULTILINE):
            analysis.classes.append(ClassInfo(name=m.group(1), kind="enum"))

        # Namespaces (treat as structural markers)
        for m in re.finditer(r'^[ \t]*namespace\s+(\w+)', content, re.MULTILINE):
            analysis.classes.append(ClassInfo(name=m.group(1), kind="namespace"))

        # Functions (simplified - top-level only)
        for m in re.finditer(
            r'^(\w[\w:*&<>\s]+?)\s+(\w+)\s*\(([^)]*)\)\s*(?:const\s*)?(?:override\s*)?(?:noexcept\s*)?(?:\{|;)',
            content, re.MULTILINE
        ):
            ret = m.group(1).strip()
            name = m.group(2)
            params = m.group(3).strip()
            if name in ("if", "for", "while", "switch", "catch", "return", "sizeof", "typeof", "alignof"):
                continue
            if ret in ("class", "struct", "enum", "namespace", "typedef", "using", "template"):
                continue
            analysis.functions.append(FunctionInfo(
                name=name,
                parameters=RegexAnalyzer._clean_params(params),
                return_type=ret,
            ))

        # Defines as constants
        for m in re.finditer(r'^\s*#define\s+([A-Z][A-Z0-9_]+)\s', content, re.MULTILINE):
            analysis.constants.append(VariableInfo(name=m.group(1), is_constant=True))

    # -- Scala --

    @staticmethod
    def _analyze_scala(content: str, analysis: FileAnalysis) -> None:
        """Extract structure from Scala files."""
        for m in re.finditer(r'^\s*import\s+([\w.{}]+)', content, re.MULTILINE):
            analysis.imports.append(ImportInfo(source=m.group(1)))

        for m in re.finditer(
            r'^[ \t]*(?:(?:abstract|sealed|final|case)\s+)*(class|trait|object|enum)\s+(\w+)'
            r'(?:\s+extends\s+(\w+))?',
            content, re.MULTILINE
        ):
            analysis.classes.append(ClassInfo(
                name=m.group(2), kind=m.group(1),
                bases=[m.group(3)] if m.group(3) else [],
            ))

        for m in re.finditer(
            r'^[ \t]*def\s+(\w+)\s*(?:\[.*?\])?\s*\(([^)]*)\)\s*(?::\s*(\w+))?',
            content, re.MULTILINE
        ):
            analysis.functions.append(FunctionInfo(
                name=m.group(1),
                parameters=RegexAnalyzer._clean_params(m.group(2).strip()),
                return_type=m.group(3) or "",
            ))

    # -- Dart --

    @staticmethod
    def _analyze_dart(content: str, analysis: FileAnalysis) -> None:
        """Extract structure from Dart files."""
        for m in re.finditer(r'''^\s*import\s+['"](.+?)['"]''', content, re.MULTILINE):
            analysis.imports.append(ImportInfo(source=m.group(1)))

        for m in re.finditer(
            r'^[ \t]*(?:abstract\s+)?(class|mixin|enum|extension)\s+(\w+)'
            r'(?:\s+extends\s+(\w+))?(?:\s+(?:with|implements)\s+([\w,\s]+))?',
            content, re.MULTILINE
        ):
            analysis.classes.append(ClassInfo(
                name=m.group(2), kind=m.group(1),
                bases=[m.group(3)] if m.group(3) else [],
                implements=[s.strip() for s in (m.group(4) or "").split(",") if s.strip()],
            ))

        for m in re.finditer(
            r'^[ \t]*(?:static\s+)?(?:Future<)?(\w+)>?\s+(\w+)\s*\(([^)]*)\)',
            content, re.MULTILINE
        ):
            name = m.group(2)
            if name in ("if", "for", "while", "switch", "catch", "return"):
                continue
            analysis.functions.append(FunctionInfo(
                name=name,
                parameters=RegexAnalyzer._clean_params(m.group(3).strip()),
                return_type=m.group(1),
                is_async="async" in content[m.end():m.end() + 20],
            ))

    # -- Elixir --

    @staticmethod
    def _analyze_elixir(content: str, analysis: FileAnalysis) -> None:
        """Extract structure from Elixir files."""
        for m in re.finditer(r'^[ \t]*defmodule\s+([\w.]+)', content, re.MULTILINE):
            analysis.classes.append(ClassInfo(name=m.group(1), kind="module"))

        for m in re.finditer(r'^[ \t]*(?:def|defp)\s+(\w+)\s*\(([^)]*)\)', content, re.MULTILINE):
            is_private = "defp" in content[m.start():m.start() + 10]
            analysis.functions.append(FunctionInfo(
                name=m.group(1),
                parameters=m.group(2).strip(),
                is_private=is_private,
            ))

    # -- Lua --

    @staticmethod
    def _analyze_lua(content: str, analysis: FileAnalysis) -> None:
        """Extract structure from Lua files."""
        for m in re.finditer(r'''^\s*(?:local\s+)?require\s*\(?['"]([\w.]+)['"]\)?''', content, re.MULTILINE):
            analysis.imports.append(ImportInfo(source=m.group(1)))

        for m in re.finditer(r'^[ \t]*(?:local\s+)?function\s+([\w.:]+)\s*\(([^)]*)\)', content, re.MULTILINE):
            name = m.group(1)
            analysis.functions.append(FunctionInfo(
                name=name,
                parameters=m.group(2).strip(),
                is_private=name.startswith("_") or "local" in content[max(0, m.start() - 10):m.start()],
            ))

    # -- Zig --

    @staticmethod
    def _analyze_zig(content: str, analysis: FileAnalysis) -> None:
        """Extract structure from Zig files."""
        for m in re.finditer(r'@import\s*\(\s*"(.+?)"\s*\)', content):
            analysis.imports.append(ImportInfo(source=m.group(1)))

        for m in re.finditer(
            r'^[ \t]*(?:pub\s+)?fn\s+(\w+)\s*\(([^)]*)\)\s*(.+?)\s*\{',
            content, re.MULTILINE
        ):
            name = m.group(1)
            params = m.group(2).strip()
            ret = m.group(3).strip()
            is_pub = "pub" in content[max(0, m.start() - 10):m.start()]
            analysis.functions.append(FunctionInfo(
                name=name,
                parameters=RegexAnalyzer._clean_params(params),
                return_type=ret,
                is_private=not is_pub,
            ))

        for m in re.finditer(r'^[ \t]*(?:pub\s+)?const\s+(\w+)\s*=\s*(?:packed\s+)?struct', content, re.MULTILINE):
            analysis.classes.append(ClassInfo(name=m.group(1), kind="struct"))

    # -- Shell --

    @staticmethod
    def _analyze_shell(content: str, analysis: FileAnalysis) -> None:
        """Extract structure from shell scripts."""
        for m in re.finditer(r'^[ \t]*(?:function\s+)?(\w+)\s*\(\s*\)', content, re.MULTILINE):
            analysis.functions.append(FunctionInfo(name=m.group(1)))

        if re.search(r'^#!/', content):
            analysis.has_entry_point = True

    # -- PowerShell --

    @staticmethod
    def _analyze_powershell(content: str, analysis: FileAnalysis) -> None:
        """Extract structure from PowerShell files."""
        for m in re.finditer(r'^[ \t]*function\s+([\w-]+)', content, re.MULTILINE):
            analysis.functions.append(FunctionInfo(name=m.group(1)))

        for m in re.finditer(r'^[ \t]*class\s+(\w+)(?:\s*:\s*(\w+))?', content, re.MULTILINE):
            analysis.classes.append(ClassInfo(
                name=m.group(1), kind="class",
                bases=[m.group(2)] if m.group(2) else [],
            ))

    # -- R --

    @staticmethod
    def _analyze_r(content: str, analysis: FileAnalysis) -> None:
        """Extract structure from R files."""
        for m in re.finditer(r'''^\s*(?:library|require)\s*\(\s*['"]?(\w+)['"]?\s*\)''', content, re.MULTILINE):
            analysis.imports.append(ImportInfo(source=m.group(1)))

        for m in re.finditer(r'^(\w+)\s*<-\s*function\s*\(([^)]*)\)', content, re.MULTILINE):
            analysis.functions.append(FunctionInfo(
                name=m.group(1), parameters=m.group(2).strip(),
            ))

    # -- Julia --

    @staticmethod
    def _analyze_julia(content: str, analysis: FileAnalysis) -> None:
        """Extract structure from Julia files."""
        for m in re.finditer(r'^\s*(?:using|import)\s+([\w.]+)', content, re.MULTILINE):
            analysis.imports.append(ImportInfo(source=m.group(1)))

        for m in re.finditer(r'^[ \t]*(?:mutable\s+)?struct\s+(\w+)', content, re.MULTILINE):
            analysis.classes.append(ClassInfo(name=m.group(1), kind="struct"))

        for m in re.finditer(r'^[ \t]*function\s+(\w+)\s*\(([^)]*)\)', content, re.MULTILINE):
            analysis.functions.append(FunctionInfo(
                name=m.group(1), parameters=m.group(2).strip(),
            ))

    # -- Generic fallback --

    @staticmethod
    def _analyze_generic(content: str, analysis: FileAnalysis) -> None:
        """Generic fallback: extract whatever we can from any language."""
        # Try common patterns
        for m in re.finditer(r'^[ \t]*(?:class|struct|interface|enum)\s+(\w+)', content, re.MULTILINE):
            analysis.classes.append(ClassInfo(name=m.group(1)))

        for m in re.finditer(r'^[ \t]*(?:def|func|function|fn|fun)\s+(\w+)\s*\(([^)]*)\)', content, re.MULTILINE):
            analysis.functions.append(FunctionInfo(
                name=m.group(1), parameters=m.group(2).strip(),
            ))

    # -- Helpers --

    @staticmethod
    def _extract_brace_block(content: str, start: int) -> Optional[str]:
        """Extract content between matching braces starting from a position."""
        idx = content.find("{", start)
        if idx == -1:
            return None
        depth = 1
        i = idx + 1
        while i < len(content) and depth > 0:
            if content[i] == "{":
                depth += 1
            elif content[i] == "}":
                depth -= 1
            i += 1
        return content[idx + 1:i - 1] if depth == 0 else None

    @staticmethod
    def _clean_params(params: str) -> str:
        """Clean up parameter strings for display."""
        if not params:
            return ""
        # Collapse whitespace
        params = re.sub(r'\s+', ' ', params).strip()
        # Truncate if very long
        if len(params) > 120:
            params = params[:117] + "..."
        return params

    @staticmethod
    def _detect_entry_point(content: str, language: str) -> bool:
        """Detect if a file contains an entry point."""
        patterns = {
            "javascript": [r'''if\s*\(\s*require\.main\s*===\s*module\s*\)'''],
            "typescript": [r'''if\s*\(\s*require\.main\s*===\s*module\s*\)'''],
            "go": [r'^func\s+main\s*\('],
            "rust": [r'^fn\s+main\s*\('],
            "java": [r'public\s+static\s+void\s+main\s*\('],
            "kotlin": [r'^fun\s+main\s*\('],
            "csharp": [r'static\s+(?:async\s+)?(?:Task|void)\s+Main\s*\('],
            "dart": [r'^void\s+main\s*\('],
            "swift": [r'@main'],
            "c": [r'^(?:int|void)\s+main\s*\('],
            "cpp": [r'^(?:int|void)\s+main\s*\('],
        }
        for pat in patterns.get(language, []):
            if re.search(pat, content, re.MULTILINE):
                return True
        return False


# ============================================================================
# Codebase Analyzer
# ============================================================================

class CodebaseAnalyzer:
    """Walk and analyze an entire codebase."""

    def __init__(self, root_path: str, max_files: int = 5000, max_depth: int = 8):
        self.root = Path(root_path).resolve()
        self.max_files = max_files
        self.max_depth = max_depth
        self.files: List[FileAnalysis] = []
        self.file_tree: Dict = {}
        self.all_paths: List[str] = []
        self.languages_found: Dict[str, int] = defaultdict(int)
        self.gitignore_patterns: List[str] = []

    def analyze(self) -> None:
        """Analyze the entire codebase."""
        self._load_gitignore()
        self._walk_and_analyze()

    def _load_gitignore(self) -> None:
        """Load .gitignore patterns from root."""
        gitignore = self.root / ".gitignore"
        if gitignore.exists():
            try:
                for line in gitignore.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        self.gitignore_patterns.append(line)
            except Exception:
                pass

        # Also check .codemapignore
        codemapignore = self.root / ".codemapignore"
        if codemapignore.exists():
            try:
                for line in codemapignore.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        self.gitignore_patterns.append(line)
            except Exception:
                pass

    def _should_skip(self, path: Path, is_dir: bool) -> bool:
        """Check if a path should be skipped."""
        name = path.name

        # Skip hidden files/dirs (except .github)
        if name.startswith(".") and name not in {".github"}:
            return True

        if is_dir:
            if name in DEFAULT_DIR_EXCLUDES:
                return True
        else:
            for pattern in DEFAULT_FILE_EXCLUDES:
                if fnmatch(name, pattern):
                    return True

            # Check file extension for binary
            ext = path.suffix.lower()
            if ext in BINARY_EXTENSIONS:
                return True

        # Check gitignore patterns
        try:
            rel = path.relative_to(self.root).as_posix()
        except ValueError:
            return True

        for pattern in self.gitignore_patterns:
            pat = pattern.rstrip("/")
            if fnmatch(name, pat) or fnmatch(rel, pat):
                return True
            if pattern.endswith("/") and is_dir and fnmatch(name, pat):
                return True

        return False

    def _walk_and_analyze(self) -> None:
        """Walk the directory tree and analyze source files."""
        count = 0

        for dirpath, dirnames, filenames in os.walk(self.root):
            d = Path(dirpath)

            # Prune excluded directories
            dirnames[:] = [
                dn for dn in dirnames
                if not self._should_skip(d / dn, is_dir=True)
            ]

            for fn in sorted(filenames):
                fp = d / fn
                if self._should_skip(fp, is_dir=False):
                    continue

                try:
                    rel_path = fp.relative_to(self.root).as_posix()
                except ValueError:
                    continue

                self.all_paths.append(rel_path)
                self._add_to_tree(rel_path)

                # Only analyze source files
                ext = fp.suffix.lower()
                language = LANG_MAP.get(ext)

                if language:
                    self.languages_found[language] += 1

                    if language == "python":
                        analysis = PythonAnalyzer.analyze(fp, rel_path)
                    else:
                        analysis = RegexAnalyzer.analyze(fp, rel_path, language)

                    if analysis:
                        self.files.append(analysis)

                count += 1
                if count >= self.max_files:
                    return

    def _add_to_tree(self, rel_path: str) -> None:
        """Add a file path to the tree structure."""
        parts = rel_path.split("/")
        current = self.file_tree
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[parts[-1]] = None


# ============================================================================
# Documentation Generator
# ============================================================================

class DocumentationGenerator:
    """Generate LLM-optimized markdown documentation."""

    def __init__(self, analyzer: CodebaseAnalyzer, project_name: str = ""):
        self.analyzer = analyzer
        self.project_name = project_name or analyzer.root.name

    @staticmethod
    def _matches_category(path_lower: str, keywords: List[str]) -> bool:
        """Check if a path matches category keywords using path segment matching.

        Splits the path into segments (directories and filename stem) and checks
        if any keyword matches a segment. Uses exact match for short keywords
        and prefix match for longer ones (>=4 chars) to handle plurals naturally.
        This avoids false matches like 'orm' in 'format'.
        """
        parts = path_lower.replace("\\", "/").split("/")
        filename = parts[-1] if parts else ""
        stem = filename.rsplit(".", 1)[0] if "." in filename else filename
        segments = parts[:-1] + re.split(r'[_\-./]', stem)
        segments = [s for s in segments if s]

        for keyword in keywords:
            for seg in segments:
                if seg == keyword:
                    return True
                # For keywords with 4+ chars, allow prefix matching (handles plurals)
                if len(keyword) >= 4 and seg.startswith(keyword):
                    return True
        return False

    def generate(self) -> str:
        """Generate the complete documentation."""
        sections = [
            self._generate_header(),
            self._generate_summary(),
            self._generate_quick_nav(),
            self._generate_entry_points(),
            self._generate_task_guide(),
            self._generate_import_deps(),
            self._generate_file_tree(),
            self._generate_class_hierarchy(),
            self._generate_code_outline(),
        ]
        return "\n\n".join(filter(None, sections))

    def _generate_header(self) -> str:
        """Generate document header."""
        return f"""# {self.project_name} - Code Structure Documentation

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Optimized for:** LLM consumption (Claude, Cursor, Copilot, etc.)

---"""

    def _generate_summary(self) -> str:
        """Generate codebase summary with LLM-relevant stats."""
        total_source_files = len(self.analyzer.files)
        total_all_files = len(self.analyzer.all_paths)
        total_classes = sum(len(f.classes) for f in self.analyzer.files)
        total_methods = sum(
            len(c.methods) for f in self.analyzer.files for c in f.classes
        )
        total_functions = sum(len(f.functions) for f in self.analyzer.files)
        total_loc = sum(f.line_count for f in self.analyzer.files)
        estimated_tokens = total_loc * 12  # ~12 tokens per line average

        langs = sorted(self.analyzer.languages_found.keys())
        lang_str = ", ".join(f"{l} ({self.analyzer.languages_found[l]})" for l in langs)

        # Estimate this doc's token count
        doc_tokens = (total_source_files * 150) // 4

        lines = [
            "## Codebase Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total Files | {total_all_files} |",
            f"| Source Files Analyzed | {total_source_files} |",
            f"| Languages | {lang_str or 'N/A'} |",
            f"| Classes/Structs/Interfaces | {total_classes} |",
            f"| Methods | {total_methods} |",
            f"| Functions | {total_functions} |",
            f"| ~Lines of Code | {total_loc:,} |",
            f"| ~Full Codebase Tokens | {estimated_tokens:,} |",
            "",
            "**LLM Usage Note:**",
            f"- This navigation map is ~{doc_tokens:,} tokens",
            "- Include it in every session to avoid expensive codebase searches",
            "",
            "---",
        ]
        return "\n".join(lines)

    def _generate_quick_nav(self) -> str:
        """Generate categorized quick navigation."""
        lines = [
            "## Quick Navigation",
            "",
            "*Use this section to locate files by functionality*",
            "",
        ]

        categorized_files: Dict[str, List[Tuple[str, str]]] = {}

        for file_info in self.analyzer.files:
            path_lower = file_info.path.lower()
            matched = False
            for category, keywords in CATEGORIES.items():
                if self._matches_category(path_lower, keywords):
                    if category not in categorized_files:
                        categorized_files[category] = []
                    desc = file_info.doc_comment
                    if desc and len(desc) > 70:
                        desc = desc[:67] + "..."
                    categorized_files[category].append((file_info.path, desc))
                    matched = True
                    break  # Only first category match

            if not matched and (file_info.classes or file_info.functions):
                cat = "Other"
                if cat not in categorized_files:
                    categorized_files[cat] = []
                categorized_files[cat].append((file_info.path, file_info.doc_comment))

        # Sort categories by relevance (defined order)
        category_order = list(CATEGORIES.keys()) + ["Other"]
        for category in category_order:
            if category in categorized_files:
                lines.append(f"### {category}")
                lines.append("")
                for path, desc in sorted(categorized_files[category]):
                    if desc:
                        lines.append(f"- `{path}` - {desc}")
                    else:
                        lines.append(f"- `{path}`")
                lines.append("")

        return "\n".join(lines)

    def _generate_entry_points(self) -> str:
        """Generate entry points section."""
        lines = [
            "## Entry Points",
            "",
            "*Where does execution start? Look here first.*",
            "",
        ]

        # Files that match entrypoint patterns
        pattern_entries = []
        for file_info in self.analyzer.files:
            path = file_info.path
            filename = Path(path).name
            for pattern in ENTRYPOINT_PATTERNS:
                if fnmatch(path, pattern) or fnmatch(filename, pattern):
                    desc = file_info.doc_comment
                    pattern_entries.append((path, desc))
                    break

        # Files with detected entry points (main functions, etc.)
        entry_point_files = [
            f for f in self.analyzer.files if f.has_entry_point
            and f.path not in [p for p, _ in pattern_entries]
        ]

        if pattern_entries or entry_point_files:
            lines.append("### Executable Entry Points")
            lines.append("")
            for path, desc in sorted(set(pattern_entries)):
                lines.append(f"- `{path}`{' - ' + desc if desc else ''}")
            for f in sorted(entry_point_files, key=lambda x: x.path):
                lines.append(f"- `{f.path}`{' - ' + f.doc_comment if f.doc_comment else ''}")
            lines.append("")

        # Key entry functions/methods
        main_functions = []
        for file_info in self.analyzer.files:
            for func in file_info.functions:
                if func.name in ENTRY_FUNCTION_NAMES:
                    main_functions.append((file_info.path, func.name, "function"))
            for cls in file_info.classes:
                for method in cls.methods:
                    if method.name in ENTRY_FUNCTION_NAMES:
                        main_functions.append(
                            (file_info.path, f"{cls.name}.{method.name}", "method")
                        )

        if main_functions:
            lines.append("### Key Entry Functions/Methods")
            lines.append("")
            for path, name, typ in sorted(set(main_functions)):
                lines.append(f"- `{path}::{name}()` ({typ})")
            lines.append("")

        return "\n".join(lines)

    def _generate_task_guide(self) -> str:
        """Generate task-oriented navigation guide."""
        # Only include guidance for categories that actually exist
        categorized = set()
        for file_info in self.analyzer.files:
            path_lower = file_info.path.lower()
            for category, keywords in CATEGORIES.items():
                if self._matches_category(path_lower, keywords):
                    categorized.add(category)

        if not categorized:
            return ""

        lines = [
            "## Common Tasks -> Where to Look",
            "",
        ]

        task_guidance = {
            "Authentication & Authorization": (
                "To modify authentication/login",
                'Check "Authentication & Authorization" above. '
                "Look for functions like `login()`, `authenticate()`, `validateToken()`.",
            ),
            "API/Endpoints/Routes": (
                "To add/modify API endpoints",
                'Check "API/Endpoints/Routes" above. '
                "Look for route decorators, handler functions, or controller methods.",
            ),
            "Database/Models/ORM": (
                "To modify database schema/models",
                'Check "Database/Models/ORM" above. '
                "Look for model classes, migration files, or schema definitions.",
            ),
            "Services/Business Logic": (
                "To modify business logic",
                'Check "Services/Business Logic" above. '
                "Look for service classes and their public methods.",
            ),
            "UI/Components": (
                "To modify UI components",
                'Check "UI/Components" above. '
                "Look for component files matching the feature you need to change.",
            ),
            "State Management": (
                "To modify application state",
                'Check "State Management" above. '
                "Look for store definitions, reducers, or state slices.",
            ),
            "Configuration/Settings": (
                "To adjust configuration",
                'Check "Configuration/Settings" above. '
                "Look for config files, environment variable definitions, or constants.",
            ),
            "Utilities/Helpers": (
                "To add new utilities",
                'Check "Utilities/Helpers" above. '
                "Add to existing utility modules or create new ones following project conventions.",
            ),
            "Tests": (
                "To add/modify tests",
                'Check "Tests" above. '
                "Follow existing test patterns and naming conventions.",
            ),
        }

        for category, (task, guidance) in task_guidance.items():
            if category in categorized:
                lines.append(f"**{task}:**")
                lines.append(f"- {guidance}")
                lines.append("")

        lines.append("---")
        return "\n".join(lines)

    def _generate_import_deps(self) -> str:
        """Generate import dependency graph for local imports."""
        lines = [
            "## Import Dependencies",
            "",
            "*Local imports show data flow between modules*",
            "",
        ]

        has_deps = False
        for file_info in sorted(self.analyzer.files, key=lambda x: x.path):
            local_imports = [imp for imp in file_info.imports if imp.is_local]
            if local_imports:
                has_deps = True
                lines.append(f"### `{file_info.path}`")
                lines.append("")
                for imp in local_imports:
                    names = f" ({', '.join(imp.names)})" if imp.names else ""
                    lines.append(f"- {imp.source}{names}")
                lines.append("")

        if not has_deps:
            return ""

        return "\n".join(lines)

    def _generate_file_tree(self) -> str:
        """Generate visual file tree."""
        def sort_key(name: str) -> Tuple[int, str]:
            n = name.lower()
            if n.startswith("__"): return (0, n)
            if n.startswith("_"): return (1, n)
            if n and n[0].isdigit(): return (2, n)
            return (3, n)

        def build_tree(d: Dict, indent: str = "", depth: int = 0) -> List[str]:
            if depth >= self.analyzer.max_depth:
                return [f"{indent}..."]

            # Separate folders and files
            folders = [(n, v) for n, v in d.items() if v is not None]
            files = [(n, v) for n, v in d.items() if v is None]

            folders.sort(key=lambda x: sort_key(x[0]))
            files.sort(key=lambda x: sort_key(x[0]))

            items = folders + files
            result = []

            for i, (name, subdir) in enumerate(items):
                is_last = i == len(items) - 1
                prefix = "└── " if is_last else "├── "
                result.append(f"{indent}{prefix}{name}")
                if subdir is not None:
                    next_indent = indent + ("    " if is_last else "│   ")
                    result.extend(build_tree(subdir, next_indent, depth + 1))

            return result

        tree_lines = build_tree(self.analyzer.file_tree)

        lines = [
            "## Project Structure",
            "",
            "```",
            f"{self.analyzer.root.name}/",
        ]
        lines.extend(tree_lines)
        lines.append("```")

        return "\n".join(lines)

    def _generate_class_hierarchy(self) -> str:
        """Generate class inheritance hierarchy."""
        all_classes: Dict[str, Tuple[str, ClassInfo]] = {}
        inheritance: Dict[str, List[str]] = defaultdict(list)

        for file_info in self.analyzer.files:
            for cls in file_info.classes:
                if cls.kind in ("class", "struct", "trait", "interface", "protocol", "actor"):
                    all_classes[cls.name] = (file_info.path, cls)
                    for base in cls.bases:
                        inheritance[base].append(cls.name)

        if not all_classes:
            return ""

        # Only show hierarchy if there are inheritance relationships
        has_hierarchy = any(
            cls.bases and any(b in all_classes for b in cls.bases)
            for _, cls in all_classes.values()
        )
        if not has_hierarchy:
            return ""

        lines = [
            "## Class Hierarchy",
            "",
            "```",
        ]

        # Find root classes (no parent in our codebase)
        roots = []
        for cls_name in all_classes:
            _, cls = all_classes[cls_name]
            if not cls.bases or not any(b in all_classes for b in cls.bases):
                roots.append(cls_name)

        def build_hierarchy(cls_name: str, indent: str = "") -> List[str]:
            result = [f"{indent}{cls_name}"]
            if cls_name in inheritance:
                children = sorted(c for c in inheritance[cls_name] if c in all_classes)
                for child in children:
                    result.extend(build_hierarchy(child, indent + "  ├── "))
            return result

        for root in sorted(roots):
            for line in build_hierarchy(root):
                lines.append(line)

        lines.append("```")
        return "\n".join(lines)

    def _generate_code_outline(self) -> str:
        """Generate detailed code outline for each file."""
        lines = [
            "## Detailed Code Outline",
            "",
        ]

        # Legend
        lines.extend([
            "**Legend:** "
            "[C] class  [I] interface  [S] struct  [E] enum  [T] trait/type  "
            "[F] function  [A] async  [M] method  [P] property  "
            "[K] constant  [v] variable",
            "",
        ])

        for file_info in sorted(self.analyzer.files, key=lambda x: x.path):
            if not (file_info.classes or file_info.functions or file_info.constants):
                continue

            lines.append(f"### `{file_info.path}`")
            lines.append("")

            # Tags
            tags = self._generate_tags(file_info)
            if tags:
                lines.append(f"*Tags: {', '.join(tags)}*")
                lines.append("")

            lines.append("```")

            # Constants
            for const in file_info.constants:
                type_str = f": {const.type_hint}" if const.type_hint else ""
                lines.append(f"[K] {const.name}{type_str}")

            # Top-level functions
            for func in file_info.functions:
                lines.append(self._format_function(func, indent=""))

            # Classes
            for cls in file_info.classes:
                kind_marker = {
                    "class": "[C]", "interface": "[I]", "struct": "[S]",
                    "enum": "[E]", "trait": "[T]", "type": "[T]",
                    "module": "[C]", "object": "[C]", "protocol": "[I]",
                    "actor": "[C]", "mixin": "[C]", "namespace": "[C]",
                    "annotation": "[E]",
                }.get(cls.kind, "[C]")

                bases_str = ""
                if cls.bases:
                    bases_str = f"({', '.join(cls.bases)})"
                elif cls.implements:
                    bases_str = f" -> {', '.join(cls.implements)}"

                lines.append(f"{kind_marker} {cls.name}{bases_str}")

                # Variables/fields
                for var in cls.variables:
                    type_str = f": {var.type_hint}" if var.type_hint else ""
                    marker = "[K]" if var.is_constant else "[v]"
                    lines.append(f"  {marker} {var.name}{type_str}")

                # Methods
                for method in cls.methods:
                    lines.append(self._format_function(method, indent="  "))

            lines.append("```")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _format_function(func: FunctionInfo, indent: str = "") -> str:
        """Format a function/method for the outline."""
        # Determine marker
        if func.is_property:
            marker = "[P]"
        elif func.is_constructor:
            marker = "[M]"
        elif func.is_static:
            marker = "[s]"
        elif func.is_async:
            marker = "[A]"
        elif func.is_private:
            marker = "[m]"
        else:
            if indent:  # It's a method
                marker = "[M]"
            else:  # It's a function
                marker = "[A]" if func.is_async else "[F]"

        params = f"({func.parameters})" if func.parameters else "()"
        ret = f" -> {func.return_type}" if func.return_type else ""

        return f"{indent}{marker} {func.name}{params}{ret}"

    @staticmethod
    def _generate_tags(file_info: FileAnalysis) -> List[str]:
        """Generate searchable tags for a file."""
        tags = []
        path_lower = file_info.path.lower()

        tag_patterns = {
            "authentication": ["auth", "login", "session"],
            "api": ["api", "endpoint", "route"],
            "database": ["db", "database", "model", "migration"],
            "config": ["config", "settings"],
            "utility": ["util", "helper"],
            "test": ["test", "spec"],
            "middleware": ["middleware"],
            "service": ["service"],
            "component": ["component", "widget"],
        }

        for tag, keywords in tag_patterns.items():
            if DocumentationGenerator._matches_category(path_lower, keywords):
                tags.append(tag)

        if file_info.has_entry_point:
            tags.append("entry-point")

        return tags


# ============================================================================
# CLI
# ============================================================================

def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    p = argparse.ArgumentParser(
        description="CodeMap - Generate LLM-optimized code structure documentation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python codemap.py                           Analyze current directory
  python codemap.py --root /path/to/project   Analyze specific project
  python codemap.py --out CODEMAP.md          Custom output filename
  python codemap.py --no-outline              Skip detailed code outline
  python codemap.py --max-depth 10            Deeper tree rendering
  python codemap.py --name "My Project"       Custom project name
        """,
    )
    p.add_argument("--root", type=str, default=".", help="Repository root directory (default: current dir)")
    p.add_argument("--out", type=str, default="CODEBASE_STRUCTURE.md", help="Output filename (default: CODEBASE_STRUCTURE.md)")
    p.add_argument("--name", type=str, default="", help="Project name (default: directory name)")
    p.add_argument("--max-depth", type=int, default=8, help="Max tree depth (default: 8)")
    p.add_argument("--max-files", type=int, default=5000, help="Max files to index (default: 5000)")
    p.add_argument("--no-outline", action="store_true", help="Skip detailed code outline section")
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Main entry point."""
    args = parse_args(argv)
    if args.root != ".":
        root = Path(args.root).resolve()
    else:
        # Default to git repository root
        try:
            import subprocess
            git_root = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, check=True
            ).stdout.strip()
            root = Path(git_root).resolve()
        except (subprocess.CalledProcessError, FileNotFoundError):
            root = Path(".").resolve()

    if not root.exists() or not root.is_dir():
        print(f"Error: directory not found: {root}", file=sys.stderr)
        return 1

    print(f"Analyzing codebase: {root}")

    analyzer = CodebaseAnalyzer(
        root_path=str(root),
        max_files=max(1, args.max_files),
        max_depth=max(1, args.max_depth),
    )
    analyzer.analyze()

    print(f"Found {len(analyzer.files)} source files across {len(analyzer.languages_found)} languages")

    generator = DocumentationGenerator(analyzer, project_name=args.name)

    if args.no_outline:
        # Monkey-patch to skip outline
        generator._generate_code_outline = lambda: ""

    documentation = generator.generate()

    out_path = root / args.out
    try:
        out_path.write_text(documentation, encoding="utf-8")
    except Exception as e:
        print(f"Error writing output: {e}", file=sys.stderr)
        return 2

    print(f"Documentation saved to: {out_path}")
    print(f"Analyzed: {len(analyzer.files)} files, "
          f"{sum(len(f.classes) for f in analyzer.files)} classes, "
          f"{sum(len(f.functions) for f in analyzer.files)} functions")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())