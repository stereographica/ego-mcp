"""Reset desire timestamps after satisfaction-hours rebalance."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from ego_mcp import timezone_utils

TARGET_VERSION = "0.4.0"


def up(data_dir: Path) -> None:
    """Reset all recorded desire `last_satisfied` timestamps to now (UTC)."""
    desires_path = data_dir / "desires.json"
    if not desires_path.exists():
        return

    with open(desires_path, encoding="utf-8") as f:
        payload = json.load(f)

    if not isinstance(payload, dict):
        return

    now_iso = timezone_utils.now().isoformat()
    for state in payload.values():
        if isinstance(state, dict):
            state["last_satisfied"] = now_iso

    with open(desires_path, "w", encoding="utf-8") as f:
        json.dump(cast(dict[str, Any], payload), f, ensure_ascii=False, indent=2)
