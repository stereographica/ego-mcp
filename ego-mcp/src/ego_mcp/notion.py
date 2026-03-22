"""Notion persistence and update helpers."""

from __future__ import annotations

import json
import uuid
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ego_mcp import timezone_utils
from ego_mcp.types import Emotion, Memory, Notion


def _now_iso() -> str:
    return timezone_utils.now().isoformat()


def _clamp_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.5
    return max(0.0, min(1.0, confidence))


def _parse_emotion(value: Any) -> Emotion:
    if isinstance(value, Emotion):
        return value
    if isinstance(value, str):
        try:
            return Emotion(value)
        except ValueError:
            return Emotion.NEUTRAL
    return Emotion.NEUTRAL


class NotionStore:
    """JSON-backed store for notion objects."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._data: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            self._data = {}
            return
        try:
            parsed = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._data = {}
            return
        self._data = parsed if isinstance(parsed, dict) else {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _to_payload(notion: Notion) -> dict[str, Any]:
        payload = asdict(notion)
        payload["emotion_tone"] = notion.emotion_tone.value
        return payload

    @staticmethod
    def _from_payload(payload: dict[str, Any]) -> Notion:
        return Notion(
            id=str(payload.get("id", "")),
            label=str(payload.get("label", "")),
            emotion_tone=_parse_emotion(payload.get("emotion_tone")),
            valence=float(payload.get("valence", 0.0)),
            confidence=_clamp_confidence(payload.get("confidence", 0.5)),
            source_memory_ids=list(payload.get("source_memory_ids", [])),
            tags=list(payload.get("tags", [])),
            created=str(payload.get("created", "")),
            last_reinforced=str(payload.get("last_reinforced", "")),
        )

    def save(self, notion: Notion) -> None:
        if not notion.id:
            notion.id = f"notion_{uuid.uuid4().hex[:12]}"
        if not notion.created:
            notion.created = _now_iso()
        if not notion.last_reinforced:
            notion.last_reinforced = notion.created
        self._data[notion.id] = self._to_payload(notion)
        self._save()

    def get_by_id(self, notion_id: str) -> Notion | None:
        payload = self._data.get(notion_id)
        if not isinstance(payload, dict):
            return None
        return self._from_payload(payload)

    def list_all(self) -> list[Notion]:
        notions: list[Notion] = []
        for payload in self._data.values():
            if isinstance(payload, dict):
                notions.append(self._from_payload(payload))
        notions.sort(key=lambda notion: notion.created, reverse=True)
        return notions

    def update(self, notion_id: str, **kwargs: Any) -> Notion | None:
        payload = self._data.get(notion_id)
        if not isinstance(payload, dict):
            return None
        merged = dict(payload)
        for key, value in kwargs.items():
            if key == "emotion_tone":
                merged[key] = _parse_emotion(value).value
            elif key == "confidence":
                merged[key] = _clamp_confidence(value)
            else:
                merged[key] = value
        notion = self._from_payload(merged)
        self._data[notion_id] = self._to_payload(notion)
        self._save()
        return notion

    def delete(self, notion_id: str) -> bool:
        if notion_id not in self._data:
            return False
        del self._data[notion_id]
        self._save()
        return True

    def search_by_tags(self, tags: list[str], min_match: int = 1) -> list[Notion]:
        wanted = {tag.strip() for tag in tags if isinstance(tag, str) and tag.strip()}
        if not wanted:
            return []
        ranked: list[tuple[int, float, Notion]] = []
        for notion in self.list_all():
            overlap = wanted.intersection(notion.tags)
            if len(overlap) < min_match:
                continue
            ranked.append((len(overlap), notion.confidence, notion))
        ranked.sort(key=lambda item: (-item[0], -item[1], item[2].label))
        return [item[2] for item in ranked]


def generate_notion_from_cluster(memories: list[Memory]) -> Notion:
    """Generate a notion from a densely linked memory cluster."""
    if not memories:
        return Notion()

    emotion_counter = Counter(memory.emotional_trace.primary for memory in memories)
    emotion_tone = emotion_counter.most_common(1)[0][0]
    valence = sum(memory.emotional_trace.valence for memory in memories) / len(memories)

    tag_sets = [set(memory.tags) for memory in memories if memory.tags]
    shared_tags = set.intersection(*tag_sets) if tag_sets else set()
    if shared_tags:
        tags = sorted(shared_tags)
    else:
        tag_counter = Counter(tag for memory in memories for tag in memory.tags)
        tags = [tag for tag, _ in tag_counter.most_common(2)]

    label_tags = tags[:3] if tags else ["untitled"]
    created = _now_iso()
    return Notion(
        label=f'{" & ".join(label_tags)} ({emotion_tone.value})',
        emotion_tone=emotion_tone,
        valence=valence,
        confidence=min(0.3 + len(memories) * 0.1, 0.9),
        source_memory_ids=[memory.id for memory in memories],
        tags=tags,
        created=created,
        last_reinforced=created,
    )


def update_notion_from_memory(
    store: NotionStore,
    memory: Memory,
) -> list[tuple[str, str]]:
    """Reinforce or weaken notions using a newly stored memory."""
    if not memory.tags:
        return []

    now = _now_iso()
    results: list[tuple[str, str]] = []
    for notion in store.search_by_tags(memory.tags, min_match=1):
        same_sign = notion.valence == 0.0 or memory.emotional_trace.valence == 0.0
        if notion.valence != 0.0 and memory.emotional_trace.valence != 0.0:
            same_sign = (notion.valence > 0) == (memory.emotional_trace.valence > 0)

        if same_sign:
            updated_sources = list(dict.fromkeys([*notion.source_memory_ids, memory.id]))
            updated = store.update(
                notion.id,
                confidence=min(1.0, notion.confidence + 0.1),
                last_reinforced=now,
                source_memory_ids=updated_sources,
            )
            if updated is not None:
                results.append((notion.id, "reinforced"))
            continue

        weakened_confidence = notion.confidence - 0.15
        if weakened_confidence < 0.2:
            if store.delete(notion.id):
                results.append((notion.id, "dormant"))
            continue
        updated = store.update(
            notion.id,
            confidence=weakened_confidence,
            last_reinforced=now,
        )
        if updated is not None:
            results.append((notion.id, "weakened"))
    return results
