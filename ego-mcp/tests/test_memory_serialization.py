"""Tests for memory serialization helpers (ChromaDB metadata)."""

from __future__ import annotations

import json

from ego_mcp._memory_serialization import memory_from_chromadb
from ego_mcp.types import Category, Emotion


class TestMemoryFromChromadbInvalidEnums:
    def test_invalid_emotion_falls_back_to_neutral(self) -> None:
        mem = memory_from_chromadb(
            "m1",
            "content",
            {"emotion": "NONEXISTENT_EMOTION", "timestamp": "2026-01-01T00:00:00Z"},
        )
        assert mem.emotional_trace.primary == Emotion.NEUTRAL

    def test_invalid_category_falls_back_to_daily(self) -> None:
        mem = memory_from_chromadb(
            "m2",
            "content",
            {"category": "NONEXISTENT_CATEGORY", "timestamp": "2026-01-01T00:00:00Z"},
        )
        assert mem.category == Category.DAILY


class TestMemoryFromChromadbLinkedIds:
    def test_malformed_linked_ids_json_ignored(self) -> None:
        mem = memory_from_chromadb(
            "m3",
            "content",
            {"linked_ids": "NOT VALID JSON{{{", "timestamp": "2026-01-01T00:00:00Z"},
        )
        assert mem.linked_ids == []

    def test_link_with_invalid_link_type_skipped(self) -> None:
        bad_links = json.dumps(
            [{"target_id": "x", "link_type": "BOGUS", "confidence": 0.5, "note": ""}]
        )
        mem = memory_from_chromadb(
            "m4",
            "content",
            {"linked_ids": bad_links, "timestamp": "2026-01-01T00:00:00Z"},
        )
        assert mem.linked_ids == []

    def test_link_with_invalid_confidence_type_skipped(self) -> None:
        bad_links = json.dumps(
            [
                {
                    "target_id": "x",
                    "link_type": "related",
                    "confidence": "not_a_number",
                    "note": "",
                }
            ]
        )
        mem = memory_from_chromadb(
            "m5",
            "content",
            {"linked_ids": bad_links, "timestamp": "2026-01-01T00:00:00Z"},
        )
        # "not_a_number" will raise ValueError in float(), caught by except block
        assert mem.linked_ids == []


class TestMemoryFromChromadbSecondary:
    def test_invalid_secondary_emotion_skipped(self) -> None:
        mem = memory_from_chromadb(
            "m6",
            "content",
            {
                "secondary": "happy,BOGUS,sad",
                "timestamp": "2026-01-01T00:00:00Z",
            },
        )
        assert mem.emotional_trace.secondary == [Emotion.HAPPY, Emotion.SAD]


class TestMemoryFromChromadbBodyState:
    def test_malformed_body_state_json_ignored(self) -> None:
        mem = memory_from_chromadb(
            "m7",
            "content",
            {"body_state": "{{invalid json", "timestamp": "2026-01-01T00:00:00Z"},
        )
        assert mem.emotional_trace.body_state is None

    def test_body_state_with_bad_uptime_hours_ignored(self) -> None:
        bad_body = json.dumps(
            {
                "time_phase": "morning",
                "system_load": "low",
                "uptime_hours": "not_a_number",
            }
        )
        mem = memory_from_chromadb(
            "m8",
            "content",
            {"body_state": bad_body, "timestamp": "2026-01-01T00:00:00Z"},
        )
        assert mem.emotional_trace.body_state is None
