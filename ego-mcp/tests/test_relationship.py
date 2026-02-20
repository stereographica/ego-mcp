"""Tests for RelationshipStore."""

from __future__ import annotations

from pathlib import Path

from ego_mcp.relationship import RelationshipStore


class TestRelationshipStore:
    def test_get_default(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "relationships.json")
        rel = store.get("Master")
        assert rel.person_id == "Master"
        assert rel.trust_level == 0.5
        assert rel.total_interactions == 0
        assert rel.preferred_topics == []
        assert rel.sensitive_topics == []

    def test_update_partial(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "relationships.json")
        updated = store.update("Master", {"trust_level": 0.9, "known_facts": ["busy"]})
        assert updated.trust_level == 0.9
        assert updated.known_facts == ["busy"]

        again = store.get("Master")
        assert again.trust_level == 0.9
        assert again.known_facts == ["busy"]

    def test_add_interaction(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "relationships.json")
        ts = "2026-02-20T10:00:00+00:00"
        updated = store.add_interaction("Master", ts, "focused")
        assert updated.total_interactions == 1
        assert updated.first_interaction == ts
        assert updated.last_interaction == ts
        assert updated.communication_style["focused"] == 1.0
        assert updated.recent_mood_trajectory[-1]["mood"] == "focused"

    def test_add_shared_episode(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "relationships.json")
        store.add_shared_episode("Master", "ep_1")
        updated = store.add_shared_episode("Master", "ep_1")
        assert updated.shared_episode_ids == ["ep_1"]

    def test_persistence(self, tmp_path: Path) -> None:
        path = tmp_path / "relationships.json"
        store = RelationshipStore(path)
        store.update("Master", {"trust_level": 0.77})
        store.add_shared_episode("Master", "ep_x")

        reloaded = RelationshipStore(path)
        rel = reloaded.get("Master")
        assert rel.trust_level == 0.77
        assert rel.shared_episode_ids == ["ep_x"]

    def test_corrupt_json_fallback(self, tmp_path: Path) -> None:
        path = tmp_path / "relationships.json"
        path.write_text("{broken json", encoding="utf-8")
        store = RelationshipStore(path)
        rel = store.get("Master")
        assert rel.total_interactions == 0

    def test_apply_tom_feedback(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "relationships.json")
        updated = store.apply_tom_feedback(
            "Master",
            dominant_tone="curious",
            preferred_topics=["technical", "planning"],
            sensitive_topics=["relationship"],
        )
        assert updated.preferred_topics[:2] == ["technical", "planning"]
        assert updated.sensitive_topics == ["relationship"]
        assert updated.recent_mood_trajectory[-1]["mood"] == "curious"
