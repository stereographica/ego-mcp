"""Configuration for the derived (batch) layer.

The derived batch runs in a separate process and never embeds anything, so it
must not require an API key. ``EgoConfig.from_env()`` raises when the provider
key is missing, hence this narrower configuration object which reads only the
two environment variables the batch actually needs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class DerivedConfig:
    """Immutable configuration for ``python -m ego_mcp.derived``.

    Environment variables:
        EGO_MCP_DATA_DIR: Data directory (default: ~/.ego-mcp/data)
        EGO_MCP_TIMEZONE: IANA timezone ID (default: "UTC")
    """

    data_dir: Path
    timezone: str

    @classmethod
    def from_env(cls) -> DerivedConfig:
        """Construct DerivedConfig from environment variables."""
        data_dir_str = os.environ.get(
            "EGO_MCP_DATA_DIR",
            str(Path.home() / ".ego-mcp" / "data"),
        )
        data_dir = Path(data_dir_str)

        timezone = os.environ.get("EGO_MCP_TIMEZONE", "UTC")
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(
                f"Invalid timezone '{timezone}' in EGO_MCP_TIMEZONE. "
                "Use an IANA timezone ID (e.g. 'UTC', 'Asia/Tokyo')."
            ) from exc

        return cls(data_dir=data_dir, timezone=timezone)
