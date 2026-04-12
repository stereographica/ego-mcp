"""Tests for configure_desires backend handler."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ego_mcp._server_backend_configure_desires import _handle_configure_desires
from ego_mcp.desire_catalog import (
    ensure_default_desire_catalog_file,
)


@pytest.fixture
def catalog_path(tmp_path: Path) -> Path:
    path = tmp_path / "settings" / "desires.json"
    ensure_default_desire_catalog_file(path)
    return path


class TestConfigureDesires:
    def test_show_all(self, catalog_path: Path) -> None:
        result = _handle_configure_desires(str(catalog_path), {"action": "show"})
        assert "Desire catalog (version 2):" in result
        assert "curiosity" in result

    def test_show_one(self, catalog_path: Path) -> None:
        result = _handle_configure_desires(
            str(catalog_path), {"action": "show", "desire_id": "curiosity"}
        )
        assert "Desire: curiosity" in result
        assert "sentence.rising:" in result
        assert "sentence.steady:" in result
        assert "sentence.settling:" in result

    def test_show_unknown_desire(self, catalog_path: Path) -> None:
        result = _handle_configure_desires(
            str(catalog_path), {"action": "show", "desire_id": "nonexistent"}
        )
        assert "Unknown desire: nonexistent" in result

    def test_check_all_configured(self, catalog_path: Path) -> None:
        result = _handle_configure_desires(str(catalog_path), {"action": "check"})
        assert "All desires are fully configured." in result

    def test_check_incomplete_settling(self, catalog_path: Path) -> None:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        payload["fixed_desires"]["curiosity"]["sentence"]["settling"] = ""
        catalog_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        result = _handle_configure_desires(str(catalog_path), {"action": "check"})
        assert "curiosity: missing settling sentence" in result

    def test_set_sentence(self, catalog_path: Path) -> None:
        result = _handle_configure_desires(
            str(catalog_path),
            {
                "action": "set_sentence",
                "desire_id": "curiosity",
                "direction": "settling",
                "sentence": "New settling text.",
            },
        )
        assert "Updated curiosity.sentence.settling" in result
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        assert payload["fixed_desires"]["curiosity"]["sentence"]["settling"] == "New settling text."

    def test_set_sentence_missing_params(self, catalog_path: Path) -> None:
        result = _handle_configure_desires(
            str(catalog_path),
            {"action": "set_sentence", "desire_id": "curiosity"},
        )
        assert "requires" in result

    def test_set_signals(self, catalog_path: Path) -> None:
        result = _handle_configure_desires(
            str(catalog_path),
            {
                "action": "set_signals",
                "desire_id": "curiosity",
                "signals": ["finding an answer", "exploring something unknown"],
            },
        )
        assert "Updated curiosity.satisfaction_signals" in result
        assert "2 signal(s)" in result

    def test_set_signals_missing_params(self, catalog_path: Path) -> None:
        result = _handle_configure_desires(
            str(catalog_path),
            {"action": "set_signals", "desire_id": "curiosity"},
        )
        assert "requires" in result

    def test_unknown_action(self, catalog_path: Path) -> None:
        result = _handle_configure_desires(
            str(catalog_path), {"action": "frobnicate"}
        )
        assert "Unknown action: frobnicate" in result

    def test_set_sentence_unknown_desire(self, catalog_path: Path) -> None:
        result = _handle_configure_desires(
            str(catalog_path),
            {
                "action": "set_sentence",
                "desire_id": "nonexistent",
                "direction": "rising",
                "sentence": "test",
            },
        )
        assert "Unknown desire: nonexistent" in result
