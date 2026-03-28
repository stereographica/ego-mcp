"""Notion persistence and update helpers."""

from __future__ import annotations

import json
import math
import re
import uuid
from collections import Counter, deque
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ego_mcp import timezone_utils
from ego_mcp.types import Emotion, Memory, Notion

_PLACEHOLDER_NOTION_LABEL = re.compile(r"^untitled\s*\([^)]+\)$", re.IGNORECASE)
_TITLE_SEPARATOR = re.compile(r"[.!?。！？\n]+")
_WHITESPACE = re.compile(r"\s+")
_MAX_CONTENT_LABEL_LENGTH = 48


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


def _parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone_utils.app_timezone())
    return parsed


def is_placeholder_notion_label(label: str) -> bool:
    """Return whether the given notion label still uses the placeholder form."""
    normalized = _WHITESPACE.sub(" ", label).strip()
    return not normalized or _PLACEHOLDER_NOTION_LABEL.fullmatch(normalized) is not None


def derive_notion_tags(memories: list[Memory]) -> list[str]:
    """Build notion tags from shared tags first, then frequent tags."""
    tag_sets = [set(memory.tags) for memory in memories if memory.tags]
    shared_tags = set.intersection(*tag_sets) if tag_sets else set()
    if shared_tags:
        return sorted(shared_tags)

    tag_counter = Counter(tag for memory in memories for tag in memory.tags)
    return [tag for tag, _count in tag_counter.most_common(2)]


def _content_label_candidate(content: str) -> str:
    normalized = _WHITESPACE.sub(" ", content).strip()
    if not normalized:
        return ""

    head = _TITLE_SEPARATOR.split(normalized, maxsplit=1)[0].strip()
    candidate = head or normalized
    candidate = candidate.strip(" -_.,;:!?/\\|()[]{}\"'`")
    if not candidate:
        return ""
    if len(candidate) <= _MAX_CONTENT_LABEL_LENGTH:
        return candidate

    clipped = candidate[: _MAX_CONTENT_LABEL_LENGTH - 3].rstrip(" -_.,;:!?/\\|")
    return f"{clipped}..."


def _derive_content_label(memories: list[Memory]) -> str:
    candidates: Counter[str] = Counter()
    first_seen: dict[str, int] = {}
    for index, memory in enumerate(memories):
        candidate = _content_label_candidate(memory.content)
        if not candidate:
            continue
        candidates[candidate] += 1
        first_seen.setdefault(candidate, index)

    if not candidates:
        return "untitled"

    return min(
        candidates,
        key=lambda candidate: (
            -candidates[candidate],
            first_seen[candidate],
            candidate,
        ),
    )


