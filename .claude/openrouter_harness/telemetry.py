from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class AttemptRecord:
    timestamp: float
    model: str
    selected_model: str
    attempt: int
    max_attempts: int
    duration_s: float
    latency_s: float
    ok: bool
    outcome: str
    reason: Optional[str] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    http_status: Optional[int] = None


class TelemetryWriter:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, record: AttemptRecord) -> None:
        payload = asdict(record)
        payload["timestamp"] = round(payload["timestamp"], 3)
        payload["duration_s"] = round(payload["duration_s"], 3)
        payload["latency_s"] = round(payload["latency_s"], 3)
        line = json.dumps(payload, ensure_ascii=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    @staticmethod
    def now() -> float:
        return time.time()
