"""Tests for migration framework."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

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


class TestDesireCatalogV2Migration:
    """Tests for 0007_desire_catalog_v2 migration."""

    @pytest.fixture
    def migration_mod(self) -> object:
        return __import__(
            "ego_mcp.migrations.0007_desire_catalog_v2",
            fromlist=["up", "migrate_catalog_v1_to_v2"],
        )

    def _catalog_path(self, data_dir: Path) -> Path:
        return data_dir / "settings" / "desires.json"

    def _write_catalog(self, data_dir: Path, payload: dict[str, Any]) -> None:
        path = self._catalog_path(data_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _read_catalog(self, data_dir: Path) -> dict[str, Any]:
        result: dict[str, Any] = json.loads(self._catalog_path(data_dir).read_text(encoding="utf-8"))
        return result

    def test_medium_becomes_steady_and_high_becomes_rising(
        self, tmp_path: Path, migration_mod: object
    ) -> None:
        self._write_catalog(tmp_path, {
            "version": 1,
            "fixed_desires": {
                "curiosity": {
                    "satisfaction_hours": 18.0,
                    "maslow_level": 4,
                    "sentence": {
                        "medium": "A quiet wondering.",
                        "high": "Something caught your attention.",
                    },
                    "implicit_satisfaction": {},
                }
            },
            "emergent": {"satisfaction_hours": 24.0, "expiry_hours": 72.0, "satisfied_ttl_hours": 168.0},
        })

        migration_mod.up(tmp_path)  # type: ignore[attr-defined]

        result = self._read_catalog(tmp_path)
        sentence = result["fixed_desires"]["curiosity"]["sentence"]
        assert sentence["steady"] == "A quiet wondering."
        assert sentence["rising"] == "Something caught your attention."
        assert sentence["settling"] == ""
        assert "medium" not in sentence
        assert "high" not in sentence

    def test_settling_placeholder_is_empty_string(
        self, tmp_path: Path, migration_mod: object
    ) -> None:
        self._write_catalog(tmp_path, {
            "version": 1,
            "fixed_desires": {
                "curiosity": {
                    "satisfaction_hours": 18.0,
                    "maslow_level": 4,
                    "sentence": {"medium": "m", "high": "h"},
                    "implicit_satisfaction": {},
                }
            },
            "emergent": {"satisfaction_hours": 24.0, "expiry_hours": 72.0, "satisfied_ttl_hours": 168.0},
        })

        migration_mod.up(tmp_path)  # type: ignore[attr-defined]

        result = self._read_catalog(tmp_path)
        assert result["fixed_desires"]["curiosity"]["sentence"]["settling"] == ""

    def test_satisfaction_signals_default_empty_list(
        self, tmp_path: Path, migration_mod: object
    ) -> None:
        self._write_catalog(tmp_path, {
            "version": 1,
            "fixed_desires": {
                "curiosity": {
                    "satisfaction_hours": 18.0,
                    "maslow_level": 4,
                    "sentence": {"medium": "m", "high": "h"},
                    "implicit_satisfaction": {},
                }
            },
            "emergent": {"satisfaction_hours": 24.0, "expiry_hours": 72.0, "satisfied_ttl_hours": 168.0},
        })

        migration_mod.up(tmp_path)  # type: ignore[attr-defined]

        result = self._read_catalog(tmp_path)
        assert result["fixed_desires"]["curiosity"]["satisfaction_signals"] == []

    def test_implicit_satisfaction_tool_rename(
        self, tmp_path: Path, migration_mod: object
    ) -> None:
        self._write_catalog(tmp_path, {
            "version": 1,
            "fixed_desires": {
                "pattern_seeking": {
                    "satisfaction_hours": 72.0,
                    "maslow_level": 2,
                    "sentence": {"medium": "m", "high": "h"},
                    "implicit_satisfaction": {"emotion_trend": 0.3, "introspect": 0.2},
                }
            },
            "emergent": {"satisfaction_hours": 24.0, "expiry_hours": 72.0, "satisfied_ttl_hours": 168.0},
        })

        migration_mod.up(tmp_path)  # type: ignore[attr-defined]

        result = self._read_catalog(tmp_path)
        implicit = result["fixed_desires"]["pattern_seeking"]["implicit_satisfaction"]
        assert "attune" in implicit
        assert implicit["attune"] == 0.3
        assert "emotion_trend" not in implicit
        assert implicit["introspect"] == 0.2

    def test_implicit_satisfaction_feel_desires_renamed(
        self, tmp_path: Path, migration_mod: object
    ) -> None:
        self._write_catalog(tmp_path, {
            "version": 1,
            "fixed_desires": {
                "curiosity": {
                    "satisfaction_hours": 18.0,
                    "maslow_level": 4,
                    "sentence": {"medium": "m", "high": "h"},
                    "implicit_satisfaction": {"feel_desires": 0.5},
                }
            },
            "emergent": {"satisfaction_hours": 24.0, "expiry_hours": 72.0, "satisfied_ttl_hours": 168.0},
        })

        migration_mod.up(tmp_path)  # type: ignore[attr-defined]

        result = self._read_catalog(tmp_path)
        implicit = result["fixed_desires"]["curiosity"]["implicit_satisfaction"]
        assert "attune" in implicit
        assert "feel_desires" not in implicit

    def test_implicit_rules_tool_rename(
        self, tmp_path: Path, migration_mod: object
    ) -> None:
        self._write_catalog(tmp_path, {
            "version": 1,
            "fixed_desires": {},
            "implicit_rules": [
                {
                    "tool": "emotion_trend",
                    "effects": [{"id": "pattern_seeking", "quality": 0.3}],
                },
                {
                    "tool": "remember",
                    "when": {"category": "introspection"},
                    "effects": [{"id": "cognitive_coherence", "quality": 0.4}],
                },
            ],
            "emergent": {"satisfaction_hours": 24.0, "expiry_hours": 72.0, "satisfied_ttl_hours": 168.0},
        })

        migration_mod.up(tmp_path)  # type: ignore[attr-defined]

        result = self._read_catalog(tmp_path)
        assert result["implicit_rules"][0]["tool"] == "attune"
        assert result["implicit_rules"][1]["tool"] == "remember"

    def test_version_updated_to_2(
        self, tmp_path: Path, migration_mod: object
    ) -> None:
        self._write_catalog(tmp_path, {
            "version": 1,
            "fixed_desires": {},
            "emergent": {"satisfaction_hours": 24.0, "expiry_hours": 72.0, "satisfied_ttl_hours": 168.0},
        })

        migration_mod.up(tmp_path)  # type: ignore[attr-defined]

        result = self._read_catalog(tmp_path)
        assert result["version"] == 2

    def test_idempotent_when_already_v2(
        self, tmp_path: Path, migration_mod: object
    ) -> None:
        v2_catalog = {
            "version": 2,
            "fixed_desires": {
                "curiosity": {
                    "satisfaction_hours": 18.0,
                    "maslow_level": 4,
                    "sentence": {"rising": "r", "steady": "s", "settling": "t"},
                    "implicit_satisfaction": {},
                    "satisfaction_signals": ["finding an answer"],
                }
            },
            "emergent": {"satisfaction_hours": 24.0, "expiry_hours": 72.0, "satisfied_ttl_hours": 168.0},
        }
        self._write_catalog(tmp_path, v2_catalog)

        migration_mod.up(tmp_path)  # type: ignore[attr-defined]

        result = self._read_catalog(tmp_path)
        assert result == v2_catalog

    def test_noop_when_catalog_file_missing(
        self, tmp_path: Path, migration_mod: object
    ) -> None:
        # No desires.json at all
        migration_mod.up(tmp_path)  # type: ignore[attr-defined]
        assert not self._catalog_path(tmp_path).exists()

    def test_backup_created(
        self, tmp_path: Path, migration_mod: object
    ) -> None:
        self._write_catalog(tmp_path, {
            "version": 1,
            "fixed_desires": {
                "curiosity": {
                    "satisfaction_hours": 18.0,
                    "maslow_level": 4,
                    "sentence": {"medium": "m", "high": "h"},
                    "implicit_satisfaction": {},
                }
            },
            "emergent": {"satisfaction_hours": 24.0, "expiry_hours": 72.0, "satisfied_ttl_hours": 168.0},
        })

        migration_mod.up(tmp_path)  # type: ignore[attr-defined]

        backup_path = tmp_path / "settings" / "desires.pre_0007_catalog_v2.json"
        assert backup_path.exists()
        backup = json.loads(backup_path.read_text(encoding="utf-8"))
        assert backup["version"] == 1


class TestEmergentDesireIdMigration:
    def test_run_migrations_applies_0006_to_existing_desire_state(
        self,
        tmp_path: Path,
    ) -> None:
        state_path = tmp_path / "desire_state.json"
        state_path.write_text(
            json.dumps(
                {
                    "You want to feel safe.": {
                        "last_satisfied": "",
                        "satisfaction_quality": 0.5,
                        "boost": 0.0,
                        "is_emergent": True,
                        "created": "2024-01-01T00:00:00+00:00",
                        "satisfaction_hours": 24.0,
                    }
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        applied = migrations_mod.run_migrations(tmp_path)

        payload = json.loads(state_path.read_text(encoding="utf-8"))
        assert "0006_emergent_desire_ids" in applied
        assert "feel_safe" in payload
        assert "You want to feel safe." not in payload

    def test_0006_normalizes_legacy_emergent_labels_and_creates_backup(
        self,
        tmp_path: Path,
    ) -> None:
        migration_mod = __import__(
            "ego_mcp.migrations.0006_emergent_desire_ids",
            fromlist=["up"],
        )
        state_path = tmp_path / "desire_state.json"
        state_path.write_text(
            json.dumps(
                {
                    "curiosity": {"satisfaction_quality": 0.8, "is_emergent": False},
                    "You want to grasp something.": {
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

        payload = json.loads(state_path.read_text(encoding="utf-8"))
        backup_path = tmp_path / "desire_state.pre_0006_emergent_desire_ids.json"
        backup_payload = json.loads(backup_path.read_text(encoding="utf-8"))
        assert "grasp_something" in payload
        assert "You want to grasp something." not in payload
        assert payload["grasp_something"]["created"] == "2024-01-01T00:00:00+00:00"
        assert "You want to grasp something." in backup_payload

    def test_0006_is_idempotent_when_state_is_already_normalized(
        self,
        tmp_path: Path,
    ) -> None:
        migration_mod = __import__(
            "ego_mcp.migrations.0006_emergent_desire_ids",
            fromlist=["up"],
        )
        state_path = tmp_path / "desire_state.json"
        state_path.write_text(
            json.dumps(
                {
                    "grasp_something": {
                        "last_satisfied": "",
                        "satisfaction_quality": 0.5,
                        "boost": 0.0,
                        "is_emergent": True,
                        "created": "2024-01-01T00:00:00+00:00",
                        "satisfaction_hours": 24.0,
                    }
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        migration_mod.up(tmp_path)

        payload = json.loads(state_path.read_text(encoding="utf-8"))
        assert payload == {
            "grasp_something": {
                "last_satisfied": "",
                "satisfaction_quality": 0.5,
                "boost": 0.0,
                "is_emergent": True,
                "created": "2024-01-01T00:00:00+00:00",
                "satisfaction_hours": 24.0,
            }
        }
        assert not (
            tmp_path / "desire_state.pre_0006_emergent_desire_ids.json"
        ).exists()

    def test_0006_prefers_existing_canonical_entry_on_collision(
        self,
        tmp_path: Path,
    ) -> None:
        migration_mod = __import__(
            "ego_mcp.migrations.0006_emergent_desire_ids",
            fromlist=["up"],
        )
        state_path = tmp_path / "desire_state.json"
        state_path.write_text(
            json.dumps(
                {
                    "grasp_something": {
                        "last_satisfied": "2024-02-01T00:00:00+00:00",
                        "satisfaction_quality": 0.9,
                        "boost": 0.0,
                        "is_emergent": True,
                        "created": "2024-02-01T00:00:00+00:00",
                        "satisfaction_hours": 24.0,
                    },
                    "You want to grasp something.": {
                        "last_satisfied": "",
                        "satisfaction_quality": 0.2,
                        "boost": 0.4,
                        "is_emergent": True,
                        "created": "2024-01-01T00:00:00+00:00",
                        "satisfaction_hours": 48.0,
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        migration_mod.up(tmp_path)

        payload = json.loads(state_path.read_text(encoding="utf-8"))
        assert payload["grasp_something"]["satisfaction_quality"] == 0.9
        assert payload["grasp_something"]["satisfaction_hours"] == 24.0
        assert "You want to grasp something." not in payload
