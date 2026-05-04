"""Migration 0009: Add meta_fields to Notion.

Adds empty meta_fields dict to all existing notions.
Supports both the legacy {"notions": [...]} format and the
current flat dict format keyed by notion ID.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

TARGET_VERSION = "1.2.0"


def up(data_dir: Path) -> None:
    """Add meta_fields to existing notions."""
    notions_path = data_dir / "notions.json"

    if not notions_path.exists():
        return

    try:
        data = json.loads(notions_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    if not isinstance(data, dict):
        return

    updated_count = 0

    # Handle legacy {"notions": [...]} format: convert to flat dict
    notions_list = data.get("notions")
    if isinstance(notions_list, list):
        flat: dict[str, dict[str, object]] = {}
        for notion in notions_list:
            if not isinstance(notion, dict):
                continue
            notion_id = notion.get("id", "")
            if not notion_id:
                continue
            if "meta_fields" not in notion:
                notion["meta_fields"] = {}
                updated_count += 1
            flat[str(notion_id)] = notion
        data = flat
    else:
        # Handle current flat dict format keyed by notion ID
        for notion_id, notion in data.items():
            if not isinstance(notion, dict):
                continue
            if notion_id.startswith("_") or notion_id == "version":
                continue
            if "meta_fields" not in notion:
                notion["meta_fields"] = {}
                updated_count += 1

    if updated_count == 0:
        return

    notions_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    logger.info("Migration 0009: added meta_fields to %d notion(s)", updated_count)
