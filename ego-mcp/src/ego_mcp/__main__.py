"""Entry point for ego-mcp server."""

import asyncio
import logging

from ego_mcp.logging_utils import configure_logging, install_global_exception_hooks
from ego_mcp.server import main

if __name__ == "__main__":
    log_path = configure_logging()
    install_global_exception_hooks()
    logging.getLogger(__name__).info(
        "Logging initialized",
        extra={"log_path": str(log_path)},
    )
    try:
        asyncio.run(main())
    except Exception:
        logging.getLogger(__name__).exception(
            "ego-mcp server terminated with an unhandled exception"
        )
        raise