def derive_notion_label(
    emotion_tone: Emotion,
    memories: list[Memory],
    *,
    notion_tags: list[str] | None = None,
) -> str:
    """Build a notion label from tags or, when absent, source memory content."""
    tags = [tag for tag in (notion_tags or []) if tag.strip()]
    label_core = " & ".join(tags[:3]) if tags else _derive_content_label(memories)
    return f"{label_core} ({emotion_tone.value})"


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
            related_notion_ids=list(payload.get("related_notion_ids", [])),
            reinforcement_count=int(payload.get("reinforcement_count", 0)),
            person_id=str(payload.get("person_id", "")),
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

    def search_related(
        self,
        *,
        source_memory_ids: list[str],
        tags: list[str],
        min_tag_match: int = 1,
    ) -> list[Notion]:
        wanted_memory_ids = {
            memory_id.strip()
            for memory_id in source_memory_ids
            if isinstance(memory_id, str) and memory_id.strip()
        }
        wanted_tags = {
            tag.strip() for tag in tags if isinstance(tag, str) and tag.strip()
        }
        if not wanted_memory_ids and not wanted_tags:
            return []

        ranked: list[tuple[int, int, float, Notion]] = []
        for notion in self.list_all():
            source_overlap = len(wanted_memory_ids.intersection(notion.source_memory_ids))
            tag_overlap = len(wanted_tags.intersection(notion.tags))
            if source_overlap == 0 and tag_overlap < min_tag_match:
                continue
            ranked.append((source_overlap, tag_overlap, notion.confidence, notion))

        ranked.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3].label))
        return [item[3] for item in ranked]

    def apply_time_decay(
        self,
        *,
        half_life_days: float = 30.0,
        conviction_half_life_days: float = 90.0,
        prune_threshold: float = 0.15,
    ) -> list[tuple[str, str]]:
        return apply_time_decay(
            self,
            half_life_days=half_life_days,
            conviction_half_life_days=conviction_half_life_days,
            prune_threshold=prune_threshold,
        )

    def find_duplicates(
        self,
        *,
        jaccard_threshold: float = 0.6,
    ) -> list[tuple[str, str]]:
        return find_duplicates(self, jaccard_threshold=jaccard_threshold)

    def find_duplicate_components(
        self,
        *,
        jaccard_threshold: float = 0.6,
    ) -> list[list[str]]:
        return find_duplicate_components(self, jaccard_threshold=jaccard_threshold)

    def merge_notions(
        self,
        keep_id: str,
        absorb_id: str,
        *,
        person_id: str | None = None,
    ) -> Notion | None:
        return merge_notions(self, keep_id, absorb_id, person_id=person_id)

    def auto_link_notions(
        self,
        *,
        overlap_threshold: int = 2,
        max_notions: int = 200,
    ) -> int:
        return auto_link_notions(
            self,
            overlap_threshold=overlap_threshold,
            max_notions=max_notions,
        )

    def get_associated(self, notion_id: str, depth: int = 1) -> list[Notion]:
        return get_associated(self, notion_id, depth=depth)


def generate_notion_from_cluster(memories: list[Memory]) -> Notion:
    """Generate a notion from a densely linked memory cluster."""
    if not memories:
        return Notion()

    emotion_counter = Counter(memory.emotional_trace.primary for memory in memories)
    emotion_tone = emotion_counter.most_common(1)[0][0]
    valence = sum(memory.emotional_trace.valence for memory in memories) / len(memories)
    tags = derive_notion_tags(memories)
    created = _now_iso()
    return Notion(
        label=derive_notion_label(emotion_tone, memories, notion_tags=tags),
        emotion_tone=emotion_tone,
        valence=valence,
        confidence=min(0.3 + len(memories) * 0.1, 0.9),
        source_memory_ids=[memory.id for memory in memories],
        tags=tags,
        created=created,
        last_reinforced=created,
    )


def is_conviction(
    notion: Notion,
    min_reinforcements: int = 5,
    min_confidence: float = 0.7,
) -> bool:
    return (
        notion.reinforcement_count >= min_reinforcements
        and notion.confidence >= min_confidence
    )


_EPHEMERAL_PATTERNS = (
    re.compile(r"セッション終了|セッション開始|session end|session start", re.IGNORECASE),
    re.compile(r"^【セッション", re.IGNORECASE),
    re.compile(r"^(goodbye|bye|see you|また|おやすみ)", re.IGNORECASE),
)


def is_ephemeral_cluster(memories: list[Memory]) -> bool:
    if not memories:
        return False
    matches = sum(
        1
        for memory in memories
        if any(pattern.search(memory.content) for pattern in _EPHEMERAL_PATTERNS)
    )
    if matches > len(memories) / 2:
        return True
    low_importance = sum(1 for memory in memories if memory.importance <= 1)
    return low_importance > len(memories) / 2


