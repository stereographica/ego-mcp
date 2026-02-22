"""Tests for SelfModelStore."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ego_mcp.self_model import SelfModelStore, _calculate_salience


class TestSelfModelStore:
    def test_get_default(self, tmp_path: Path) -> None:
        store = SelfModelStore(tmp_path / "self_model.json")
        model = store.get()
        assert model.confidence_calibration == 0.5
        assert model.unresolved_questions == []
        assert model.last_updated != ""

    def test_update_partial(self, tmp_path: Path) -> None:
        store = SelfModelStore(tmp_path / "self_model.json")
        model = store.update(
            {"confidence_calibration": 0.8, "current_goals": ["learn"]}
        )
        assert model.confidence_calibration == 0.8
        assert model.current_goals == ["learn"]
        assert model.last_updated != ""

    def test_add_question_and_resolve(self, tmp_path: Path) -> None:
        store = SelfModelStore(tmp_path / "self_model.json")
        qid = store.add_question("What should I prioritize?")
        model = store.get()
        assert qid.startswith("q_")
        assert model.unresolved_questions == ["What should I prioritize?"]

        resolved = store.resolve_question(qid)
        model_after = store.get()
        assert resolved is True
        assert model_after.unresolved_questions == []

    def test_add_question_stores_importance_and_created_at(self, tmp_path: Path) -> None:
        path = tmp_path / "self_model.json"
        store = SelfModelStore(path)
        qid = store.add_question("How should I pace learning?", importance=5)

        payload = json.loads(path.read_text(encoding="utf-8"))
        entry = next(item for item in payload["question_log"] if item["id"] == qid)
        assert entry["importance"] == 5
        assert entry["created_at"]

    def test_add_question_clamps_importance(self, tmp_path: Path) -> None:
        path = tmp_path / "self_model.json"
        store = SelfModelStore(path)
        qid = store.add_question("How urgent is this?", importance=99)
        payload = json.loads(path.read_text(encoding="utf-8"))
        entry = next(item for item in payload["question_log"] if item["id"] == qid)
        assert entry["importance"] == 5

    def test_persistence(self, tmp_path: Path) -> None:
        path = tmp_path / "self_model.json"
        store = SelfModelStore(path)
        store.update({"current_goals": ["maintain continuity"]})
        store.add_question("How can I improve focus?")

        reloaded = SelfModelStore(path)
        model = reloaded.get()
        assert model.current_goals == ["maintain continuity"]
        assert "How can I improve focus?" in model.unresolved_questions

    def test_corrupt_json_fallback(self, tmp_path: Path) -> None:
        path = tmp_path / "self_model.json"
        path.write_text("{broken", encoding="utf-8")
        store = SelfModelStore(path)
        model = store.get()
        assert model.unresolved_questions == []

    def test_legacy_question_entries_fallback_defaults(self, tmp_path: Path) -> None:
        path = tmp_path / "self_model.json"
        path.write_text(
            json.dumps(
                {
                    "question_log": [
                        {
                            "id": "q_legacy",
                            "question": "Legacy question without metadata",
                            "resolved": False,
                        }
                    ],
                    "unresolved_questions": ["q_legacy"],
                }
            ),
            encoding="utf-8",
        )
        store = SelfModelStore(path)
        active, resurfacing = store.get_visible_questions()
        assert resurfacing == []
        assert active
        assert active[0]["id"] == "q_legacy"
        assert active[0]["importance"] == 3
        assert active[0]["created_at"] == ""

    def test_get_visible_questions_classifies_active_fading_dormant(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "self_model.json"
        now = datetime.now(timezone.utc)
        path.write_text(
            json.dumps(
                {
                    "question_log": [
                        {
                            "id": "q_active",
                            "question": "Active question",
                            "resolved": False,
                            "importance": 5,
                            "created_at": (now - timedelta(days=5)).isoformat(),
                        },
                        {
                            "id": "q_fading",
                            "question": "Fading question",
                            "resolved": False,
                            "importance": 4,
                            "created_at": (now - timedelta(days=60)).isoformat(),
                        },
                        {
                            "id": "q_dormant",
                            "question": "Dormant question",
                            "resolved": False,
                            "importance": 1,
                            "created_at": (now - timedelta(days=120)).isoformat(),
                        },
                    ],
                    "unresolved_questions": ["q_active", "q_fading", "q_dormant"],
                }
            ),
            encoding="utf-8",
        )
        store = SelfModelStore(path)
        active, resurfacing = store.get_visible_questions()
        assert [q["id"] for q in active] == ["q_active"]
        assert [q["id"] for q in resurfacing] == ["q_fading"]
        assert all("salience" in q and "age_days" in q for q in active + resurfacing)


class TestQuestionSalience:
    @pytest.mark.parametrize(
        ("importance", "age_days", "expected"),
        [
            (5, 0.0, 1.0),
            (3, 0.0, 0.6),
            (1, 0.0, 0.2),
        ],
    )
    def test_salience_initial_value(
        self, importance: int, age_days: float, expected: float
    ) -> None:
        assert _calculate_salience(importance, age_days) == pytest.approx(expected)

    def test_salience_decays_with_age(self) -> None:
        fresh = _calculate_salience(5, 0.0)
        older = _calculate_salience(5, 70.0)
        much_older = _calculate_salience(5, 180.0)
        assert fresh > older > much_older
