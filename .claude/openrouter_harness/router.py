from __future__ import annotations

import sys
import time
import os
from typing import Any, Callable, Dict, List, Optional, Tuple

from .exceptions import NonRetryableError, RetryableError, TotalTimeoutError
from .models import RouterCaps, RouterConfig
from .openrouter_client import OpenRouterClient
from .telemetry import AttemptRecord, TelemetryWriter
from .tool_handler import ToolHandler


class OpenRouterHarness:
    def __init__(
        self,
        config: RouterConfig,
        client: Optional[OpenRouterClient] = None,
        telemetry: Optional[TelemetryWriter] = None,
    ) -> None:
        self.config = config
        self.client = client or OpenRouterClient()
        self.telemetry = telemetry or TelemetryWriter(
            path=".claude/logs/llm_attempts.jsonl"
        )
        self.tool_handler = ToolHandler(
            allowed_tools=["read_file", "write_to_file", "replace_in_file", "search_files", "list_files", "execute_command"],
            cwd=os.getcwd()
        )

    def request(
        self,
        messages: List[Dict[str, Any]],
        per_attempt_timeout_s: Optional[int] = None,
        max_attempts: Optional[int] = None,
        total_timeout_s: Optional[int] = None,
        task_id: Optional[str] = None,
        stream: bool = True,
        on_token: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        model: str
        caps = self._resolve_caps(per_attempt_timeout_s, max_attempts, total_timeout_s)
        start_time = time.monotonic()
        last_error: Optional[Exception] = None

        for index, model in enumerate(self.config.models):
            attempt = index + 1
            if attempt > caps.max_attempts:
                break
            elapsed = time.monotonic() - start_time
            if elapsed > caps.total_timeout_s:
                raise TotalTimeoutError(
                    f"Total timeout exceeded before attempt {attempt}",
                    elapsed_s=elapsed,
                )

            attempt_start = time.monotonic()
            try:
                # Make initial LLM request
                completion_response = self.client.create_chat_completion(
                    model=model,
                    messages=messages,
                    timeout_s=caps.per_attempt_timeout_s,
                    stream=stream,
                    on_token=on_token,
                )

                # Handle tool execution flow
                result = completion_response
                tool_results = []
                MAX_TOOL_ITERATIONS = 5  # Prevent infinite loops from tool responses
                
                for iteration in range(MAX_TOOL_ITERATIONS):
                    if not isinstance(result, dict) or not result.get("choices"):
                        break
                    
                    # Extract tool calls from response
                    tool_calls = result["choices"][0].get("tool_calls", [])
                    
                    if not tool_calls:
                        break  # No tool calls found, exit loop
                    
                    # Execute each tool call
                    for tool_call in tool_calls:
                        try:
                            tool_name = tool_call["tool"]
                            tool_params = tool_call["parameters"]
                            
                            # Execute tool
                            execution_result = self.tool_handler.execute_tool({
                                "tool": tool_name,
                                "parameters": tool_params
                            })
                            
                            # Format and store result
                            tool_results.append({
                                "tool": tool_name,
                                "result": execution_result
                            })
                            
                            # Append tool result to messages
                            messages.append({
                                "role": "tool",
                                "content": json.dumps(execution_result),
                                "name": tool_name
                            })
                            
                        except Exception as e:
                            print(f"Tool execution error: {e}", file=sys.stderr, flush=True)
                    
                    # Resend enriched prompt back to LLM
                    result = self.client.create_chat_completion(
                        model=model,
                        messages=messages,
                        timeout_s=caps.per_attempt_timeout_s,
                        stream=stream,
                        on_token=on_token,
                    )
                duration = time.monotonic() - attempt_start
                latency_ms = int(duration * 1000)
                log_task_id = task_id or "unknown"
                print(
                    f"LLM model={model} attempt={attempt}/{caps.max_attempts} task={log_task_id} latency_ms={latency_ms}",
                    file=sys.stderr,
                    flush=True,
                )
                print(
                    f"attempt {attempt}/{caps.max_attempts} model={model} status=ok latency_ms={latency_ms}",
                    file=sys.stderr,
                    flush=True,
                )
                self.telemetry.write(
                    AttemptRecord(
                        timestamp=TelemetryWriter.now(),
                        model=model,
                        selected_model=model,
                        attempt=attempt,
                        max_attempts=caps.max_attempts,
                        duration_s=duration,
                        latency_s=duration,
                        ok=True,
                        outcome="ok",
                    )
                )
                print(
                    f"selected model={model}",
                    file=sys.stderr,
                    flush=True,
                )
                return result
            except RetryableError as exc:
                duration = time.monotonic() - attempt_start
                latency_ms = int(duration * 1000)
                log_task_id = task_id or "unknown"
                print(
                    f"LLM model={model} attempt={attempt}/{caps.max_attempts} task={log_task_id} latency_ms={latency_ms}",
                    file=sys.stderr,
                    flush=True,
                )
                print(
                    f"attempt {attempt}/{caps.max_attempts} model={model} status=retryable_error latency_ms={latency_ms}",
                    file=sys.stderr,
                    flush=True,
                )
                self.telemetry.write(
                    AttemptRecord(
                        timestamp=TelemetryWriter.now(),
                        model=model,
                        selected_model=model,
                        attempt=attempt,
                        max_attempts=caps.max_attempts,
                        duration_s=duration,
                        latency_s=duration,
                        ok=False,
                        outcome="retryable_error",
                        reason=exc.reason,
                        error_type=exc.__class__.__name__,
                        error_message=str(exc),
                        http_status=exc.status_code,
                    )
                )
                last_error = exc
                next_attempt = attempt + 1
                if next_attempt > caps.max_attempts or next_attempt > len(self.config.models):
                    break
                elapsed = time.monotonic() - start_time
                if elapsed > caps.total_timeout_s:
                    raise TotalTimeoutError(
                        f"Total timeout exceeded after attempt {attempt}",
                        elapsed_s=elapsed,
                    ) from exc
                continue
            except NonRetryableError as exc:
                duration = time.monotonic() - attempt_start
                latency_ms = int(duration * 1000)
                log_task_id = task_id or "unknown"
                print(
                    f"LLM model={model} attempt={attempt}/{caps.max_attempts} task={log_task_id} latency_ms={latency_ms}",
                    file=sys.stderr,
                    flush=True,
                )
                print(
                    f"attempt {attempt}/{caps.max_attempts} model={model} status=non_retryable_error latency_ms={latency_ms}",
                    file=sys.stderr,
                    flush=True,
                )
                self.telemetry.write(
                    AttemptRecord(
                        timestamp=TelemetryWriter.now(),
                        model=model,
                        selected_model=model,
                        attempt=attempt,
                        max_attempts=caps.max_attempts,
                        duration_s=duration,
                        latency_s=duration,
                        ok=False,
                        outcome="non_retryable_error",
                        reason="non_retryable",
                        error_type=exc.__class__.__name__,
                        error_message=str(exc),
                        http_status=exc.status_code,
                    )
                )
                raise

        if isinstance(last_error, RetryableError):
            raise last_error
        raise NonRetryableError("All model attempts failed")

    def _add_tool_system_message(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        tool_list = [
            "read_file - Read file contents at specified path",
            "write_to_file - Create/overwrite files with specified content",
            "replace_in_file - Modify existing files with SEARCH/REPLACE blocks",
            "search_files - Regex search across files with context",
            "list_files - List directory contents",
            "execute_command - Run system commands (requires approval)"
        ]
        
        system_message = {
            "role": "system",
            "content": f"You can use these tools:\n" + "\n".join([f"- {tool}" for tool in tool_list])
        }
        
        # Don't duplicate existing system messages
        if not any(m["role"] == "system" for m in messages):
            return [system_message] + messages
        return messages

    def _resolve_caps(
        self,
        per_attempt_timeout_s: Optional[int],
        max_attempts: Optional[int],
        total_timeout_s: Optional[int],
    ) -> RouterCaps:
        caps = self.config.caps
        return RouterCaps(
            per_attempt_timeout_s=per_attempt_timeout_s or caps.per_attempt_timeout_s,
            max_attempts=max_attempts or caps.max_attempts,
            total_timeout_s=total_timeout_s or caps.total_timeout_s,
        )
