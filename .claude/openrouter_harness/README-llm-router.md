This directory contains a minimal OpenRouter fallback router for Python agents.

Drop-in usage (future wiring inside `todo-executor.py` or similar):

```python
from openrouter_harness import OpenRouterHarness, load_config

config = load_config(".claude/config/models.json")
router = OpenRouterHarness(config=config)

response = router.request(
    messages=[
        {"role": "user", "content": "Hello from the router"}
    ]
)

content = response["choices"][0]["message"]["content"]
print(content)
```

Notes:

- The router prefers `OPENROUTER_API_KEY` and falls back to `ANTHROPIC_AUTH_TOKEN`.
- Telemetry is written to `.claude/logs/llm_attempts.jsonl`.
- Retries occur on timeouts, network errors, HTTP 429, and HTTP 5xx.
