"""Tests for RelationshipStore."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ego_mcp.relationship import (
    _UPDATABLE_FIELDS,
    INTERACTION_LOG_MAX,
    RelationshipStore,
)


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

    def test_update_rejects_unknown_field(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "relationships.json")
        with pytest.raises(ValueError, match="Invalid relationship field"):
            store.update("Master", {"trust": 0.9})

    def test_updatable_fields_excludes_person_id(self) -> None:
        assert "person_id" not in _UPDATABLE_FIELDS

    def test_add_interaction(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "relationships.json")
        ts = "2026-02-20T10:00:00+00:00"
        updated = store.add_interaction("Master", ts, "focused")
        assert updated.total_interactions == 1
        assert updated.first_interaction == ts
        assert updated.last_interaction == ts
        assert updated.communication_style["focused"] == 1.0
        assert updated.recent_mood_trajectory[-1]["mood"] == "focused"

    def test_add_interaction_increments_total_independent_of_log_length(
        self,
        tmp_path: Path,
    ) -> None:
        path = tmp_path / "relationships.json"
        path.write_text(
            json.dumps(
                {
                    "Master": {
                        "person_id": "Master",
                        "name": "Master",
                        "total_interactions": 10,
                        "interaction_log": [
                            {
                                "timestamp": "2026-02-19T10:00:00+00:00",
                                "tone": "warm",
                            }
                        ],
                    }
                }
            ),
            encoding="utf-8",
        )
        store = RelationshipStore(path)

        updated = store.add_interaction(
            "Master",
            "2026-02-20T10:00:00+00:00",
            "focused",
        )

        assert updated.total_interactions == 11
        assert len(store.raw("Master")["interaction_log"]) == 2

    def test_add_interaction_caps_log_and_preserves_first_interaction(
        self,
        tmp_path: Path,
    ) -> None:
        store = RelationshipStore(tmp_path / "relationships.json")
        first_ts = "2026-01-01T00:00:00+00:00"
        store.add_interaction("Master", first_ts, "unknown-tone")

        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for index in range(1, INTERACTION_LOG_MAX + 6):
            store.add_interaction(
                "Master",
                (start + timedelta(days=index)).isoformat(),
                "unknown-tone",
            )

        rel = store.get("Master")
        raw = store.raw("Master")
        assert rel.total_interactions == INTERACTION_LOG_MAX + 6
        assert rel.first_interaction == first_ts
        assert len(raw["interaction_log"]) == INTERACTION_LOG_MAX
        assert raw["interaction_log"][0]["timestamp"] != first_ts
        assert rel.communication_style["unknown-tone"] == float(
            INTERACTION_LOG_MAX + 6
        )

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

    def test_update_rejects_wrong_type_for_dict_field(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "relationships.json")
        with pytest.raises(TypeError, match="communication_style.*dict.*str"):
            store.update("Master", {"communication_style": "calm and warm"})

    def test_update_rejects_wrong_type_for_list_field(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "relationships.json")
        with pytest.raises(TypeError, match="known_facts.*list.*str"):
            store.update("Master", {"known_facts": "likes coffee"})

    def test_update_rejects_wrong_type_for_numeric_field(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "relationships.json")
        with pytest.raises(TypeError, match="trust_level"):
            store.update("Master", {"trust_level": "high"})

    def test_update_accepts_correct_types(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "relationships.json")
        updated = store.update(
            "Master",
            {
                "communication_style": {"warm": 3.0},
                "known_facts": ["likes coffee"],
                "trust_level": 0.9,
            },
        )
        assert updated.communication_style == {"warm": 3.0}
        assert updated.known_facts == ["likes coffee"]
        assert updated.trust_level == 0.9

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

    def test_default_aliases_and_relation_kind(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "relationships.json")
        rel = store.get("Master")
        assert rel.aliases == []
        assert rel.relation_kind == "interlocutor"

    def test_update_aliases(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "relationships.json")
        updated = store.update("Master", {"aliases": ["Master", "マスター"]})
        assert updated.aliases == ["Master", "マスター"]
        # Verify persistence
        reloaded = store.get("Master")
        assert reloaded.aliases == ["Master", "マスター"]

    def test_update_relation_kind(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "relationships.json")
        updated = store.update("Master", {"relation_kind": "mentioned"})
        assert updated.relation_kind == "mentioned"
        reloaded = store.get("Master")
        assert reloaded.relation_kind == "mentioned"

    def test_resolve_person_canonical_match(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "relationships.json")
        store.update("Master", {"name": "Master"})
        assert store.resolve_person("Master") == "Master"

    def test_resolve_person_alias_match(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "relationships.json")
        store.update("Master", {"aliases": ["マスター", "master"]})
        assert store.resolve_person("マスター") == "Master"
        assert store.resolve_person("master") == "Master"

    def test_resolve_person_no_match(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "relationships.json")
        store.update("Master", {"aliases": ["マスター"]})
        assert store.resolve_person("unknown") is None

    def test_resolve_person_empty_store(self, tmp_path: Path) -> None:
        store = RelationshipStore(tmp_path / "relationships.json")
        assert store.resolve_person("anyone") is None
