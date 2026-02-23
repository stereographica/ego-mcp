"""Data-file migration framework for ego-mcp."""

from __future__ import annotations

import importlib
import json
import logging
import re
from pathlib import Path
from types import ModuleType
from typing import Callable, cast

logger = logging.getLogger(__name__)

_MIGRATION_FILENAME_PATTERN = re.compile(r"^[0-9]{4}_.+\.py$")
_MIGRATIONS_DIR = Path(__file__).parent
_MIGRATION_PACKAGE = __name__

MigrationFunc = Callable[[Path], None]


class MigrationRunner:
    """Run ordered file-based migrations for ego-mcp data files."""

    def __init__(
        self,
        migrations_dir: Path | None = None,
        migration_package: str | None = None,
    ) -> None:
        self._migrations_dir = migrations_dir or _MIGRATIONS_DIR
        self._migration_package = migration_package or _MIGRATION_PACKAGE

    def run_migrations(self, data_dir: Path) -> list[str]:
        """Apply unapplied migrations in filename order."""
        state_path = data_dir / "migration_state.json"
        applied = self._load_applied(state_path)
        applied_set = set(applied)
        newly_applied: list[str] = []

        importlib.invalidate_caches()
        for migration_name in self._discover_migration_names():
            if migration_name in applied_set:
                continue

            loaded = self._load_migration(migration_name)
            if loaded is None:
                continue

            target_version, up = loaded
            logger.info("Applying migration: %s (target: %s)", migration_name, target_version)
            up(data_dir)
            applied.append(migration_name)
            applied_set.add(migration_name)
            newly_applied.append(migration_name)
            self._save_applied(state_path, applied)

        logger.info("Applied %d migration(s): %s", len(newly_applied), newly_applied)
        return newly_applied

    def _discover_migration_names(self) -> list[str]:
        if not self._migrations_dir.exists():
            return []

        names = [
            path.stem
            for path in self._migrations_dir.iterdir()
            if path.is_file() and _MIGRATION_FILENAME_PATTERN.match(path.name)
        ]
        names.sort()
        return names

    def _load_migration(self, migration_name: str) -> tuple[str, MigrationFunc] | None:
        module_name = f"{self._migration_package}.{migration_name}"
        module = importlib.import_module(module_name)
        target_version = getattr(module, "TARGET_VERSION", None)
        if not isinstance(target_version, str):
            logger.warning(
                "Skipping migration %s: TARGET_VERSION is missing or not str",
                migration_name,
            )
            return None

        up = self._get_up_function(module, migration_name)
        if up is None:
            return None

        return target_version, up

    def _get_up_function(
        self, module: ModuleType, migration_name: str
    ) -> MigrationFunc | None:
        up = getattr(module, "up", None)
        if not callable(up):
            logger.warning("Skipping migration %s: up(data_dir) is missing", migration_name)
            return None
        return cast(MigrationFunc, up)

    def _load_applied(self, state_path: Path) -> list[str]:
        if not state_path.exists():
            return []

        try:
            with open(state_path, encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError):
            logger.warning(
                "Failed to read migration state %s; treating as empty state",
                state_path,
            )
            return []

        applied = payload.get("applied", [])
        if not isinstance(applied, list):
            return []
        return [name for name in applied if isinstance(name, str)]

    def _save_applied(self, state_path: Path, applied: list[str]) -> None:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"applied": applied}
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)


def run_migrations(data_dir: Path) -> list[str]:
    """Run all data-file migrations for the given data directory."""
    return MigrationRunner().run_migrations(data_dir)
