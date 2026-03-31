"""Copy legacy desire state into the new desire_state.json location."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from ego_mcp.desire_catalog import BUILTIN_FIXED_DESIRE_IDS

TARGET_VERSION = "0.6.0"


def up(data_dir: Path) -> None:
    """Copy legacy root desires.json into desire_state.json when upgrading."""
    legacy_path = data_dir / "desires.json"
    new_state_path = data_dir / "desire_state.json"

    if new_state_path.exists() or not legacy_path.exists():
        return

    try:
        with open(legacy_path, encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return

    if not isinstance(payload, dict):
        return

    filtered: dict[str, dict[str, Any]] = {}
    for name, raw in payload.items():
        if not isinstance(name, str) or not isinstance(raw, dict):
            continue
        if bool(raw.get("is_emergent", False)) or name in BUILTIN_FIXED_DESIRE_IDS:
            filtered[name] = raw

    with open(new_state_path, "w", encoding="utf-8") as f:
        json.dump(cast(dict[str, Any], filtered), f, ensure_ascii=False, indent=2)