def infer_person_id(
    source_memory_ids: list[str],
    person_memory_ids: dict[str, set[str]],
) -> str:
    normalized_memory_ids = [memory_id for memory_id in source_memory_ids if memory_id]
    if not normalized_memory_ids or not person_memory_ids:
        return ""

    threshold = len(normalized_memory_ids) / 2
    best_person = ""
    best_overlap = 0
    tied = False
    source_set = set(normalized_memory_ids)
    for person, memory_ids in person_memory_ids.items():
        overlap = len(source_set.intersection(memory_ids))
        if overlap <= best_overlap:
            if overlap == best_overlap and overlap > 0:
                tied = True
            continue
        best_person = person
        best_overlap = overlap
        tied = False

    if tied or best_overlap <= threshold:
        return ""
    return best_person


def apply_time_decay(
    store: NotionStore,
    *,
    half_life_days: float = 30.0,
    conviction_half_life_days: float = 90.0,
    prune_threshold: float = 0.15,
) -> list[tuple[str, str]]:
    now = _parse_iso_datetime(_now_iso())
    if now is None:
        return []

    outcomes: list[tuple[str, str]] = []
    for notion in store.list_all():
        created_at = _parse_iso_datetime(notion.created)
        last_reinforced_at = _parse_iso_datetime(notion.last_reinforced) or created_at
        if created_at is None or last_reinforced_at is None:
            continue
        if (now - created_at).total_seconds() < 86400:
            continue

        effective_half_life = (
            conviction_half_life_days if is_conviction(notion) else half_life_days
        )
        days_since_reinforced = max(
            0.0, (now - last_reinforced_at).total_seconds() / 86400
        )
        decayed_confidence = notion.confidence * math.pow(
            0.5, days_since_reinforced / effective_half_life
        )
        if decayed_confidence < prune_threshold:
            if store.delete(notion.id):
                outcomes.append((notion.id, "pruned"))
            continue
        if decayed_confidence < notion.confidence:
            updated = store.update(notion.id, confidence=decayed_confidence)
            if updated is not None:
                outcomes.append((notion.id, "decayed"))
    return outcomes


def _jaccard_similarity(left: list[str], right: list[str]) -> float:
    left_set = {item for item in left if item}
    right_set = {item for item in right if item}
    if not left_set and not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def find_duplicates(
    store: NotionStore,
    *,
    jaccard_threshold: float = 0.6,
) -> list[tuple[str, str]]:
    notions = store.list_all()
    duplicates: list[tuple[str, str]] = []
    for index, left in enumerate(notions):
        if not left.id:
            continue
        for right in notions[index + 1 :]:
            if not right.id:
                continue
            if (
                _jaccard_similarity(left.source_memory_ids, right.source_memory_ids)
                >= jaccard_threshold
            ):
                duplicates.append((left.id, right.id))
    duplicates.sort()
    return duplicates


def find_duplicate_components(
    store: NotionStore,
    *,
    jaccard_threshold: float = 0.6,
) -> list[list[str]]:
    notions = store.list_all()
    adjacency: dict[str, set[str]] = {notion.id: set() for notion in notions if notion.id}
    for left_id, right_id in find_duplicates(store, jaccard_threshold=jaccard_threshold):
        adjacency[left_id].add(right_id)
        adjacency[right_id].add(left_id)

    components: list[list[str]] = []
    visited: set[str] = set()
    for notion_id, neighbors in adjacency.items():
        if notion_id in visited or not neighbors:
            continue
        stack = [notion_id]
        component: list[str] = []
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            component.append(current)
            stack.extend(sorted(adjacency[current] - visited, reverse=True))
        if len(component) > 1:
            components.append(sorted(component))
    components.sort()
    return components


