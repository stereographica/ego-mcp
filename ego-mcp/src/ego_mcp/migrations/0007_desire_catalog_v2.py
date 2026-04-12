"""Migrate desire catalog from v1 (medium/high) to v2 (rising/steady/settling)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

TARGET_VERSION = "1.0.0"

_BACKUP_FILENAME = "desires.pre_0007_catalog_v2.json"

_TOOL_RENAMES: dict[str, str] = {
    "emotion_trend": "attune",
    "feel_desires": "attune",
}


def migrate_catalog_v1_to_v2(data: dict[str, Any]) -> bool:
    """Migrate a catalog dict in-place from v1 to v2.

    Returns True if any changes were made.
    """
    if data.get("version", 1) >= 2:
        return False

    changed = False

    # Migrate fixed_desires
    for desire_config in data.get("fixed_desires", {}).values():
        if not isinstance(desire_config, dict):
            continue

        # Sentence migration: medium→steady, high→rising, add settling
        sentence = desire_config.get("sentence", {})
        if isinstance(sentence, dict):
            if "medium" in sentence or "high" in sentence:
                new_sentence: dict[str, str] = {
                    "rising": sentence.pop("high", ""),
                    "steady": sentence.pop("medium", ""),
                    "settling": sentence.get("settling", ""),
                }
                desire_config["sentence"] = new_sentence
                changed = True
            elif "settling" not in sentence:
                sentence["settling"] = ""
                changed = True

        # Add satisfaction_signals if missing
        if "satisfaction_signals" not in desire_config:
            desire_config["satisfaction_signals"] = []
            changed = True

        # Rename tool references in implicit_satisfaction
        implicit = desire_config.get("implicit_satisfaction", {})
        if isinstance(implicit, dict):
            for old_name, new_name in _TOOL_RENAMES.items():
                if old_name in implicit:
                    value = implicit.pop(old_name)
                    implicit[new_name] = value
                    changed = True

    # Rename tool references in implicit_rules
    for rule in data.get("implicit_rules", []):
        if isinstance(rule, dict):
            tool = rule.get("tool", "")
            if tool in _TOOL_RENAMES:
                rule["tool"] = _TOOL_RENAMES[tool]
                changed = True

    # Update version
    if data.get("version", 1) != 2:
        data["version"] = 2
        changed = True

    return changed


def up(data_dir: Path) -> None:
    """Migrate settings/desires.json from v1 to v2."""
    catalog_path = data_dir / "settings" / "desires.json"
    if not catalog_path.exists():
        return

    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    if not isinstance(payload, dict):
        return

    if not migrate_catalog_v1_to_v2(payload):
        return

    # Create backup
    backup_path = catalog_path.parent / _BACKUP_FILENAME
    if not backup_path.exists():
        original_text = catalog_path.read_text(encoding="utf-8")
        backup_path.write_text(original_text, encoding="utf-8")

    catalog_path.write_text(
        json.dumps(cast(dict[str, Any], payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
