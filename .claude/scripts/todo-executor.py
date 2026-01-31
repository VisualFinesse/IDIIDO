#!/usr/bin/env python3
"""
TODO Task Executor - Sequential execution with fresh context per task.

Agentic harness to allow a sequence of agent work with context handling, testing, and graceful failure.

USAGE:
    python .claude/scripts/todo_executor.py

OPTIONS:
    --todo-file FILE         Specific TODO file to process (default: project root TODO.md)
    --max-tasks N            Limit number of tasks to process (default: unlimited)
    --agent-select {claude,codex,router}
                             Select agent provider (default: claude).
                             - claude: run local Claude CLI
                             - codex: run local Codex CLI
                             - router: use internal openrouter_harness (model selection handled by harness)
    --skip-tests             Skip running tests during validation

    --agent-timeout N        Timeout for agent execution in seconds (default: 600)
    --mode {agent,ci}        Execution mode (agent spawns or CI/no-agent)
    --continue-on-failure    Continue to next task even if current one fails (batch mode)
    --max-retries N          Maximum retries per task before moving on (default: 3)
    --max-dod-attempts N     Maximum DoD remediation attempts per task (default: 3)
    --debug                 Enable debugpy listener (waits for attach on port 5678)

ENV:
    AGENT_FALLBACK_ORDER     Pipe/comma/space-separated agent order, e.g. "router | codex | claude"
                             If unset, defaults to: "router | codex | claude"
    OPENROUTER_API_KEY       Required for agent-select=router
    LLM_STREAM               If "1", stream router output tokens (default: "1")
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import dotenv
from dataclasses import dataclass
from pathlib import Path
from threading import Thread
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# Path bootstrap (works even when invoked from nested directories)
# ---------------------------------------------------------------------------

SCRIPTS_DIR = Path(__file__).resolve().parent
CLAUDE_DIR = SCRIPTS_DIR.parent
PROJECT_ROOT = CLAUDE_DIR.parent
EXEC_CWD = Path.cwd().resolve()

dotenv.load_dotenv()


def _ensure_import_paths() -> None:
    # Allow local imports (scripts) and .claude package imports
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    if str(CLAUDE_DIR) not in sys.path:
        sys.path.insert(0, str(CLAUDE_DIR))


_ensure_import_paths()

from todo_parser import (  # noqa: E402
    ensure_task_pending,
    get_next_pending_task,
    get_task_context,
    mark_task_complete,
    parse_todo_file,
)
from dod_validator import validate_task_completion  # noqa: E402

# openrouter_harness imports are optional at runtime (only needed when agent_select == router)
try:  # noqa: E402
    from openrouter_harness.models import load_config  # type: ignore
    from openrouter_harness.router import OpenRouterHarness  # type: ignore
    from openrouter_harness.telemetry import TelemetryWriter  # type: ignore
except Exception:  # pragma: no cover
    load_config = None  # type: ignore
    OpenRouterHarness = None  # type: ignore
    TelemetryWriter = None  # type: ignore


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------

DEFAULT_AGENT_FALLBACK_ORDER = "router | codex | claude"


def _which(cmd: str) -> Optional[str]:
    return shutil.which(cmd)


def _env_flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default) not in ("0", "", "false", "False", "FALSE")


def _truncate(s: str, n: int = 200) -> str:
    if s is None:
        return ""
    return s if len(s) <= n else (s[:n] + "...")


def _has_router_creds() -> bool:
    return bool(os.getenv("OPENROUTER_API_KEY"))


def _normalize_agent_name(name: str) -> Optional[str]:
    if not name:
        return None
    value = name.strip().lower()
    if value in ("claude", "codex", "router"):
        return value
    if value in ("openrouter", "openrouter_harness", "openrouter-harness"):
        return "router"
    return None


def _parse_agent_order(raw: Optional[str]) -> tuple[list[str], list[str]]:
    if not raw:
        return [], []
    parts = [p for p in re.split(r"[|,>]+", raw) if p.strip()]
    if len(parts) == 1 and " " in parts[0]:
        parts = [p for p in parts[0].split() if p.strip()]
    order: list[str] = []
    invalid: list[str] = []
    for part in parts:
        normalized = _normalize_agent_name(part)
        if normalized:
            if normalized not in order:
                order.append(normalized)
        else:
            invalid.append(part.strip())
    return order, invalid


def _resolve_default_todo_file(exec_cwd: Path, project_root: Path) -> Path:
    """
    Default behavior:
      - Prefer CWD TODO.md
      - If missing, fall back to CWD/scripts/TODO.md
      - If missing, prefer project root TODO.md
      - If missing, fall back to project root/scripts/TODO.md
    """
    cwd_todo = exec_cwd / "TODO.md"
    if cwd_todo.exists():
        return cwd_todo

    cwd_scripts_todo = exec_cwd / "scripts" / "TODO.md"
    if cwd_scripts_todo.exists():
        return cwd_scripts_todo

    root_todo = project_root / "TODO.md"
    if root_todo.exists():
        return root_todo

    root_scripts_todo = project_root / "scripts" / "TODO.md"
    if root_scripts_todo.exists():
        return root_scripts_todo

    # Still return the preferred location so error messages are stable.
    return cwd_todo


def _resolve_todo_file_arg(todo_file: str, exec_cwd: Path, project_root: Path) -> Path:
    """
    Resolve --todo-file with stable and intuitive semantics:
      - Absolute paths are used as-is.
      - Relative paths are resolved against the execution CWD first.
      - If not found in CWD, fall back to resolving against project root.
    """
    p = Path(todo_file)
    if p.is_absolute():
        return p.resolve()

    cand_cwd = (exec_cwd / p).resolve()
    if cand_cwd.exists():
        return cand_cwd

    return (project_root / p).resolve()


def _is_interactive() -> bool:
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


def _resolve_cli_command_for_windows(base: str) -> list[str]:
    """
    Prefer:
      - <base>.cmd if available (Node global shim)
      - <base> if it resolves to .exe/.cmd/.bat
      - If <base> resolves to .ps1, run it via powershell -File

    This allows users to pass `claude` / `codex` and have it “just work”.
    """
    base = (base or "").strip()
    candidates: list[str] = []
    if base:
        candidates.append(base)

    # If user typed 'claude' or 'codex', prefer .cmd on Windows.
    if base.lower() in ("claude", "codex"):
        candidates.insert(0, f"{base}.cmd")

    for cand in candidates:
        resolved = _which(cand)
        if not resolved:
            continue

        lower = resolved.lower()
        if lower.endswith(".ps1"):
            return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", resolved]
        return [resolved]

    # Last resort: let subprocess try it (may fail with FileNotFoundError).
    return [base] if base else []


def _stream_pipe_to(pipe, out_stream) -> None:
    try:
        for line in iter(pipe.readline, ""):
            if not line:
                break
            out_stream.write(line)
            out_stream.flush()
    except Exception:
        return


def _emit_claude_stream_json_lines(proc: subprocess.Popen) -> None:
    """
    Parse `claude -p --output-format stream-json` NDJSON and emit only human-readable text
    while preserving streaming behavior.
    """
    assert proc.stdout is not None
    buf = b""
    out = sys.stdout

    def write_text(s: str) -> None:
        if not s:
            return
        out.write(s)
        out.flush()

    def handle_obj(obj: dict) -> None:
        ev = obj.get("event") if isinstance(obj, dict) else None
        if isinstance(ev, dict):
            delta = ev.get("delta")
            if isinstance(delta, dict):
                txt = delta.get("text")
                if isinstance(txt, str) and txt:
                    write_text(txt)
                    return

        msg = obj.get("message")
        if isinstance(msg, dict):
            content = msg.get("content")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        txt = part.get("text")
                        if isinstance(txt, str) and txt:
                            write_text(txt)
                return

        res = obj.get("result")
        if isinstance(res, str) and res:
            write_text(res)

    while True:
        chunk = proc.stdout.read(4096)
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line.decode("utf-8", "replace"))
            except Exception:
                sys.stdout.buffer.write(line + b"\n")
                sys.stdout.buffer.flush()
                continue
            if isinstance(obj, dict):
                handle_obj(obj)


def _claude_headless_args() -> list[str]:
    return [
        "-p",
        "--output-format",
        "stream-json",
        "--include-partial-messages",
        "--verbose",
        "--allowedTools",
        "Read,Edit,Write,Replace,Glob,Grep,LS,Bash",
    ]


def _build_fallback_order(agent_select: str) -> list[str]:
    """
    Fallback order is driven only by AGENT_FALLBACK_ORDER (or DEFAULT_AGENT_FALLBACK_ORDER).
    agent_select is treated as the primary and is placed first; remaining agents keep env order.
    """
    raw = os.getenv("AGENT_FALLBACK_ORDER") or DEFAULT_AGENT_FALLBACK_ORDER
    order, invalid = _parse_agent_order(raw)
    if invalid:
        print(
            "Warning: ignoring unknown agent(s) in AGENT_FALLBACK_ORDER: " + ", ".join(invalid),
            file=sys.stderr,
        )
    if not order:
        order = [agent_select]
    if agent_select in order:
        order = [agent_select] + [a for a in order if a != agent_select]
    else:
        order = [agent_select] + order
    # de-dupe (preserve order)
    out: list[str] = []
    for a in order:
        if a not in out:
            out.append(a)
    return out


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExecutorPaths:
    project_root: Path
    claude_dir: Path
    codemap_path: Path
    models_config_path: Path
    telemetry_path: Path
    pre_prompt_hook_path: Path
    post_complete_hook_path: Path
    dod_path: Path

    @staticmethod
    def from_project_root(project_root: Path) -> "ExecutorPaths":
        claude_dir = project_root / ".claude"
        dod_path = claude_dir / "definition-of-done.md"
        if not dod_path.exists():
            alt = project_root / "docs" / "definition-of-done.md"
            if alt.exists():
                dod_path = alt
            else:
                alt2 = project_root / "definition-of-done.md"
                if alt2.exists():
                    dod_path = alt2
        return ExecutorPaths(
            project_root=project_root,
            claude_dir=claude_dir,
            codemap_path=claude_dir / "CODEMAP.md",
            models_config_path=claude_dir / "config" / "models.json",
            telemetry_path=claude_dir / "logs" / "llm_attempts.jsonl",
            pre_prompt_hook_path=claude_dir / "hooks" / "pre-prompt.py",
            post_complete_hook_path=claude_dir / "hooks" / "post-complete.py",
            dod_path=dod_path,
        )


class CountingTelemetryWriter:
    def __init__(self, writer: "TelemetryWriter", on_record: Callable) -> None:
        self.writer = writer
        self.on_record = on_record

    def write(self, record) -> None:
        self.writer.write(record)
        self.on_record(record)


# ---------------------------------------------------------------------------
# Agent runner
# ---------------------------------------------------------------------------

class AgentRunner:
    def __init__(
        self,
        paths: ExecutorPaths,
        agent_timeout: int,
        agent_select: str,
    ) -> None:
        self._paths = paths
        self._agent_timeout = agent_timeout
        self._agent_select = agent_select  # "claude" | "codex" | "router"

        self._router: Optional["OpenRouterHarness"] = None
        self._router_call_count = 0
        self._router_model_counts: dict[str, int] = {}
        self._router_summary_every = int(os.getenv("openrouter_harness_SUMMARY_EVERY", "0"))

    def _get_router(self) -> "OpenRouterHarness":
        if OpenRouterHarness is None or load_config is None or TelemetryWriter is None:  # type: ignore[misc]
            raise RuntimeError("openrouter_harness is not available (missing imports).")

        if self._router is None:
            config = load_config(self._paths.models_config_path)
            telemetry = TelemetryWriter(self._paths.telemetry_path)

            def on_record(record) -> None:
                model = getattr(record, "model", None)
                if model:
                    self._router_model_counts[model] = self._router_model_counts.get(model, 0) + 1

            self._router = OpenRouterHarness(
                config=config,
                telemetry=CountingTelemetryWriter(telemetry, on_record),
            )
        return self._router

    def _maybe_print_router_summary(self) -> None:
        self._router_call_count += 1
        if not self._router_summary_every:
            return
        if self._router_call_count % self._router_summary_every != 0:
            return
        summary = " ".join(
            f"{model}={count}" for model, count in sorted(self._router_model_counts.items())
        )
        if summary:
            print(
                f"[router-summary] calls={self._router_call_count} {summary}",
                file=sys.stderr,
                flush=True,
            )

    def build_task_prompt(
        self,
        task,
        hook_context: str = "",
        dod_text: str = "",
        previous_failure_context: str = "",
    ) -> str:
        codemap_content = ""
        if self._paths.codemap_path.exists():
            try:
                codemap_content = self._paths.codemap_path.read_text(encoding="utf-8")
            except Exception as e:
                codemap_content = f"[Error reading CODEMAP: {e}]"
        else:
            codemap_content = "[CODEMAP.md missing]"

        hook_block = f"\n## PRE-PROMPT HOOK CONTEXT\n\n{hook_context}\n" if hook_context else ""
        dod_block = (
            f"\n## DEFINITION OF DONE (read and follow before claiming done)\n\n{dod_text}\n"
            if dod_text
            else ""
        )
        failure_block = (
            f"\n## PREVIOUS FAILURE CONTEXT\n\n{previous_failure_context}\n"
            if previous_failure_context
            else ""
        )

        return f"""You are working on a TODO task. Complete the task and ensure all Definition of Done criteria are met.

