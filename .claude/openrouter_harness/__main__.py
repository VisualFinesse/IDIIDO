from __future__ import annotations

import json
from pathlib import Path

from .models import load_config


def main() -> None:
    config_path = Path(".claude/config/models.json")
    config = load_config(config_path)
    payload = {
        "models": config.models,
        "caps": {
            "per_attempt_timeout_s": config.caps.per_attempt_timeout_s,
            "max_attempts": config.caps.max_attempts,
            "total_timeout_s": config.caps.total_timeout_s,
        },
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
