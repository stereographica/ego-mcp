"""Nightly batch entry point (D0 S7): ``python -m ego_mcp.derived``.

Exit codes:
    0  every selected lens succeeded
    1  bad arguments (unknown lens name, bad configuration)
    2  the snapshot could not be taken (nothing was written)
    3  at least one lens failed (the others were still written)
"""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ego_mcp import timezone_utils
from ego_mcp.derived.config import DerivedConfig
from ego_mcp.derived.contract import DerivedFile, write_lens_file
from ego_mcp.derived.lenses import LENSES, Lens, discover_lenses, lens_stats
from ego_mcp.derived.source import SnapshotUnavailable, SourceSnapshot, load_snapshot
from ego_mcp.logging_utils import configure_logging

logger = logging.getLogger("ego_mcp.derived")

EXIT_OK = 0
EXIT_BAD_ARGS = 1
EXIT_NO_SNAPSHOT = 2
EXIT_LENS_FAILED = 3

DRY_RUN_KEY_PREVIEW = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ego_mcp.derived",
        description="Compute the derived layer (batch). Writes nothing to the primary stores.",
    )
    parser.add_argument(
        "--lens",
        default="",
        help="Comma-separated lens names to run (default: all registered lenses).",
    )
    parser.add_argument(
        "--data-dir",
        default="",
        help="Override EGO_MCP_DATA_DIR.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute only; print counts and the first key(s) and write nothing.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_lenses",
        help="List registered lenses and exit.",
    )
    return parser


def _select_lenses(requested: str) -> tuple[list[Lens], str | None]:
    """Resolve ``--lens`` into lens objects, or return an error message."""
    if not requested.strip():
        return list(LENSES.values()), None
    names = [name.strip() for name in requested.split(",") if name.strip()]
    if not names:
        return list(LENSES.values()), None
    selected: list[Lens] = []
    for name in names:
        lens = LENSES.get(name)
        if lens is None:
            known = ", ".join(sorted(LENSES)) or "(none registered)"
            return [], f"Unknown lens: '{name}'. Registered lenses: {known}"
        selected.append(lens)
    return selected, None


def _run_lens(
    lens: Lens,
    snapshot: SourceSnapshot,
    data_dir: Path,
    *,
    dry_run: bool,
) -> bool:
    """Compute and (unless dry-run) write one lens. Returns success."""
    started = time.monotonic()
    try:
        items = lens.compute(snapshot)
    except Exception:
        logger.error(
            "Derived lens failed",
            exc_info=True,
            extra={
                "lens": lens.name,
                "duration_ms": int((time.monotonic() - started) * 1000),
                "memory_count": snapshot.memory_count,
                "embedding_count": snapshot.embedding_count,
            },
        )
        return False

    duration_ms = int((time.monotonic() - started) * 1000)

    if dry_run:
        preview = ", ".join(
            str(item.get("key", "")) for item in items[:DRY_RUN_KEY_PREVIEW]
        )
        print(f"{lens.name}: {len(items)} item(s)" + (f" [{preview}]" if preview else ""))
    else:
        valid_until = snapshot.now + timedelta(hours=float(lens.ttl_hours))
        write_lens_file(
            data_dir,
            DerivedFile(
                lens=lens.name,
                generated_at=snapshot.now.isoformat(),
                valid_until=valid_until.isoformat(),
                source=snapshot.source_stats(),
                items=items,
            ),
        )

    extra: dict[str, Any] = {
        "lens": lens.name,
        "item_count": len(items),
        "duration_ms": duration_ms,
        "memory_count": snapshot.memory_count,
        "embedding_count": snapshot.embedding_count,
    }
    extra.update(lens_stats(lens))
    logger.info("Derived lens completed", extra=extra)
    return True


def main(argv: Sequence[str] | None = None) -> int:
    """Run the derived batch. Returns the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    configure_logging()
    discover_lenses()

    if args.list_lenses:
        if not LENSES:
            print("No lenses registered.")
        for name, lens in LENSES.items():
            print(
                f"{name}\tneeds_embeddings={lens.needs_embeddings}"
                f"\tttl_hours={lens.ttl_hours}"
            )
        return EXIT_OK

    selected, error = _select_lenses(args.lens)
    if error is not None:
        parser.exit(status=EXIT_BAD_ARGS, message=f"{error}\n")

    try:
        config = DerivedConfig.from_env()
    except ValueError as exc:
        parser.exit(status=EXIT_BAD_ARGS, message=f"{exc}\n")

    data_dir = Path(args.data_dir) if args.data_dir.strip() else config.data_dir

    now: datetime = timezone_utils.now()
    needs_embeddings = any(lens.needs_embeddings for lens in selected)
    try:
        snapshot = load_snapshot(
            data_dir, with_embeddings=needs_embeddings, now=now
        )
    except SnapshotUnavailable:
        logger.error("Derived snapshot unavailable", exc_info=True)
        return EXIT_NO_SNAPSHOT

    failures = 0
    for lens in selected:
        if not _run_lens(lens, snapshot, data_dir, dry_run=bool(args.dry_run)):
            failures += 1

    return EXIT_LENS_FAILED if failures else EXIT_OK
