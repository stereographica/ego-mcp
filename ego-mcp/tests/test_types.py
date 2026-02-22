"""Tests for core type definitions."""

from __future__ import annotations

from ego_mcp.types import (
    BodyState,
    Category,
    DesireState,
    Emotion,
    EmotionalTrace,
    LinkType,
    Memory,
    MemoryLink,
    MemorySearchResult,
    RelationshipModel,
    SelfModel,
)


class TestEnums:
    """Enum value tests."""

    def test_emotion_values(self) -> None:
        assert Emotion.HAPPY.value == "happy"
        assert Emotion.SAD.value == "sad"
        assert Emotion.SURPRISED.value == "surprised"
        assert Emotion.MOVED.value == "moved"
        assert Emotion.EXCITED.value == "excited"
        assert Emotion.NOSTALGIC.value == "nostalgic"
        assert Emotion.CURIOUS.value == "curious"
        assert Emotion.NEUTRAL.value == "neutral"
        assert Emotion.MELANCHOLY.value == "melancholy"
        assert Emotion.ANXIOUS.value == "anxious"
        assert Emotion.CONTENTMENT.value == "contentment"
        assert Emotion.FRUSTRATED.value == "frustrated"

    def test_category_values(self) -> None:
        assert Category.DAILY.value == "daily"
        assert Category.PHILOSOPHICAL.value == "philosophical"
        assert Category.INTROSPECTION.value == "introspection"
        assert Category.RELATIONSHIP.value == "relationship"
        assert Category.SELF_DISCOVERY.value == "self_discovery"
        assert Category.DREAM.value == "dream"
        assert Category.LESSON.value == "lesson"

    def test_link_type_values(self) -> None:
        assert LinkType.SIMILAR.value == "similar"
        assert LinkType.CAUSED_BY.value == "caused_by"
        assert LinkType.LEADS_TO.value == "leads_to"
        assert LinkType.RELATED.value == "related"


class TestDataclassDefaults:
    """Default construction of all dataclasses."""

    def test_body_state(self) -> None:
        bs = BodyState()
        assert bs.time_phase == "unknown"
        assert bs.system_load == "unknown"
        assert bs.uptime_hours == 0.0

    def test_emotional_trace(self) -> None:
        et = EmotionalTrace()
        assert et.primary == Emotion.NEUTRAL
        assert et.secondary == []
        assert et.intensity == 0.5
        assert et.valence == 0.0
        assert et.arousal == 0.5

    def test_memory_link(self) -> None:
        ml = MemoryLink()
        assert ml.link_type == LinkType.RELATED
        assert ml.confidence == 0.5

    def test_memory(self) -> None:
        m = Memory()
        assert m.importance == 3
        assert m.category == Category.DAILY
        assert m.linked_ids == []
        assert m.tags == []
        assert m.is_private is False

    def test_memory_search_result(self) -> None:
        msr = MemorySearchResult()
        assert msr.distance == 0.0
        assert msr.score == 0.0

    def test_desire_state(self) -> None:
        ds = DesireState()
        assert ds.level == 0.0
        assert ds.satisfaction_quality == 0.5

    def test_relationship_model(self) -> None:
        rm = RelationshipModel()
        assert rm.trust_level == 0.5
        assert rm.total_interactions == 0
        assert rm.known_facts == []
        assert rm.preferred_topics == []
        assert rm.sensitive_topics == []
        assert rm.recent_mood_trajectory == []

    def test_self_model(self) -> None:
        sm = SelfModel()
        assert sm.confidence_calibration == 0.5
        assert sm.current_goals == []
        assert sm.unresolved_questions == []
        assert sm.last_updated == ""


class TestMutableFieldIsolation:
    """Mutable fields not shared between instances."""

    def test_memory_linked_ids_not_shared(self) -> None:
        m1 = Memory()
        m2 = Memory()
        m1.linked_ids.append(MemoryLink(target_id="test"))
        assert len(m2.linked_ids) == 0

    def test_memory_tags_not_shared(self) -> None:
        m1 = Memory()
        m2 = Memory()
        m1.tags.append("tag1")
        assert len(m2.tags) == 0

    def test_emotional_trace_secondary_not_shared(self) -> None:
        et1 = EmotionalTrace()
        et2 = EmotionalTrace()
        et1.secondary.append(Emotion.HAPPY)
        assert len(et2.secondary) == 0

    def test_relationship_known_facts_not_shared(self) -> None:
        r1 = RelationshipModel()
        r2 = RelationshipModel()
        r1.known_facts.append("fact1")
        assert len(r2.known_facts) == 0

    def test_relationship_topics_not_shared(self) -> None:
        r1 = RelationshipModel()
        r2 = RelationshipModel()
        r1.preferred_topics.append("technical")
        assert len(r2.preferred_topics) == 0

    def test_self_model_goals_not_shared(self) -> None:
        s1 = SelfModel()
        s2 = SelfModel()
        s1.current_goals.append("goal1")
        assert len(s2.current_goals) == 0


class TestNowIso:
    """Memory.now_iso() returns valid ISO 8601."""

    def test_now_iso_format(self) -> None:
        iso = Memory.now_iso()
        assert "T" in iso
        assert "+" in iso or "Z" in iso or iso.endswith("+00:00")