def merge_notions(
    store: NotionStore,
    keep_id: str,
    absorb_id: str,
    *,
    person_id: str | None = None,
) -> Notion | None:
    keep = store.get_by_id(keep_id)
    absorb = store.get_by_id(absorb_id)
    if keep is None or absorb is None or keep.id == absorb.id:
        return keep

    merged_person_id = person_id
    if merged_person_id is None:
        merged_person_id = keep.person_id or absorb.person_id

    updated_related = list(
        dict.fromkeys(
            notion_id
            for notion_id in [*keep.related_notion_ids, *absorb.related_notion_ids]
            if notion_id and notion_id not in {keep.id, absorb.id}
        )
    )
    merged = store.update(
        keep.id,
        source_memory_ids=list(
            dict.fromkeys([*keep.source_memory_ids, *absorb.source_memory_ids])
        ),
        tags=list(dict.fromkeys([*keep.tags, *absorb.tags])),
        related_notion_ids=updated_related,
        confidence=max(keep.confidence, absorb.confidence),
        reinforcement_count=keep.reinforcement_count + absorb.reinforcement_count,
        person_id=merged_person_id,
    )
    if merged is None:
        return None
    if not store.delete(absorb.id):
        return merged

    for notion in store.list_all():
        if absorb.id not in notion.related_notion_ids:
            continue
        rewritten_related = list(
            dict.fromkeys(
                keep.id if related_id == absorb.id else related_id
                for related_id in notion.related_notion_ids
                if related_id and related_id != notion.id
            )
        )
        store.update(notion.id, related_notion_ids=rewritten_related)
    return store.get_by_id(keep.id)


def auto_link_notions(
    store: NotionStore,
    *,
    overlap_threshold: int = 2,
    max_notions: int = 200,
) -> int:
    notions = store.list_all()
    if len(notions) > max_notions:
        return 0

    previous_pairs = {
        tuple(sorted((notion.id, related_id)))
        for notion in notions
        for related_id in notion.related_notion_ids
        if notion.id and related_id
    }
    related_map: dict[str, list[str]] = {
        notion.id: [
            related_id
            for related_id in notion.related_notion_ids
            if related_id and related_id != notion.id
        ]
        for notion in notions
        if notion.id
    }
    for index, left in enumerate(notions):
        if not left.id:
            continue
        left_sources = {memory_id for memory_id in left.source_memory_ids if memory_id}
        for right in notions[index + 1 :]:
            if not right.id:
                continue
            overlap = len(left_sources.intersection(right.source_memory_ids))
            if overlap < overlap_threshold:
                continue
            related_map[left.id].append(right.id)
            related_map[right.id].append(left.id)

    new_pairs = {
        tuple(sorted((notion_id, related_id)))
        for notion_id, related_ids in related_map.items()
        for related_id in related_ids
        if notion_id and related_id
    }
    for notion in notions:
        if not notion.id:
            continue
        store.update(
            notion.id,
            related_notion_ids=sorted(set(related_map.get(notion.id, []))),
        )
    return max(0, len(new_pairs - previous_pairs))


def get_associated(store: NotionStore, notion_id: str, depth: int = 1) -> list[Notion]:
    start = store.get_by_id(notion_id)
    if start is None or depth < 1:
        return []

    queue = deque((related_id, 1) for related_id in start.related_notion_ids)
    seen = {notion_id}
    found: list[tuple[int, Notion]] = []
    while queue:
        current_id, current_depth = queue.popleft()
        if current_id in seen or current_depth > depth:
            continue
        seen.add(current_id)
        notion = store.get_by_id(current_id)
        if notion is None:
            continue
        found.append((current_depth, notion))
        if current_depth < depth:
            queue.extend(
                (related_id, current_depth + 1)
                for related_id in notion.related_notion_ids
            )

    found.sort(key=lambda item: (item[0], -item[1].confidence, item[1].label, item[1].id))
    return [item[1] for item in found]


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
                reinforcement_count=notion.reinforcement_count + 1,
            )
            if updated is not None:
                results.append((notion.id, "reinforced"))
            continue

        weakened_confidence = notion.confidence - 0.15
        if weakened_confidence < 0.2:
            if store.delete(notion.id):
                results.append((notion.id, "dormant"))
            continue
        # Contradiction weakens confidence but does not count as reinforcement.
        updated = store.update(
            notion.id,
            confidence=weakened_confidence,
        )
        if updated is not None:
            results.append((notion.id, "weakened"))
    return results
