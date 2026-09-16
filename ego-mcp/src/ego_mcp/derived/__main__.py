"""``python -m ego_mcp.derived`` entry point."""

from __future__ import annotations

import sys

from ego_mcp.derived.cli import main

if __name__ == "__main__":
    sys.exit(main())
