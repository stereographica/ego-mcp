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


class TestDesireStateSplitMigration:
    def test_0005_copies_legacy_state_to_new_location_and_filters_unknown_fixed(
        self,
        tmp_path: Path,
    ) -> None:
        migration_mod = __import__(
            "ego_mcp.migrations.0005_desire_state_split",
            fromlist=["up"],
        )
        legacy_path = tmp_path / "desires.json"
        legacy_path.write_text(
            json.dumps(
                {
                    "curiosity": {
                        "last_satisfied": "2024-01-01T00:00:00+00:00",
                        "satisfaction_quality": 0.8,
                        "boost": 0.1,
                        "is_emergent": False,
                        "created": "",
                    },
                    "legacy_fixed": {
                        "last_satisfied": "2024-01-01T00:00:00+00:00",
                        "satisfaction_quality": 0.5,
                        "boost": 0.0,
                        "is_emergent": False,
                        "created": "",
                    },
                    "You want to feel safe.": {
                        "last_satisfied": "",
                        "satisfaction_quality": 0.5,
                        "boost": 0.0,
                        "is_emergent": True,
                        "created": "2024-01-01T00:00:00+00:00",
                        "satisfaction_hours": 24.0,
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        migration_mod.up(tmp_path)

        new_payload = json.loads((tmp_path / "desire_state.json").read_text(encoding="utf-8"))
        assert "curiosity" in new_payload
        assert "legacy_fixed" not in new_payload
        assert "You want to feel safe." in new_payload
        assert json.loads(legacy_path.read_text(encoding="utf-8"))["curiosity"][
            "satisfaction_quality"
        ] == 0.8

    def test_0005_is_idempotent_when_new_state_already_exists(self, tmp_path: Path) -> None:
        migration_mod = __import__(
            "ego_mcp.migrations.0005_desire_state_split",
            fromlist=["up"],
        )
        (tmp_path / "desires.json").write_text(
            json.dumps({"curiosity": {"satisfaction_quality": 0.2}}),
            encoding="utf-8",
        )
        (tmp_path / "desire_state.json").write_text(
            json.dumps({"curiosity": {"satisfaction_quality": 0.9}}),
            encoding="utf-8",
        )

        migration_mod.up(tmp_path)

        payload = json.loads((tmp_path / "desire_state.json").read_text(encoding="utf-8"))
        assert payload["curiosity"]["satisfaction_quality"] == 0.9

    def test_0005_noops_for_invalid_legacy_json(self, tmp_path: Path) -> None:
        migration_mod = __import__(
            "ego_mcp.migrations.0005_desire_state_split",
            fromlist=["up"],
        )
        (tmp_path / "desires.json").write_text("{broken", encoding="utf-8")

        migration_mod.up(tmp_path)

        assert not (tmp_path / "desire_state.json").exists()

    def test_0005_noops_for_non_object_legacy_payload(self, tmp_path: Path) -> None:
        migration_mod = __import__(
            "ego_mcp.migrations.0005_desire_state_split",
            fromlist=["up"],
        )
        (tmp_path / "desires.json").write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

        migration_mod.up(tmp_path)

        assert not (tmp_path / "desire_state.json").exists()

    def test_0005_skips_non_string_or_non_object_entries(self, tmp_path: Path) -> None:
        migration_mod = __import__(
            "ego_mcp.migrations.0005_desire_state_split",
            fromlist=["up"],
        )
        (tmp_path / "desires.json").write_text(
            json.dumps(
                {
                    "curiosity": {"satisfaction_quality": 0.8, "is_emergent": False},
                    "bad_raw": "not-an-object",
                    "You want to feel safe.": {
                        "satisfaction_quality": 0.5,
                        "is_emergent": True,
                    },
                }
            ),
            encoding="utf-8",
        )

        migration_mod.up(tmp_path)

        payload = json.loads((tmp_path / "desire_state.json").read_text(encoding="utf-8"))
        assert set(payload.keys()) == {"curiosity", "You want to feel safe."}
