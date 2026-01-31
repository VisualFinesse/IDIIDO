from __future__ import annotations

import json
import pathlib
import pytest
from openrouter_harness import *



class DummyClient:
    def __init__(self, sequence):
        self.sequence = list(sequence)

    def create_chat_completion(self, model, messages, timeout_s, stream=False, on_token=None):
        if not self.sequence:
            raise RuntimeError("No more responses configured")
        item = self.sequence.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_timeout_fallback_success(tmp_path, capsys):
    models = ["model-a", "model-b"]
    config = RouterConfig(models=models, caps=RouterCaps(max_attempts=7))
    telemetry_path = tmp_path / "llm_attempts.jsonl"
    telemetry = TelemetryWriter(telemetry_path)
    client = DummyClient(
        [
            RetryableError("timeout", reason="timeout"),
            {"choices": [{"message": {"content": "ok"}}]},
        ]
    )
    router = OpenRouterHarness(config=config, client=client, telemetry=telemetry)
    result = router.request(messages=[{"role": "user", "content": "hi"}])

    assert result["choices"][0]["message"]["content"] == "ok"
    err_lines = capsys.readouterr().err.strip().splitlines()
    combined = "\n".join(err_lines)
    assert "LLM model=model-a attempt=1/7 task=unknown latency_ms=" in combined
    assert "LLM model=model-b attempt=2/7 task=unknown latency_ms=" in combined
    assert "attempt 1/7 model=model-a status=retryable_error latency_ms=" in combined
    assert "attempt 2/7 model=model-b status=ok latency_ms=" in combined
    assert "selected model=model-b" in combined

    records = [json.loads(line) for line in telemetry_path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 2
    assert records[0]["ok"] is False
    assert records[1]["ok"] is True
    assert records[1]["model"] == "model-b"


def test_429_5xx_fallback_success(tmp_path, capsys):
    models = ["model-a", "model-b", "model-c"]
    config = RouterConfig(models=models, caps=RouterCaps(max_attempts=7))
    telemetry_path = tmp_path / "llm_attempts.jsonl"
    telemetry = TelemetryWriter(telemetry_path)
    client = DummyClient(
        [
            RetryableError("rate limited", reason="http_429", status_code=429),
            RetryableError("server error", reason="http_500", status_code=500),
            {"choices": [{"message": {"content": "ok"}}]},
        ]
    )
    router = OpenRouterHarness(config=config, client=client, telemetry=telemetry)
    result = router.request(messages=[{"role": "user", "content": "hi"}])

    assert result["choices"][0]["message"]["content"] == "ok"
    err_lines = capsys.readouterr().err.strip().splitlines()
    combined = "\n".join(err_lines)
    assert "LLM model=model-a attempt=1/7 task=unknown latency_ms=" in combined
    assert "LLM model=model-b attempt=2/7 task=unknown latency_ms=" in combined
    assert "LLM model=model-c attempt=3/7 task=unknown latency_ms=" in combined
    assert "attempt 1/7 model=model-a status=retryable_error latency_ms=" in combined
    assert "attempt 2/7 model=model-b status=retryable_error latency_ms=" in combined
    assert "attempt 3/7 model=model-c status=ok latency_ms=" in combined
    assert "selected model=model-c" in combined

    records = [json.loads(line) for line in telemetry_path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 3
    assert records[2]["ok"] is True
    assert records[2]["model"] == "model-c"


def test_router_fail_fast_nonretryable(tmp_path, capsys):
    models = ["model-a", "model-b"]
    config = RouterConfig(models=models, caps=RouterCaps(max_attempts=7))
    telemetry_path = tmp_path / "llm_attempts.jsonl"
    telemetry = TelemetryWriter(telemetry_path)
    client = DummyClient([NonRetryableError("bad request", status_code=400)])
    router = OpenRouterHarness(config=config, client=client, telemetry=telemetry)

    with pytest.raises(NonRetryableError):
        router.request(messages=[{"role": "user", "content": "hi"}])

    err_lines = capsys.readouterr().err.strip().splitlines()
    combined = "\n".join(err_lines)
    assert "LLM model=model-a attempt=1/7 task=unknown latency_ms=" in combined
    assert "attempt 1/7 model=model-a status=non_retryable_error latency_ms=" in combined

    records = [json.loads(line) for line in telemetry_path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    assert records[0]["ok"] is False
    assert records[0]["http_status"] == 400


def test_total_timeout_exceeded(tmp_path, monkeypatch):
    models = ["model-a", "model-b"]
    config = RouterConfig(models=models, caps=RouterCaps(max_attempts=7, total_timeout_s=1))
    telemetry = TelemetryWriter(tmp_path / "llm_attempts.jsonl")
    client = DummyClient([RetryableError("timeout", reason="timeout")])
    router = OpenRouterHarness(config=config, client=client, telemetry=telemetry)

    times = [0.0, 2.0, 2.0]

    def fake_monotonic():
        return times.pop(0)

    monkeypatch.setattr("openrouter_harness.router.time.monotonic", fake_monotonic)

    with pytest.raises(TotalTimeoutError):
        router.request(messages=[{"role": "user", "content": "hi"}])


def test_streaming_on_token_propagates(tmp_path):
    models = ["model-a"]
    config = RouterConfig(models=models, caps=RouterCaps(max_attempts=1))
    telemetry = TelemetryWriter(tmp_path / "llm_attempts.jsonl")
    observed = {"stream": None, "tokens": []}

    class StreamingClient:
        def create_chat_completion(self, model, messages, timeout_s, stream=False, on_token=None):
            observed["stream"] = stream
            if on_token:
                on_token("hello")
                on_token(" world")
            return {
                "choices": [{"message": {"content": "hello world"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            }

    router = OpenRouterHarness(config=config, client=StreamingClient(), telemetry=telemetry)

    def on_token(token):
        observed["tokens"].append(token)

    result = router.request(
        messages=[{"role": "user", "content": "hi"}],
        stream=True,
        on_token=on_token,
    )

    assert observed["stream"] is True
    assert observed["tokens"] == ["hello", " world"]
    assert result["choices"][0]["message"]["content"] == "hello world"
    assert result["usage"]["total_tokens"] == 3


def test_streaming_disconnect_raises_retryable(monkeypatch):
    client = OpenRouterClient()
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    class FakeResponse:
        def __init__(self, lines):
            self._lines = lines

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def __iter__(self):
            return iter(self._lines)

    lines = [
        b"data: {\"choices\": [{\"delta\": {\"content\": \"hi\"}}]}\n",
        b"\n",
    ]

    def fake_urlopen(request, timeout):
        return FakeResponse(lines)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(RetryableError):
        client.create_chat_completion(
            model="model-a",
            messages=[{"role": "user", "content": "hi"}],
            timeout_s=1,
            stream=True,
            on_token=None,
        )
