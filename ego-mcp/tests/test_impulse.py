"""Tests for transient impulse boosts."""

from __future__ import annotations

from ego_mcp.impulse import ImpulseManager
from ego_mcp.types import Emotion, EmotionalTrace, Memory


def test_register_proust_event_creates_one_shot_boost_and_event() -> None:
    manager = ImpulseManager()
    memory = Memory(
        id="mem_1",
        emotional_trace=EmotionalTrace(primary=Emotion.CURIOUS),
    )

    boosts = manager.register_proust_event(memory)

    assert boosts == {"information_hunger": 0.15}
    assert manager.consume_boosts() == {"information_hunger": 0.15}

    event = manager.consume_event()
    assert event["impulse_boost_triggered"] is True
    assert event["impulse_source_memory_id"] == "mem_1"
    assert event["impulse_boosted_desire"] == "information_hunger"
    assert event["impulse_boost_amount"] == 0.15


def test_register_proust_event_respects_cooldown() -> None:
    manager = ImpulseManager()
    memory = Memory(
        id="mem_2",
        emotional_trace=EmotionalTrace(primary=Emotion.NOSTALGIC),
    )

    assert manager.register_proust_event(memory) == {"resonance": 0.15}
    assert manager.register_proust_event(memory) == {}


def test_register_proust_event_aggregates_multiple_pending_events() -> None:
    manager = ImpulseManager()
    first = Memory(
        id="mem_3",
        emotional_trace=EmotionalTrace(primary=Emotion.CURIOUS),
    )
    second = Memory(
        id="mem_4",
        emotional_trace=EmotionalTrace(primary=Emotion.NOSTALGIC),
    )

    manager.register_proust_event(first)
    manager.register_proust_event(second)
    event = manager.consume_event()

    assert event["impulse_boost_triggered"] is True
    assert event["impulse_event_count"] == 2
    assert event["impulse_source_memory_ids"] == "mem_3,mem_4"
    assert event["impulse_boosted_desires"] == "information_hunger,resonance"
    assert event["impulse_boost_amounts"] == "0.15,0.15"