## CODEBASE CONTEXT (from .claude/CODEMAP.md)

{codemap_content}
{hook_block}{dod_block}{failure_block}

## TASK TO COMPLETE

**Task**: {task.description}
**File**: {task.file_path}:{task.line_number}
**Section**: {task.section or 'N/A'}
**Parent**: {task.parent_task or 'N/A'}

## INSTRUCTIONS

1. Read the relevant source files to understand the current implementation.
2. Implement ONLY what the task describes.
3. Keep changes minimal and aligned with existing patterns.
4. Run tests with `pytest` (or the repo's test command).
5. Do NOT mark TODO items complete; the executor will update TODO.md after validation.

Begin working on the task now.
"""

    def _run_cli_agent(self, command: list[str], prompt: str) -> bool:
        print(f"\n--- Spawning agent via {' '.join(command)} (timeout: {self._agent_timeout}s) ---")
        print(f"    Prompt size: {len(prompt)} chars")
        print("    Starting process...")
        print("-" * 60)

        is_claude = (self._agent_select == "claude")

        start_time = time.time()
        try:
            if is_claude:
                proc = subprocess.Popen(
                    command,
                    cwd=str(self._paths.project_root),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=False,
                    bufsize=0,
                )
                assert proc.stdin is not None
                assert proc.stdout is not None

                proc.stdin.write(prompt.encode("utf-8", "replace"))
                proc.stdin.flush()
                proc.stdin.close()

                t_out = Thread(target=_emit_claude_stream_json_lines, args=(proc,), daemon=True)
                t_out.start()

                try:
                    rc = proc.wait(timeout=self._agent_timeout)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    print(f"\nError: agent timed out after {self._agent_timeout}s")
                    return False
            else:
                proc = subprocess.Popen(
                    command,
                    cwd=str(self._paths.project_root),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                )
                assert proc.stdin is not None
                assert proc.stdout is not None
                assert proc.stderr is not None

                t_out = Thread(target=_stream_pipe_to, args=(proc.stdout, sys.stdout), daemon=True)
                t_err = Thread(target=_stream_pipe_to, args=(proc.stderr, sys.stderr), daemon=True)
                t_out.start()
                t_err.start()

                proc.stdin.write(prompt)
                proc.stdin.write("\n")
                proc.stdin.flush()
                proc.stdin.close()

                try:
                    rc = proc.wait(timeout=self._agent_timeout)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    print(f"\nError: agent timed out after {self._agent_timeout}s")
                    return False

            elapsed = time.time() - start_time
            if rc != 0:
                print(f"\nError: agent exited with code {rc}")
                return False

            print(f"\nAgent completed in {elapsed:.1f}s")
            return True

        except FileNotFoundError:
            print(f"Error: command not found: {command[0]}")
            if os.name == "nt":
                print("  Windows hint: if PowerShell resolves `claude` to claude.ps1, use claude.cmd instead.")
            return False
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"Error spawning agent: {e}")
            return False

    def run(
        self,
        task,
        prompt: str,
        task_id_suffix: str = "",
    ) -> bool:
        task_id = task.metadata.get("task_id") or f"{Path(task.file_path).name}:{task.line_number}"
        if task_id_suffix:
            task_id = f"{task_id}:{task_id_suffix}"

        if self._agent_select in ("claude", "codex"):
            cmd = _resolve_cli_command_for_windows(self._agent_select)
            if not cmd:
                print(f"Error: invalid agent selection: {self._agent_select}")
                return False
            if self._agent_select == "claude":
                cmd = [*cmd, *_claude_headless_args()]
            return self._run_cli_agent(cmd, prompt)

        if self._agent_select != "router":
            print(f"Error: invalid --agent-select value: {self._agent_select}")
            return False

        if not _has_router_creds():
            print("Error: missing OpenRouter credentials in .env (OPENROUTER_API_KEY) for agent-select=router")
            return False

        router = self._get_router()
        stream_enabled = _env_flag("LLM_STREAM", "1")
        model_hint = ""
        try:
            if getattr(router, "config", None) and getattr(router.config, "models", None):
                model_hint = router.config.models[0]
        except Exception:
            model_hint = ""

        def on_token(token: str) -> None:
            sys.stdout.write(token)
            sys.stdout.flush()

        print(f"\n--- Spawning agent via router {self._router} (timeout: {self._agent_timeout}s) ---")
        if model_hint:
            print(f"    Model: {model_hint}")
        print(f"    Prompt size: {len(prompt)} chars")
        print("    Starting request...")
        print("-" * 60)
        if stream_enabled:
            print("    Streaming response:\n")

        start_time = time.time()
        try:
            result = router.request(  # type: ignore[attr-defined]
                messages=[{"role": "user", "content": prompt}],
                total_timeout_s=self._agent_timeout,
                task_id=task_id,
                stream=stream_enabled,
                on_token=on_token if stream_enabled else None,
            )
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"Error spawning agent: {e}")
            return False
        finally:
            elapsed = time.time() - start_time

        if stream_enabled:
            print("\n")

        if not stream_enabled:
            content = ""
            try:
                content = result["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                content = str(result)
            if content:
                print(f"\n[RESULT]\n{content[:1000]}")

        self._maybe_print_router_summary()
        print(f"Agent completed in {elapsed:.1f}s")
        return True

    def run_with_agent(
        self,
        agent_select: str,
        task,
        prompt: str,
        task_id_suffix: str = "",
    ) -> bool:
        previous = self._agent_select
        self._agent_select = agent_select
        try:
            return self.run(task, prompt, task_id_suffix=task_id_suffix)
        finally:
            self._agent_select = previous


# ---------------------------------------------------------------------------
# Todo executor
# ---------------------------------------------------------------------------

class TodoExecutor:
    def __init__(
        self,
        paths: ExecutorPaths,
        todo_file: Optional[str] = None,
        max_tasks: Optional[int] = None,
        skip_tests: bool = False,
        agent_timeout: int = 600,
        continue_on_failure: bool = False,
        max_retries: int = 3,
        max_dod_attempts: int = 3,
        mode: str = "agent",
        agent_select: str = "claude",
        agent_fallback_order: Optional[list[str]] = None,
    ) -> None:
        self._paths = paths

        self.todo_file = todo_file
        self.max_tasks = max_tasks
        self.skip_tests = skip_tests
        self.agent_timeout = agent_timeout
        self.continue_on_failure = continue_on_failure
        self.max_retries = max_retries
        self.max_dod_attempts = max_dod_attempts
        self.mode = mode

        self.agent_select = agent_select
        self.agent_fallback_order = agent_fallback_order or [agent_select]

        self._check_codemap = mode != "ci"

        self.tasks_attempted = 0
        self.tasks_completed = 0
        self.tasks_failed = 0

        self._current_task_retries = 0
        self.total_pending = 0
        self._previous_failure_context = ""

        self._agent = AgentRunner(
            paths=self._paths,
            agent_timeout=self.agent_timeout,
            agent_select=self.agent_select,
        )

    def _todo_files(self) -> list[Path]:
        if self.todo_file:
            return [_resolve_todo_file_arg(self.todo_file, EXEC_CWD, self._paths.project_root)]
        return [_resolve_default_todo_file(EXEC_CWD, self._paths.project_root)]

    def _count_pending_tasks(self) -> int:
        total = 0
        for todo_file in self._todo_files():
            if todo_file.exists():
                tasks = parse_todo_file(str(todo_file))
                total += sum(1 for t in tasks if t.status == "pending")
        return total

    def _next_task(self):
        for todo_file in self._todo_files():
            if todo_file.exists():
                task = get_next_pending_task(str(todo_file))
                if task:
                    return task
        return None

    def _regenerate_codemap(self) -> bool:
        cwd = self._paths.project_root

        for ps_script in cwd.glob("**/*codemap*.ps1"):
            try:
                result = subprocess.run(
                    ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ps_script)],
                    cwd=str(cwd),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=60,
                )
                if result.returncode == 0:
                    print(f"    CODEMAP.md regenerated via {ps_script.relative_to(cwd)}")
                    return True
            except Exception as e:
                print(f"    PowerShell script failed: {e}")

        for py_tool in cwd.glob("**/*codemap*.py"):
            try:
                result = subprocess.run(
                    [sys.executable, str(py_tool)],
                    cwd=str(cwd),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=60,
                )
                if result.returncode == 0:
                    print(f"    CODEMAP.md regenerated via {py_tool.relative_to(cwd)}")
                    return True
            except Exception as e:
                print(f"    Python tool failed: {e}")

        print("    Warning: Could not regenerate CODEMAP.md")
        return False

    def _load_dod_text(self) -> str:
        path = self._paths.dod_path
        if not path.exists():
            return f"[Definition of Done not found: {path}]"
        try:
            return path.read_text(encoding="utf-8")
        except Exception as e:
            return f"[Error reading Definition of Done: {e}]"

    def _run_hook(self, hook_path: Path, args: list[str], timeout_s: int = 15) -> tuple[int, str, str]:
        if not hook_path.exists():
            return 127, "", f"Hook not found: {hook_path}"
        try:
            result = subprocess.run(
                [sys.executable, str(hook_path), *args],
                cwd=str(self._paths.project_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_s,
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except Exception as e:
            return 1, "", f"Hook error: {e}"

    def _run_pre_prompt_hook(self) -> str:
        rc, out, err = self._run_hook(self._paths.pre_prompt_hook_path, [], timeout_s=10)
        if rc != 0:
            if err:
                print(f"Warning: pre-prompt hook failed: {err}", file=sys.stderr)
            return ""
        return out

    def _run_tests(self) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest"],
                cwd=str(self._paths.project_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            return False, "Tests timed out after 5 minutes"
        except Exception as e:
            return False, f"Error running tests: {e}"

        output = "\n".join([result.stdout, result.stderr]).strip()
        if result.returncode == 0:
            return True, output or "Tests passed"
        return False, output or f"Tests failed (exit code {result.returncode})"

    def _build_remediation_prompt(
        self,
        failure: str,
        details: str,
        tests_output: str,
        task_context: str,
        dod_text: str,
    ) -> str:
        output_block = f"\n## TEST OUTPUT\n\n{tests_output}\n" if tests_output else ""
        context_block = f"\n## TASK CONTEXT\n\n{task_context}\n" if task_context else ""
        dod_block = f"\n## DEFINITION OF DONE\n\n{dod_text}\n" if dod_text else ""
        return (
            "You are running targeted DoD remediation.\n\n"
            f"Failure: {failure}\n"
            f"Details: {details}\n"
            f"{output_block}"
            f"{context_block}"
            f"{dod_block}\n"
            "Instructions:\n"
            "- Fix only the failing criteria described above.\n"
            "- Keep changes minimal and focused.\n"
        )

    def _format_validation_failure_context(
        self,
        task,
        validation,
        task_context: str,
        hook_out: str = "",
        hook_err: str = "",
        tests_output: str = "",
        validation_tests_output: str = "",
    ) -> str:
        lines = [
            "The previous task failed Definition of Done validation.",
            f"Task: {task.description}",
            f"File: {task.file_path}:{task.line_number}",
        ]
        if task.section:
            lines.append(f"Section: {task.section}")
        if task.parent_task:
            lines.append(f"Parent: {task.parent_task}")
        lines.append("Failed criteria:")
        for criterion in validation.criteria_failed:
            lines.append(f"- {criterion}")
            details = validation.failure_details.get(criterion, "")
            if details:
                lines.append(_truncate(details, 2000))
        if validation.suggestions:
            lines.append("Suggestions:")
            for suggestion in validation.suggestions:
                lines.append(f"- {suggestion}")
        if task_context:
            lines.append("Task context:")
            lines.append(task_context)
        if hook_out or hook_err:
            lines.append("Post-complete hook output:")
            if hook_out:
                lines.append(_truncate(hook_out, 4000))
            if hook_err:
                lines.append(_truncate(hook_err, 4000))
        if validation_tests_output:
            lines.append("Validation test output:")
            lines.append(_truncate(validation_tests_output, 4000))
        if tests_output:
            lines.append("Remediation test output:")
            lines.append(_truncate(tests_output, 4000))
        lines.append("Address the errors above before retrying the task.")
        return "\n".join(lines)

    def _format_agent_failure_context(self, task, reason: str = "") -> str:
        lines = [
            "The previous task's agent run failed.",
            f"Task: {task.description}",
            f"File: {task.file_path}:{task.line_number}",
        ]
        if reason:
            lines.append(f"Reason: {reason}")
        lines.append("Use console output from the prior run for details.")
        return "\n".join(lines)

    def _agent_available(self, agent: str) -> tuple[bool, str]:
        agent = (agent or "").strip().lower()
        if agent == "router":
            return (_has_router_creds(), "missing OPENROUTER_API_KEY")
        if agent in ("claude", "codex"):
            cmd = _resolve_cli_command_for_windows(agent)
            ok = bool(cmd and cmd[0] and _which(cmd[0]))
            return (ok, f"command not found for {agent}")
        return (False, "unknown agent")

    def _run_agent_with_fallback(self, task, prompt: str, task_id_suffix: str = "") -> tuple[bool, str]:
        order = self.agent_fallback_order or [self.agent_select]
        attempted: list[str] = []
        skipped: list[str] = []

        for idx, agent in enumerate(order):
            avail, why = self._agent_available(agent)
            if not avail:
                skipped.append(f"{agent} ({why})")
                continue

            attempted.append(agent)
            if idx > 0:
                print(f"\n--- Falling back to {agent} ---")
            ok = self._agent.run_with_agent(agent, task, prompt, task_id_suffix=task_id_suffix)
            if ok:
                if skipped:
                    print(
                        "Note: skipped unavailable agents: " + ", ".join(skipped),
                        file=sys.stderr,
                    )
                return True, ""

        msg = "Tried agents: " + (", ".join(attempted) if attempted else "(none)")
        if skipped:
            msg += " | Skipped: " + ", ".join(skipped)
        return False, msg

    def _format_no_task_context(self) -> str:
        todo_files = self._todo_files()
        primary_todo = todo_files[0] if todo_files else None
        lines = [
            "TODO TASK CONTEXT",
            "Task: (none pending)",
            f"File: {primary_todo}" if primary_todo else "File: (unknown)",
            "Section: (none)",
            "Parent: (none)",
        ]
        return "\n".join(lines)

    def _validate_and_remediate(self, task) -> bool:
        validation = None
        dod_text = self._load_dod_text()
        task_context = get_task_context(task)

        last_hook_out = ""
        last_hook_err = ""
        last_tests_output = ""
        last_validation_tests_output = ""

        for attempt in range(1, self.max_dod_attempts + 1):
            print("\n--- Validating Definition of Done ---\n")
            rc, hook_out, hook_err = self._run_hook(
                self._paths.post_complete_hook_path,
                ["--validate-only"],
                timeout_s=300,
            )
            last_hook_out = hook_out
            last_hook_err = hook_err
            if rc != 0 and (hook_out or hook_err):
                print("\n[post-complete hook output]\n")
                if hook_out:
                    print(hook_out)
                if hook_err:
                    print(hook_err, file=sys.stderr)

            validation = validate_task_completion(
                skip_tests=self.skip_tests,
                codemap_base_dir=self._paths.project_root,
                check_codemap=self._check_codemap,
            )

            if validation.passed:
                self._previous_failure_context = ""
                mark_task_complete(task.file_path, task.line_number)
                self.tasks_completed += 1
                print(f"\n[PASS] Task completed: {task.description}")
                print(f"  All {len(validation.criteria_met)} DoD criteria met")
                print(f"  OK Marked as complete in {task.file_path}")
                return True

            print(f"\n[FAIL] Task NOT complete: {task.description}")
            print(f"\nFailed criteria ({len(validation.criteria_failed)}):")
            for criterion in validation.criteria_failed:
                print(f"  - {criterion}")
                if criterion in validation.failure_details:
                    print(f"    {_truncate(validation.failure_details[criterion], 200)}")

            if "Tests Pass" in validation.failure_details:
                last_validation_tests_output = validation.failure_details["Tests Pass"]

            if validation.suggestions:
                print("\nSuggestions:")
                for suggestion in validation.suggestions:
                    print(f"  - {suggestion}")

            if attempt >= self.max_dod_attempts:
                print(f"\nMax DoD remediation attempts reached ({self.max_dod_attempts}).")
                break

            failures = set(validation.criteria_failed)

            if "CODEMAP Updated" in failures and self._check_codemap:
                print("\n--- Remediating: CODEMAP Updated ---\n")
                self._regenerate_codemap()
                continue

            if "Tests Pass" in failures:
                print("\n--- Remediating: Tests Pass ---\n")
                tests_ok, tests_output = self._run_tests()
                if tests_output:
                    last_tests_output = tests_output
                if tests_ok:
                    continue
                failure_details = validation.failure_details.get("Tests Pass", "")
                prompt = self._build_remediation_prompt(
                    "Tests Pass",
                    failure_details,
                    tests_output,
                    task_context,
                    dod_text,
                )
                self._run_agent_with_fallback(task, prompt, task_id_suffix="dod-remediation")
                continue

            if validation.criteria_failed:
                failure = validation.criteria_failed[0]
                details = validation.failure_details.get(failure, "")
                prompt = self._build_remediation_prompt(
                    failure,
                    details,
                    "",
                    task_context,
                    dod_text,
                )
                self._run_agent_with_fallback(task, prompt, task_id_suffix="dod-remediation")
                continue

            break

        if validation is not None:
            self._previous_failure_context = self._format_validation_failure_context(
                task,
                validation,
                task_context,
                hook_out=last_hook_out,
                hook_err=last_hook_err,
                tests_output=last_tests_output,
                validation_tests_output=last_validation_tests_output,
            )
        return False

    def run(self) -> int:
        self.total_pending = self._count_pending_tasks()
        todo_files = self._todo_files()

        print("=" * 80)
        print("TODO Task Executor - Starting")
        print("=" * 80)
        print("Project root:", self._paths.project_root)
        print("TODO files:")
        for p in todo_files:
            print("  -", p)
        print(f"Pending tasks: {self.total_pending}")
        if self.max_tasks:
            print(f"Max tasks to process: {self.max_tasks}")
        if self.continue_on_failure:
            print("Mode: Continue on failure (batch mode)")
        print(f"Run mode: {self.mode}")
        print()

        while True:
            self.tasks_attempted += 1

            if self.max_tasks and self.tasks_attempted > self.max_tasks:
                print(f"\nReached max tasks: {self.max_tasks}")
                break

            task = self._next_task()
            if not task:
                print("\n" + self._format_no_task_context())
                print("\nOK All TODO tasks complete!")
                print("Tasks completed: 0 (no pending tasks)")
                break

            print(f"\n{'=' * 80}")
            task_label = f"TASK {self.tasks_attempted}"
            if self.max_tasks:
                task_label += f"/{self.max_tasks}"
            elif self.total_pending:
                task_label += f"/{self.total_pending}"
            print(task_label)
            print(f"{'=' * 80}")
            print(get_task_context(task))

            hook_context = self._run_pre_prompt_hook()
            dod_text = self._load_dod_text()
            prompt = self._agent.build_task_prompt(
                task,
                hook_context=hook_context,
                dod_text=dod_text,
                previous_failure_context=self._previous_failure_context,
            )
            ok, failure_reason = self._run_agent_with_fallback(task, prompt)
            if not ok:
                self._previous_failure_context = self._format_agent_failure_context(
                    task,
                    reason=failure_reason,
                )
                self._current_task_retries += 1
                if self._current_task_retries >= self.max_retries:
                    print(f"\nAgent failed {self.max_retries} times. Skipping task.")
                    self.tasks_failed += 1
                    self._current_task_retries = 0
                    continue
                print(f"\nAgent failed (attempt {self._current_task_retries}/{self.max_retries}). Retrying...")
                self.tasks_attempted -= 1
                continue
            self._current_task_retries = 0

            if ensure_task_pending(task.file_path, task.line_number):
                print(f"    Reset TODO status to pending for {task.file_path}:{task.line_number}")

            passed = self._validate_and_remediate(task)
            if passed:
                continue

            if self.continue_on_failure:
                print("\nContinuing to next task...")
                self.tasks_failed += 1
                self._current_task_retries = 0
                continue
            self._current_task_retries += 1
            if self._current_task_retries >= self.max_retries:
                print(f"\nValidation failed {self.max_retries} times. Skipping task.")
                self.tasks_failed += 1
                self._current_task_retries = 0
                continue
            print(f"\nValidation failed (attempt {self._current_task_retries}/{self.max_retries}). Retrying...")
            self.tasks_attempted -= 1
            continue

        print("\n" + "=" * 80)
        print("EXECUTION SUMMARY")
        print("=" * 80)
        print(f"Tasks attempted: {self.tasks_attempted}")
        print(f"Tasks completed: {self.tasks_completed}")
        print(f"Tasks failed: {self.tasks_failed}")

        return 0 if self.tasks_failed == 0 else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="TODO Task Executor - Sequential execution with DoD validation"
    )
    parser.add_argument(
        "--todo-file",
        type=str,
        default=None,
        help="Specific TODO file to process (default: project root TODO.md)",
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=None,
        help="Maximum number of tasks to process (default: unlimited)",
    )
    parser.add_argument(
        "--agent-select",
        choices=["claude", "codex", "router"],
        default="claude",
        help="Select agent provider (default: claude). Use 'router' for internal openrouter_harness.",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip running tests during validation (faster for testing)",
    )
    parser.add_argument(
        "--agent-timeout",
        type=int,
        default=600,
        help="Timeout in seconds for each agent execution (default: 600)",
    )
    parser.add_argument(
        "--mode",
        choices=["agent", "ci"],
        default="agent",
        help="Execution mode (agent spawns or CI/no-agent)",
    )
    parser.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="Continue to next task even if current one fails validation (batch mode)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum retries per task before moving on (default: 3)",
    )
    parser.add_argument(
        "--max-dod-attempts",
        type=int,
        default=3,
        help="Maximum DoD remediation attempts per task (default: 3)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debugpy listener (waits for attach on port 5678)",
    )

    args = parser.parse_args()

    if args.debug:
        try:
            import debugpy  # type: ignore
        except Exception as e:
            raise RuntimeError(
                "debugpy is required for --debug. Install with: pip install debugpy"
            ) from e
        debugpy.listen(("127.0.0.1", 5678))
        print("debugpy listening on 127.0.0.1:5678")
        print('Attach from VS Code: Run and Debug -> "Todo Executor (terminal + attach)" or press F5')
        if _is_interactive():
            try:
                input("Press Enter after starting the VS Code attach (F5)... ")
            except EOFError:
                pass
        debugpy.wait_for_client()

    agent_select = _normalize_agent_name(args.agent_select) or args.agent_select
    agent_fallback_order = _build_fallback_order(agent_select)

    paths = ExecutorPaths.from_project_root(PROJECT_ROOT)

    executor = TodoExecutor(
        paths=paths,
        todo_file=args.todo_file,
        max_tasks=args.max_tasks,
        skip_tests=args.skip_tests,
        agent_timeout=args.agent_timeout,
        continue_on_failure=args.continue_on_failure,
        max_retries=args.max_retries,
        max_dod_attempts=args.max_dod_attempts,
        mode=args.mode,
        agent_select=agent_select,
        agent_fallback_order=agent_fallback_order,
    )
    return executor.run()


if __name__ == "__main__":
    sys.exit(main())
