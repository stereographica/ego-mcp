"""Question ripening helpers."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from ego_mcp import timezone_utils
from ego_mcp._server_emotion_formatting import _truncate_for_quote
from ego_mcp._server_runtime import update_tool_metadata
from ego_mcp.absence import approx_duration_words
from ego_mcp.notion import NotionStore
from ego_mcp.self_model import (
    QUESTION_ACTIVE_MIN_SALIENCE,
    QUESTION_DORMANT_MAX_SALIENCE,
    SelfModelStore,
)
from ego_mcp.types import Memory, MemorySearchResult, Notion

RIPENING_FEED_MAX_QUESTIONS = 5
RIPENING_COMPANION_DISTANCE_MIN = 0.35
RIPENING_COMPANION_DISTANCE_MAX = 0.65
RIPENING_COMPANIONS_PER_FEED = 2
RIPENING_TENSIONS_PER_FEED = 1
RIPENING_SEARCH_N = 15
RIPENING_TENSION_VALENCE_MIN = 0.3
RIPENING_TENSION_SHARED_TAGS_MIN = 2
RIPENING_RESURFACE_THRESHOLD = 3
RIPENING_PRESENCE_PROBABILITY = 0.25


class RandomLike(Protocol):
    def random(self) -> float: ...


@dataclass(frozen=True)
class RipeningFeedStats:
    fed_questions: int = 0
    deposits: int = 0


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return timezone_utils.localize(parsed)


def _age_words_from_timestamp(timestamp: str, now: datetime) -> str:
    parsed = _parse_time(timestamp)
    if parsed is None:
        return approx_duration_words(0.0)
    elapsed_days = max(0.0, (timezone_utils.localize(now) - parsed).total_seconds() / 86400.0)
    return approx_duration_words(elapsed_days)


def _shared_tags(left: list[str], right: list[str]) -> set[str]:
    return {
        tag
        for tag in left
        if isinstance(tag, str) and tag and tag in {r for r in right if isinstance(r, str)}
    }


def _has_opposed_valence(left: float, right: float) -> bool:
    return (
        abs(left) >= RIPENING_TENSION_VALENCE_MIN
        and abs(right) >= RIPENING_TENSION_VALENCE_MIN
        and left * right < 0
    )


def _memory_tags(memory: Memory) -> list[str]:
    return [tag for tag in memory.tags if isinstance(tag, str) and tag]


def _notion_tags(notion: Notion) -> list[str]:
    return [tag for tag in notion.tags if isinstance(tag, str) and tag]


def _existing_memory_ids(companions: list[dict[str, Any]]) -> set[str]:
    memory_ids: set[str] = set()
    for companion in companions:
        for key in ("memory_id", "paired_memory_id"):
            value = companion.get(key)
            if isinstance(value, str) and value:
                memory_ids.add(value)
    return memory_ids


def _existing_memory_pairs(companions: list[dict[str, Any]]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for companion in companions:
        left = companion.get("memory_id")
        right = companion.get("paired_memory_id")
        if isinstance(left, str) and isinstance(right, str) and left and right:
            pairs.add((left, right) if left <= right else (right, left))
    return pairs


def _existing_notion_pairs(companions: list[dict[str, Any]]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for companion in companions:
        left = companion.get("notion_id")
        right = companion.get("paired_notion_id")
        if isinstance(left, str) and isinstance(right, str) and left and right:
            pairs.add((left, right) if left <= right else (right, left))
    return pairs


def _fading_feed_targets(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fading = [
        entry
        for entry in entries
        if not entry.get("resolved", False)
        and int(entry.get("importance", 3)) >= 2
        and QUESTION_DORMANT_MAX_SALIENCE
        < float(entry.get("salience", 0.0))
        <= QUESTION_ACTIVE_MIN_SALIENCE
    ]
    return sorted(fading, key=lambda entry: str(entry.get("last_fed_at", "")))[
        :RIPENING_FEED_MAX_QUESTIONS
    ]


def _companion_deposits(
    results: list[MemorySearchResult],
    companions: list[dict[str, Any]],
    now_iso: str,
) -> list[dict[str, Any]]:
    existing_ids = _existing_memory_ids(companions)
    deposits: list[dict[str, Any]] = []
    seen: set[str] = set()
    candidates = sorted(
        (
            result
            for result in results
            if RIPENING_COMPANION_DISTANCE_MIN
            <= float(result.distance)
            <= RIPENING_COMPANION_DISTANCE_MAX
            and result.memory.id
            and result.memory.id not in existing_ids
        ),
        key=lambda result: (float(result.distance), result.memory.id),
    )
    for result in candidates:
        if result.memory.id in seen:
            continue
        seen.add(result.memory.id)
        deposits.append(
            {
                "memory_id": result.memory.id,
                "distance": round(float(result.distance), 3),
                "added_at": now_iso,
                "kind": "companion",
            }
        )
        if len(deposits) >= RIPENING_COMPANIONS_PER_FEED:
            break
    return deposits


def _memory_tension_deposit(
    results: list[MemorySearchResult],
    companions: list[dict[str, Any]],
    now_iso: str,
) -> dict[str, Any] | None:
    existing_pairs = _existing_memory_pairs(companions)
    nearby = sorted(
        (
            result
            for result in results
            if float(result.distance) <= RIPENING_COMPANION_DISTANCE_MAX
            and result.memory.id
        ),
        key=lambda result: (float(result.distance), result.memory.id),
    )
    candidates: list[tuple[float, str, str, MemorySearchResult, MemorySearchResult]] = []
    for index, left in enumerate(nearby):
        for right in nearby[index + 1 :]:
            left_id = left.memory.id
            right_id = right.memory.id
            if not left_id or not right_id or left_id == right_id:
                continue
            pair = tuple(sorted((left_id, right_id)))
            if pair in existing_pairs:
                continue
            if len(_shared_tags(_memory_tags(left.memory), _memory_tags(right.memory))) < (
                RIPENING_TENSION_SHARED_TAGS_MIN
            ):
                continue
            if not _has_opposed_valence(
                float(left.memory.emotional_trace.valence),
                float(right.memory.emotional_trace.valence),
            ):
                continue
            candidates.append(
                (
                    float(left.distance) + float(right.distance),
                    pair[0],
                    pair[1],
                    left,
                    right,
                )
            )
    if not candidates:
        return None
    _, _, _, left, right = sorted(candidates, key=lambda item: item[:3])[0]
    return {
        "memory_id": left.memory.id,
        "paired_memory_id": right.memory.id,
        "distance": round(float(left.distance) + float(right.distance), 3),
        "added_at": now_iso,
        "kind": "tension",
    }


def _notion_tension_deposit(
    results: list[MemorySearchResult],
    companions: list[dict[str, Any]],
    notion_store: NotionStore | None,
    now_iso: str,
) -> dict[str, Any] | None:
    if notion_store is None:
        return None
    try:
        notions = notion_store.list_all()
    except Exception:
        return None
    existing_pairs = _existing_notion_pairs(companions)
    nearby_tags = {
        tag
        for result in results
        if float(result.distance) <= RIPENING_COMPANION_DISTANCE_MAX
        for tag in _memory_tags(result.memory)
    }
    candidates: list[tuple[str, str, Notion, Notion]] = []
    for index, left in enumerate(notions):
        for right in notions[index + 1 :]:
            if not left.id or not right.id or left.id == right.id:
                continue
            pair = tuple(sorted((left.id, right.id)))
            if pair in existing_pairs:
                continue
            left_tags = _notion_tags(left)
            right_tags = _notion_tags(right)
            if len(_shared_tags(left_tags, right_tags)) < RIPENING_TENSION_SHARED_TAGS_MIN:
                continue
            if not (set(left_tags).intersection(nearby_tags) or set(right_tags).intersection(nearby_tags)):
                continue
            if not _has_opposed_valence(float(left.valence), float(right.valence)):
                continue
            candidates.append((pair[0], pair[1], left, right))
    if not candidates:
        return None
    _, _, left, right = sorted(candidates, key=lambda item: item[:2])[0]
    return {
        "notion_id": left.id,
        "paired_notion_id": right.id,
        "added_at": now_iso,
        "kind": "tension_notion",
    }


async def feed_ripening_questions(
    self_store: SelfModelStore,
    memory: Any,
    notion_store: NotionStore | None = None,
    *,
    now: datetime | None = None,
) -> RipeningFeedStats:
    """Feed fading questions with companions and tensions."""
    now = now or timezone_utils.now()
    now_iso = now.isoformat()
    targets = _fading_feed_targets(self_store.get_unresolved_questions_with_salience())
    deposits_count = 0
    for target in targets:
        companions = list(target.get("companions", []))
        try:
            results = await memory.search(
                str(target["question"]),
                n_results=RIPENING_SEARCH_N,
            )
        except Exception:
            results = []
        if not isinstance(results, list):
            results = []

        deposits = _companion_deposits(results, companions, now_iso)
        companions.extend(deposits)

        tension_count = 0
        tension = _memory_tension_deposit(results, companions, now_iso)
        if tension is not None and tension_count < RIPENING_TENSIONS_PER_FEED:
            companions.append(tension)
            deposits.append(tension)
            tension_count += 1
        if tension_count < RIPENING_TENSIONS_PER_FEED:
            notion_tension = _notion_tension_deposit(
                results,
                companions,
                notion_store,
                now_iso,
            )
            if notion_tension is not None:
                companions.append(notion_tension)
                deposits.append(notion_tension)

        deposits_count += len(deposits)
        self_store.update_question_fields(
            str(target["id"]),
            {"companions": companions, "last_fed_at": now_iso},
        )
    return RipeningFeedStats(
        fed_questions=len(targets),
        deposits=deposits_count,
    )


def pick_ripened_question(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    ready = [
        entry
        for entry in entries
        if not entry.get("resolved", False)
        and len(entry.get("companions", [])) >= RIPENING_RESURFACE_THRESHOLD
    ]
    if not ready:
        return None
    ready.sort(
        key=lambda entry: (
            -len(entry.get("companions", [])),
            str(entry.get("last_fed_at", "")),
        )
    )
    return ready[0]


def has_ripening_presence(entries: list[dict[str, Any]]) -> bool:
    return any(
        not entry.get("resolved", False)
        and int(entry.get("importance", 3)) >= 2
        and entry.get("companions")
        and QUESTION_DORMANT_MAX_SALIENCE
        < float(entry.get("salience", 0.0))
        <= QUESTION_ACTIVE_MIN_SALIENCE
        for entry in entries
    )


def should_show_ripening_presence(
    entries: list[dict[str, Any]],
    rng: RandomLike = random,
) -> bool:
    return has_ripening_presence(entries) and rng.random() < RIPENING_PRESENCE_PROBABILITY


async def _memory_snippet_line(
    memory_store: Any,
    companion: dict[str, Any],
    now: datetime,
) -> str | None:
    memory_id = companion.get("memory_id")
    if not isinstance(memory_id, str) or not memory_id:
        return None
    memory = await memory_store.get_by_id(memory_id)
    if memory is None:
        return None
    snippet = _truncate_for_quote(memory.content, 60)
    age_words = _age_words_from_timestamp(memory.timestamp, now)
    return f'- "{snippet}" ({age_words})'


async def _memory_tension_line(
    memory_store: Any,
    companion: dict[str, Any],
) -> str | None:
    left_id = companion.get("memory_id")
    right_id = companion.get("paired_memory_id")
    if not isinstance(left_id, str) or not isinstance(right_id, str):
        return None
    left = await memory_store.get_by_id(left_id)
    right = await memory_store.get_by_id(right_id)
    if left is None or right is None:
        return None
    left_snippet = _truncate_for_quote(left.content, 60)
    right_snippet = _truncate_for_quote(right.content, 60)
    return f'- "{left_snippet}" / "{right_snippet}" — these two don\'t agree'


def _notion_tension_line(
    notion_store: NotionStore | None,
    companion: dict[str, Any],
) -> str | None:
    if notion_store is None:
        return None
    left_id = companion.get("notion_id")
    right_id = companion.get("paired_notion_id")
    if not isinstance(left_id, str) or not isinstance(right_id, str):
        return None
    left = notion_store.get_by_id(left_id)
    right = notion_store.get_by_id(right_id)
    if left is None or right is None:
        return None
    return f'- "{left.label}" / "{right.label}" — these two don\'t agree'


def _person_name(relationship_store: Any, person_id: str) -> str:
    try:
        rel = relationship_store.get(person_id)
    except Exception:
        rel = None
    return rel.name if rel is not None and rel.name else person_id


def person_display_name(relationship_store: Any, person_id: str) -> str:
    return _person_name(relationship_store, person_id)


def shared_open_questions_for_person(
    self_store: SelfModelStore,
    person_id: str,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    questions = [
        entry
        for entry in self_store.get_unresolved_questions_with_salience()
        if entry.get("person_id") == person_id and not entry.get("resolved", False)
    ]
    questions.sort(key=lambda entry: float(entry.get("salience", 0.0)), reverse=True)
    return questions[:limit]


def format_shared_question_line(
    self_store: SelfModelStore,
    person_id: str,
) -> str:
    questions = shared_open_questions_for_person(self_store, person_id, limit=1)
    if not questions:
        return ""
    question = questions[0]
    return f'There\'s something you two left open: "[{question["id"]}] {question["question"]}"'


async def build_ripened_question_block(
    self_store: SelfModelStore,
    memory_store: Any,
    entry: dict[str, Any],
    *,
    relationship_store: Any | None = None,
    notion_store: NotionStore | None = None,
    now: datetime | None = None,
) -> str | None:
    """Build and consume a ripened question presentation block."""
    now = now or timezone_utils.now()
    companions = sorted(
        list(entry.get("companions", [])),
        key=lambda companion: str(companion.get("added_at", "")),
    )
    lines: list[str] = []
    for companion in companions:
        kind = companion.get("kind")
        line: str | None = None
        if kind == "companion":
            line = await _memory_snippet_line(memory_store, companion, now)
        elif kind == "tension":
            line = await _memory_tension_line(memory_store, companion)
        elif kind == "tension_notion":
            line = _notion_tension_line(notion_store, companion)
        if line is None:
            continue
        lines.append(line)
        if len(lines) >= RIPENING_RESURFACE_THRESHOLD:
            break

    qid = str(entry["id"])
    self_store.update_question_fields(qid, {"companions": []})
    if not lines:
        return None

    block_lines = [
        "A question you'd set aside has gathered strange companions:",
        f'"[{qid}] {entry["question"]}"',
        "alongside:",
        *lines,
        "They don't obviously fit together. What do they want to say to each other?",
        "If the question itself has changed shape, say it anew:",
        f'update_self(field="new_question", value={{"question": ..., "supersedes": "{qid}"}})',
    ]
    person_id = entry.get("person_id")
    if isinstance(person_id, str) and person_id:
        name = (
            _person_name(relationship_store, person_id)
            if relationship_store is not None
            else person_id
        )
        block_lines.append(
            f"This one is held with {name} — it may be wanting to go back to them."
        )
    update_tool_metadata(ripening_resurfaced=qid)
    return "\n".join(block_lines)
