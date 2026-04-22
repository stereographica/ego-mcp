"""Seed default implicit_emergent_satisfaction entries for existing catalogs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

TARGET_VERSION = "1.1.0"

_BACKUP_FILENAME = "desires.pre_0008_emergent_cascade.json"

_DEFAULTS: dict[str, dict[str, float]] = {
    "curiosity":           {"grasp_something": 0.5},
    "information_hunger":  {"grasp_something": 0.5},
    "social_thirst":       {"be_with_someone": 0.5},
    "resonance":           {"be_with_someone": 0.5},
    "cognitive_coherence": {"feel_safe":       0.5},
}


def _apply_defaults(payload: dict[str, Any]) -> bool:
    """Add missing cascade defaults to the catalog payload. Returns True if changed."""
    fixed = payload.get("fixed_desires")
    if not isinstance(fixed, dict):
        return False

    changed = False
    for desire_id, defaults in _DEFAULTS.items():
        desire_config = fixed.get(desire_id)
        if not isinstance(desire_config, dict):
            continue

        existing = desire_config.get("implicit_emergent_satisfaction")
        if not isinstance(existing, dict):
            desire_config["implicit_emergent_satisfaction"] = dict(defaults)
            changed = True
            continue

        for emergent_id, quality in defaults.items():
            if emergent_id not in existing:
                existing[emergent_id] = quality
                changed = True
    return changed


def up(data_dir: Path) -> None:
    """Add default implicit_emergent_satisfaction entries to settings/desires.json."""
    catalog_path = data_dir / "settings" / "desires.json"
    if not catalog_path.exists():
        return

    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    if not isinstance(payload, dict):
        return

    if not _apply_defaults(payload):
        return

    backup_path = catalog_path.parent / _BACKUP_FILENAME
    if not backup_path.exists():
        original_text = catalog_path.read_text(encoding="utf-8")
        backup_path.write_text(original_text, encoding="utf-8")

    catalog_path.write_text(
        json.dumps(cast(dict[str, Any], payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
