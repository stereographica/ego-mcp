"""Normalize legacy emergent desire sentence keys to stable IDs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from ego_mcp.emergent_desires import canonical_emergent_desire_id

TARGET_VERSION = "0.6.1"

_BACKUP_FILENAME = "desire_state.pre_0006_emergent_desire_ids.json"


def _merge_state_entry(
    existing: dict[str, Any] | None,
    incoming: dict[str, Any],
) -> dict[str, Any]:
    if existing is None:
        return dict(incoming)
    merged = dict(existing)
    for key, value in incoming.items():
        if key not in merged or merged[key] in ("", None):
            merged[key] = value
    return merged


def up(data_dir: Path) -> None:
    """Rewrite legacy emergent sentence keys in desire_state.json."""
    state_path = data_dir / "desire_state.json"
    if not state_path.exists():
        return

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    if not isinstance(payload, dict):
        return

    normalized: dict[str, dict[str, Any]] = {}
    changed = False
    for name, raw in payload.items():
        if not isinstance(name, str) or not isinstance(raw, dict):
            changed = True
            continue
        canonical_name = (
            canonical_emergent_desire_id(name)
            if bool(raw.get("is_emergent", False))
            else name
        )
        if canonical_name != name:
            changed = True
        normalized[canonical_name] = _merge_state_entry(
            normalized.get(canonical_name),
            raw,
        )

    if not changed:
        return

    backup_path = data_dir / _BACKUP_FILENAME
    if not backup_path.exists():
        backup_path.write_text(
            json.dumps(cast(dict[str, Any], payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    state_path.write_text(
        json.dumps(cast(dict[str, Any], normalized), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
