"""Release marker migration for v0.4.3."""

from __future__ import annotations

from pathlib import Path

TARGET_VERSION = "0.4.3"


def up(data_dir: Path) -> None:
    """No-op release marker for v0.4.3."""
    del data_dir
