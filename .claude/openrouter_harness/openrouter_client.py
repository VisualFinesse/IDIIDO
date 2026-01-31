from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
import dotenv
from typing import Any, Callable, Dict, List, Optional

from .exceptions import NonRetryableError, RetryableError

dotenv.load_dotenv()


class OpenRouterClient:
    def __init__(self, base_url: str = "https://openrouter.ai/api/v1/chat/completions") -> None:
        self.base_url = base_url

    def _get_api_key(self) -> str:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise NonRetryableError("Missing OpenRouter API key in env")
        return api_key

    def create_chat_completion(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        timeout_s: int,
        stream: bool = True,
        on_token: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        payload = {
            "model": model,
            "messages": messages,
        }
        if stream:
            payload["stream"] = True
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._get_api_key()}",
            "Content-Type": "application/json",
            "User-Agent": "openrouter-harness/1",
        }
        if stream:
            headers["Accept"] = "text/event-stream"
        request = urllib.request.Request(
            self.base_url,
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                if not stream:
                    body = response.read().decode("utf-8")
                    try:
                        return json.loads(body)
                    except json.JSONDecodeError as exc:
                        raise NonRetryableError(f"Invalid JSON response: {exc}") from exc

                content_chunks: List[str] = []
                usage_payload: Optional[Dict[str, Any]] = None
                data_lines: List[str] = []
                saw_done = False
                for raw_line in response:
                    if raw_line is None:
                        continue
                    line = raw_line.decode("utf-8", errors="ignore").rstrip("\r\n")
                    if line == "":
                        if not data_lines:
                            continue
                        payload_text = "\n".join(data_lines).strip()
                        data_lines.clear()
                        if payload_text == "[DONE]":
                            saw_done = True
                            break
                        try:
                            event = json.loads(payload_text)
                        except json.JSONDecodeError as exc:
                            raise NonRetryableError(f"Invalid JSON event: {exc}") from exc
                        if isinstance(event, dict) and "error" in event:
                            raise NonRetryableError(str(event["error"]))
                        if isinstance(event, dict) and isinstance(event.get("usage"), dict):
                            usage_payload = event["usage"]
                        content_chunk, tool_calls = self._extract_content(event)
                        if content_chunk:
                            content_chunks.append(content_chunk)
                            if on_token:
                                on_token(content_chunk)
                        
                        # Store tool calls in final response
                        if tool_calls:
                            if not response_payload.get("choices"):
                                response_payload["choices"] = [{"message": {}}]
                            response_payload["choices"][0]["tool_calls"] = tool_calls
                        continue
                    if line.startswith(":"):
                        continue
                    if line.startswith("data:"):
                        data_lines.append(line[len("data:"):].lstrip())
                        continue

                if not saw_done:
                    raise RetryableError("Stream ended before [DONE]", reason="stream_ended")

                response_payload: Dict[str, Any] = {
                    "choices": [{"message": {"content": "".join(content_chunks)}}]
                }
                if usage_payload is not None:
                    response_payload["usage"] = usage_payload
                return response_payload
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = ""
            try:
                body = exc.read().decode("utf-8")
            except Exception:
                body = ""
            message = f"HTTP {status}: {body}".strip()
            if status in {429} or 500 <= status <= 599:
                raise RetryableError(message, reason=f"http_{status}", status_code=status) from exc
            if status in {400, 401, 403, 404, 422} or 400 <= status <= 499:
                raise NonRetryableError(message, status_code=status) from exc
            raise NonRetryableError(message, status_code=status) from exc
        except (urllib.error.URLError, socket.timeout) as exc:
            reason = "timeout" if isinstance(exc, socket.timeout) else "network"
            raise RetryableError(str(exc), reason=reason) from exc

    @staticmethod
    def _extract_content(event: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
        import re
        content = ""
        tool_calls = []
        
        # Check all content locations
        choices = event.get("choices", [])
        if choices:
            choice = choices[0]
            if isinstance(choice, dict):
                if "delta" in choice:
                    content = choice["delta"].get("content", "")
                elif "message" in choice:
                    content = choice["message"].get("content", "")
                else:
                    content = choice.get("content", "")
        
        # Detect and extract tool calls
        tool_pattern = re.compile(r"<([a-zA-Z_]+)>(.*?)</\1>", re.DOTALL)
        matches = tool_pattern.findall(content)
        
        for tool_name, tool_content in matches:
            tool_calls.append({
                "tool": tool_name,
                "parameters": tool_content.strip()
            })
        
        # Remove tool markup from main content
        clean_content = tool_pattern.sub("", content).strip()
        
        return clean_content, tool_calls
        choices = event.get("choices")
        if not choices:
            return ""
        choice = choices[0] if isinstance(choices, list) and choices else choices
        if not isinstance(choice, dict):
            return ""
        if "delta" in choice and isinstance(choice["delta"], dict):
            return choice["delta"].get("content") or ""
        if "message" in choice and isinstance(choice["message"], dict):
            return choice["message"].get("content") or ""
        return choice.get("content") or ""
