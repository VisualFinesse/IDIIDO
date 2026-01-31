from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class RouterCaps:
    per_attempt_timeout_s: int = 90
    max_attempts: int = 7
    total_timeout_s: int = 300


@dataclass(frozen=True)
class RouterConfig:
    models: List[str]
    caps: RouterCaps


def load_config(path: str | Path) -> RouterConfig:
    config_path = Path(path)
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    models = list(raw.get("models", []))
    caps_raw = raw.get("caps", {})
    caps = RouterCaps(
        per_attempt_timeout_s=int(caps_raw.get("per_attempt_timeout_s", 90)),
        max_attempts=int(caps_raw.get("max_attempts", 7)),
        total_timeout_s=int(caps_raw.get("total_timeout_s", 300)),
    )
    if not models:
        raise ValueError("models list is empty")
    return RouterConfig(models=models, caps=caps)
