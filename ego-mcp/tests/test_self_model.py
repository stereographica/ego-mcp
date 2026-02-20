"""Tests for SelfModelStore."""

from __future__ import annotations

from pathlib import Path

from ego_mcp.self_model import SelfModelStore


class TestSelfModelStore:
    def test_get_default(self, tmp_path: Path) -> None:
        store = SelfModelStore(tmp_path / "self_model.json")
        model = store.get()
        assert model.confidence_calibration == 0.5
        assert model.unresolved_questions == []
        assert model.last_updated != ""

    def test_update_partial(self, tmp_path: Path) -> None:
        store = SelfModelStore(tmp_path / "self_model.json")
        model = store.update({"confidence_calibration": 0.8, "current_goals": ["learn"]})
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
