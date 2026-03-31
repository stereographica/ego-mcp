from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from ego_dashboard.desire_catalog import (
    LEGACY_FIXED_DESIRE_IDS,
    default_desire_catalog,
    load_desire_catalog,
)


def _write_catalog(tmp_path: Path, payload: object) -> None:
    settings_dir = tmp_path / "settings"
    settings_dir.mkdir()
    (settings_dir / "desires.json").write_text(json.dumps(payload), encoding="utf-8")


def test_load_desire_catalog_reads_fixed_desires_from_settings_file(tmp_path: Path) -> None:
    _write_catalog(
        tmp_path,
        {
            "version": 1,
            "fixed_desires": {
                "social_thirst": {
                    "display_name": "Social Thirst",
                    "satisfaction_hours": 24,
                    "maslow_level": 1,
                    "sentence": {
                        "medium": "You want some company.",
                        "high": "You need to talk to someone.",
                    },
                    "implicit_satisfaction": {"consider_them": 0.4},
                },
                "custom_focus": {
                    "display_name": "Custom Focus",
                    "satisfaction_hours": 8,
                    "maslow_level": 2,
                    "sentence": {
                        "medium": "You want to focus.",
                        "high": "You urgently need to focus.",
                    },
                    "implicit_satisfaction": {"recall": 0.2},
                },
            },
            "implicit_rules": [],
            "emergent": {"satisfaction_hours": 24},
        },
    )

    catalog = load_desire_catalog(str(tmp_path))

    assert catalog.status == "ok"
    assert [item.id for item in catalog.fixed_desires] == [
        "social_thirst",
        "custom_focus",
    ]
    assert catalog.fixed_ids == {"social_thirst", "custom_focus"}


def test_load_desire_catalog_returns_invalid_status_for_broken_json(tmp_path: Path) -> None:
    settings_dir = tmp_path / "settings"
    settings_dir.mkdir()
    (settings_dir / "desires.json").write_text("{broken", encoding="utf-8")

    catalog = load_desire_catalog(str(tmp_path))

    assert catalog.status == "invalid"
    assert catalog.fixed_desires == ()
    assert catalog.errors


def test_load_desire_catalog_returns_missing_status_when_settings_file_absent(
    tmp_path: Path,
) -> None:
    catalog = load_desire_catalog(str(tmp_path))

    assert catalog.status == "missing"
    assert catalog.fixed_desires == ()
    assert catalog.errors


def test_default_desire_catalog_uses_legacy_fixed_desires() -> None:
    catalog = default_desire_catalog()

    assert catalog.status == "unconfigured"
    assert catalog.version == 1
    assert catalog.source_path is None
    assert catalog.fixed_ids == set(LEGACY_FIXED_DESIRE_IDS)


def test_load_desire_catalog_serializes_sorted_response(tmp_path: Path) -> None:
    _write_catalog(
        tmp_path,
        {
            "version": 1,
            "fixed_desires": {
                "zeta": {
                    "display_name": "Zeta",
                    "satisfaction_hours": 12,
                    "maslow_level": 2,
                    "sentence": {
                        "medium": "You want something later.",
                        "high": "You urgently want something later.",
                    },
                    "implicit_satisfaction": {"recall": 0.1},
                },
                "alpha": {
                    "display_name": "Alpha",
                    "satisfaction_hours": 6,
                    "maslow_level": 1,
                    "sentence": {
                        "medium": "You want something first.",
                        "high": "You urgently want something first.",
                    },
                    "implicit_satisfaction": {"remember": 0.2},
                },
            },
            "implicit_rules": [{"tool": "remember", "when": {"category": "introspection"}}],
            "emergent": {"satisfaction_hours": 24, "expiry_hours": 72},
        },
    )

    catalog = load_desire_catalog(str(tmp_path))
    response = catalog.to_response()

    assert catalog.status == "ok"
    assert response["version"] == 1
    assert response["status"] == "ok"
    assert response["source_path"] == str(tmp_path / "settings" / "desires.json")
    fixed_desires = cast(list[dict[str, object]], response["fixed_desires"])
    assert [item["id"] for item in fixed_desires] == ["alpha", "zeta"]
    assert response["implicit_rules"] == [
        {"tool": "remember", "when": {"category": "introspection"}}
    ]
    assert response["emergent"] == {"satisfaction_hours": 24, "expiry_hours": 72}


def test_load_desire_catalog_reports_schema_errors_for_invalid_payload(tmp_path: Path) -> None:
    _write_catalog(
        tmp_path,
        {
            "version": "one",
            "fixed_desires": {
                "custom_focus": {
                    "display_name": "",
                    "satisfaction_hours": "fast",
                    "maslow_level": 1.5,
                    "sentence": {"medium": "", "high": None},
                    "implicit_satisfaction": ["remember"],
                }
            },
            "implicit_rules": "not-a-list",
            "emergent": [],
        },
    )

    catalog = load_desire_catalog(str(tmp_path))

    assert catalog.status == "invalid"
    assert catalog.fixed_desires == ()
    assert "version must be an integer" in catalog.errors
    assert "implicit_rules must be an array" in catalog.errors
    assert "emergent must be an object" in catalog.errors
    assert any(
        error == "fixed_desires.custom_focus.display_name must be a non-empty string"
        for error in catalog.errors
    )
    assert any(
        error == "fixed_desires.custom_focus.satisfaction_hours must be numeric"
        for error in catalog.errors
    )
    assert any(
        error == "fixed_desires.custom_focus.maslow_level must be an integer"
        for error in catalog.errors
    )
    assert any(
        error == "fixed_desires.custom_focus.sentence.medium must be a string"
        for error in catalog.errors
    )
    assert any(
        error == "fixed_desires.custom_focus.sentence.high must be a string"
        for error in catalog.errors
    )
    assert any(
        error == "fixed_desires.custom_focus.implicit_satisfaction must be an object"
        for error in catalog.errors
    )


def test_desire_catalog_visibility_and_split_filter_reserved_and_legacy_metrics() -> None:
    from ego_dashboard.desire_catalog import DesireCatalog, DesireCatalogItem

    catalog = DesireCatalog(
        version=1,
        fixed_desires=(
            DesireCatalogItem(
                id="social_thirst",
                display_name="Social Thirst",
                satisfaction_hours=24.0,
                maslow_level=1,
            ),
            DesireCatalogItem(
                id="custom_focus",
                display_name="Custom Focus",
                satisfaction_hours=8.0,
                maslow_level=2,
            ),
        ),
    )

    fixed, emergent = catalog.split_desire_metrics(
        {
            "social_thirst": 0.4,
            "custom_focus": 0.9,
            "predictability": 0.6,
            "novel_interest": 0.7,
            "impulse_boost_amount": 0.15,
            "tool_output_chars": 387.0,
            "intensity": 0.5,
        }
    )

    assert catalog.is_visible_desire_metric("social_thirst") is True
    assert catalog.is_visible_desire_metric("custom_focus") is True
    assert catalog.is_visible_desire_metric("predictability") is False
    assert catalog.is_visible_desire_metric("novel_interest") is True
    assert catalog.is_visible_desire_metric("impulse_boost_amount") is False
    assert catalog.is_visible_desire_metric("tool_output_chars") is False
    assert fixed == {"social_thirst": 0.4, "custom_focus": 0.9}
    assert emergent == {"novel_interest": 0.7}
