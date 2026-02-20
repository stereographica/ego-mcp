"""Entry point for ego-mcp server."""

import asyncio

from ego_mcp.server import main


if __name__ == "__main__":
    asyncio.run(main())
