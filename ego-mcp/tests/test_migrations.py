"""Tests for migration framework."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from ego_mcp import migrations as migrations_mod


def _make_temp_migration_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[str, Path]:
    package_name = f"test_migration_pkg_{uuid.uuid4().hex[:8]}"
    package_dir = tmp_path / package_name
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text('"""temp migration package"""', encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(migrations_mod, "_MIGRATION_PACKAGE", package_name)
    monkeypatch.setattr(migrations_mod, "_MIGRATIONS_DIR", package_dir)
    return package_name, package_dir


def _write_migration(
    package_dir: Path,
    filename: str,
    body: str,
) -> None:
    (package_dir / filename).write_text(body, encoding="utf-8")


class TestRunMigrations:
    def test_runs_unapplied_migrations_and_updates_state(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _package_name, package_dir = _make_temp_migration_package(tmp_path, monkeypatch)
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        _write_migration(
            package_dir,
            "0002_first.py",
            """
from pathlib import Path

TARGET_VERSION = "0.2.0"

def up(data_dir: Path) -> None:
    (data_dir / "0002.txt").write_text("ran", encoding="utf-8")
""".strip(),
        )
        _write_migration(
            package_dir,
            "0003_second.py",
            """
from pathlib import Path

TARGET_VERSION = "0.2.0"

def up(data_dir: Path) -> None:
    (data_dir / "0003.txt").write_text("ran", encoding="utf-8")
""".strip(),
        )

        applied = migrations_mod.run_migrations(data_dir)

        assert applied == ["0002_first", "0003_second"]
        assert (data_dir / "0002.txt").read_text(encoding="utf-8") == "ran"
        assert (data_dir / "0003.txt").read_text(encoding="utf-8") == "ran"
        state = json.loads((data_dir / "migration_state.json").read_text(encoding="utf-8"))
        assert state == {"applied": ["0002_first", "0003_second"]}

    def test_skips_already_applied_migration(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _package_name, package_dir = _make_temp_migration_package(tmp_path, monkeypatch)
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "migration_state.json").write_text(
            json.dumps({"applied": ["0002_first"]}),
            encoding="utf-8",
        )

        _write_migration(
            package_dir,
            "0002_first.py",
            """
from pathlib import Path

TARGET_VERSION = "0.2.0"

def up(data_dir: Path) -> None:
    (data_dir / "should_not_exist.txt").write_text("ran", encoding="utf-8")
""".strip(),
        )

        applied = migrations_mod.run_migrations(data_dir)

        assert applied == []
        assert not (data_dir / "should_not_exist.txt").exists()
        state = json.loads((data_dir / "migration_state.json").read_text(encoding="utf-8"))
        assert state == {"applied": ["0002_first"]}

    def test_first_run_works_without_state_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _package_name, package_dir = _make_temp_migration_package(tmp_path, monkeypatch)
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        _write_migration(
            package_dir,
            "0002_first.py",
            """
from pathlib import Path

TARGET_VERSION = "0.2.0"

def up(data_dir: Path) -> None:
    (data_dir / "ok.txt").write_text("ok", encoding="utf-8")
""".strip(),
        )

        assert not (data_dir / "migration_state.json").exists()

        applied = migrations_mod.run_migrations(data_dir)

        assert applied == ["0002_first"]
        assert (data_dir / "migration_state.json").exists()

    def test_skips_migration_without_target_version_and_warns(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _package_name, package_dir = _make_temp_migration_package(tmp_path, monkeypatch)
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        _write_migration(
            package_dir,
            "0002_missing_target.py",
            """
from pathlib import Path

def up(data_dir: Path) -> None:
    (data_dir / "should_not_exist.txt").write_text("ran", encoding="utf-8")
""".strip(),
        )

        caplog.set_level("WARNING")
        applied = migrations_mod.run_migrations(data_dir)

        assert applied == []
        assert not (data_dir / "should_not_exist.txt").exists()
        assert "TARGET_VERSION" in caplog.text
        assert "0002_missing_target" in caplog.text

    def test_ignores_non_migration_filenames(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _package_name, package_dir = _make_temp_migration_package(tmp_path, monkeypatch)
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        _write_migration(
            package_dir,
            "helper.py",
            """
from pathlib import Path

TARGET_VERSION = "0.2.0"

def up(data_dir: Path) -> None:
    (data_dir / "helper.txt").write_text("ran", encoding="utf-8")
""".strip(),
        )

        applied = migrations_mod.run_migrations(data_dir)

        assert applied == []
        assert not (data_dir / "helper.txt").exists()
