"""Tests for notion generation and reinforcement."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from ego_mcp.notion import (
    NotionStore,
    apply_time_decay,
    auto_link_notions,
    find_duplicate_components,
    find_duplicates,
    generate_notion_from_cluster,
    get_associated,
    infer_person_id,
    is_conviction,
    is_ephemeral_cluster,
    merge_notions,
    update_notion_from_memory,
)
from ego_mcp.types import Category, Emotion, EmotionalTrace, Memory, Notion


def _memory(
    *,
    memory_id: str,
    content: str,
    emotion: Emotion,
    valence: float,
    tags: list[str],
) -> Memory:
    return Memory(
        id=memory_id,
        content=content,
        category=Category.INTROSPECTION,
        emotional_trace=EmotionalTrace(primary=emotion, valence=valence),
        tags=tags,
    )


def _saved_notion(
    notion_id: str,
    *,
    label: str = "pattern (curious)",
    emotion: Emotion = Emotion.CURIOUS,
    confidence: float = 0.6,
    source_memory_ids: list[str] | None = None,
    tags: list[str] | None = None,
    created: str = "2026-02-26T00:00:00+00:00",
    last_reinforced: str = "2026-02-26T00:00:00+00:00",
    related_notion_ids: list[str] | None = None,
    reinforcement_count: int = 0,
    person_id: str = "",
) -> Notion:
    return Notion(
        id=notion_id,
        label=label,
        emotion_tone=emotion,
        confidence=confidence,
        source_memory_ids=source_memory_ids or [],
        tags=tags or [],
        created=created,
        last_reinforced=last_reinforced,
        related_notion_ids=related_notion_ids or [],
        reinforcement_count=reinforcement_count,
        person_id=person_id,
    )


def test_generate_notion_from_cluster_uses_shared_tags_and_emotion() -> None:
    memories = [
        _memory(
            memory_id="mem_a",
            content="alpha signal",
            emotion=Emotion.CURIOUS,
            valence=0.4,
            tags=["pattern", "signal"],
        ),
        _memory(
            memory_id="mem_b",
            content="beta signal",
            emotion=Emotion.CURIOUS,
            valence=0.2,
            tags=["signal", "pattern"],
        ),
    ]

    notion = generate_notion_from_cluster(memories)

    assert notion.label == "pattern & signal (curious)"
    assert notion.emotion_tone == Emotion.CURIOUS
    assert notion.confidence == 0.5
    assert notion.source_memory_ids == ["mem_a", "mem_b"]
    assert notion.tags == ["pattern", "signal"]


def test_generate_notion_from_cluster_falls_back_to_content_when_tags_missing() -> None:
    memories = [
        _memory(
            memory_id="mem_a",
            content="A recurring thought about continuity. emotion traces might carry weight.",
            emotion=Emotion.CURIOUS,
            valence=0.4,
            tags=[],
        ),
        _memory(
            memory_id="mem_b",
            content="A recurring thought about continuity.\nMore detail follows here.",
            emotion=Emotion.CURIOUS,
            valence=0.2,
            tags=[],
        ),
    ]

    notion = generate_notion_from_cluster(memories)

    assert notion.label == "A recurring thought about continuity (curious)"
    assert notion.tags == []


def test_notion_store_reinforces_and_weakens_by_tag_overlap(tmp_path: Path) -> None:
    store = NotionStore(tmp_path / "notions.json")
    reinforcing = Notion(
        id="notion_1",
        label="pattern & signal (curious)",
        emotion_tone=Emotion.CURIOUS,
        valence=0.5,
        confidence=0.4,
        source_memory_ids=["mem_a"],
        tags=["pattern", "signal"],
        created="2026-02-26T00:00:00+00:00",
        last_reinforced="2026-02-26T00:00:00+00:00",
    )
    weakening = Notion(
        id="notion_2",
        label="tension & friction (sad)",
        emotion_tone=Emotion.SAD,
        valence=-0.6,
        confidence=0.25,
        source_memory_ids=["mem_b"],
        tags=["friction", "tension"],
        created="2026-02-26T00:00:00+00:00",
        last_reinforced="2026-02-26T00:00:00+00:00",
    )
    store.save(reinforcing)
    store.save(weakening)

    memory = _memory(
        memory_id="mem_new",
        content="new signal",
        emotion=Emotion.CURIOUS,
        valence=0.4,
        tags=["signal", "pattern", "friction"],
    )

    updates = update_notion_from_memory(store, memory)

    updated = store.get_by_id("notion_1")
    assert updated is not None
    assert updated.confidence == 0.5
    assert updated.source_memory_ids == ["mem_a", "mem_new"]
    assert updated.last_reinforced != ""
    assert updated.reinforcement_count == 1

    assert store.get_by_id("notion_2") is None
    assert {item for item in updates} == {("notion_1", "reinforced"), ("notion_2", "dormant")}


def test_notion_store_search_by_tags_ranks_overlap_and_confidence(
    tmp_path: Path,
) -> None:
    store = NotionStore(tmp_path / "notions.json")
    store.save(
        Notion(
            id="notion_a",
            label="signal",
            emotion_tone=Emotion.CURIOUS,
            confidence=0.9,
            tags=["pattern", "signal"],
            created="2026-02-26T00:00:00+00:00",
            last_reinforced="2026-02-26T00:00:00+00:00",
        )
    )
    store.save(
        Notion(
            id="notion_b",
            label="pattern",
            emotion_tone=Emotion.CURIOUS,
            confidence=0.4,
            tags=["pattern"],
            created="2026-02-26T00:00:00+00:00",
            last_reinforced="2026-02-26T00:00:00+00:00",
        )
    )

    matches = store.search_by_tags(["pattern", "signal"], min_match=1)

    assert [item.id for item in matches] == ["notion_a", "notion_b"]


def test_notion_store_search_related_prefers_source_memory_overlap(
    tmp_path: Path,
) -> None:
    store = NotionStore(tmp_path / "notions.json")
    store.save(
        Notion(
            id="notion_a",
            label="from-source",
            emotion_tone=Emotion.CURIOUS,
            confidence=0.4,
            source_memory_ids=["mem_shared"],
            tags=[],
            created="2026-02-26T00:00:00+00:00",
            last_reinforced="2026-02-26T00:00:00+00:00",
        )
    )
    store.save(
        Notion(
            id="notion_b",
            label="from-tags",
            emotion_tone=Emotion.CURIOUS,
            confidence=0.9,
            source_memory_ids=["mem_other"],
            tags=["pattern", "signal"],
            created="2026-02-26T00:00:00+00:00",
            last_reinforced="2026-02-26T00:00:00+00:00",
        )
    )

    matches = store.search_related(
        source_memory_ids=["mem_shared"],
        tags=["pattern"],
        min_tag_match=1,
    )

    assert [item.id for item in matches] == ["notion_a", "notion_b"]


def test_notion_store_weakening_keeps_last_reinforced_timestamp(tmp_path: Path) -> None:
    store = NotionStore(tmp_path / "notions.json")
    store.save(
        Notion(
            id="notion_1",
            label="pattern & signal (curious)",
            emotion_tone=Emotion.CURIOUS,
            valence=0.5,
            confidence=0.4,
            source_memory_ids=["mem_a"],
            tags=["pattern", "signal"],
            created="2026-02-26T00:00:00+00:00",
            last_reinforced="2026-02-26T00:00:00+00:00",
            reinforcement_count=2,
        )
    )

    memory = _memory(
        memory_id="mem_new",
        content="counter signal",
        emotion=Emotion.SAD,
        valence=-0.6,
        tags=["signal"],
    )

    updates = update_notion_from_memory(store, memory)

    updated = store.get_by_id("notion_1")
    assert updated is not None
    assert updates == [("notion_1", "weakened")]
    assert updated.confidence == pytest.approx(0.25)
    assert updated.last_reinforced == "2026-02-26T00:00:00+00:00"
    assert updated.reinforcement_count == 2


def test_notion_store_roundtrips_extended_fields(tmp_path: Path) -> None:
    store = NotionStore(tmp_path / "notions.json")
    store.save(
        _saved_notion(
            "notion_a",
            source_memory_ids=["mem_1", "mem_2"],
            tags=["pattern", "signal"],
            related_notion_ids=["notion_b"],
            reinforcement_count=3,
            person_id="Master",
        )
    )

    notion = store.get_by_id("notion_a")
    raw = json.loads((tmp_path / "notions.json").read_text(encoding="utf-8"))

    assert notion is not None
    assert notion.related_notion_ids == ["notion_b"]
    assert notion.reinforcement_count == 3
    assert notion.person_id == "Master"
    assert raw["notion_a"]["related_notion_ids"] == ["notion_b"]
    assert raw["notion_a"]["reinforcement_count"] == 3
    assert raw["notion_a"]["person_id"] == "Master"


def test_is_conviction_requires_reinforcements_and_confidence() -> None:
    assert is_conviction(_saved_notion("n1", confidence=0.7, reinforcement_count=5)) is True
    assert is_conviction(_saved_notion("n2", confidence=0.69, reinforcement_count=5)) is False
    assert is_conviction(_saved_notion("n3", confidence=0.9, reinforcement_count=4)) is False


@pytest.mark.parametrize(
    ("memories", "expected"),
    [
        (
            [
                Memory(content="【セッション終了】2026-03-12 04:00 JST", importance=4),
                Memory(content="session end", importance=4),
                Memory(content="goodbye", importance=4),
            ],
            True,
        ),
        (
            [
                Memory(content="short note", importance=1),
                Memory(content="another short note", importance=1),
                Memory(content="still low importance", importance=3),
            ],
            True,
        ),
        (
            [
                Memory(content="pattern forming", importance=4),
                Memory(content="there is a recurring theme", importance=4),
                Memory(content="signal is getting clearer", importance=4),
            ],
            False,
        ),
    ],
)
def test_is_ephemeral_cluster_detects_noise(memories: list[Memory], expected: bool) -> None:
    assert is_ephemeral_cluster(memories) is expected


def test_apply_time_decay_decays_and_prunes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "ego_mcp.notion._now_iso",
        lambda: "2026-03-29T00:00:00+00:00",
    )
    store = NotionStore(tmp_path / "notions.json")
    store.save(
        _saved_notion(
            "notion_decay",
            confidence=0.8,
            created="2026-02-01T00:00:00+00:00",
            last_reinforced="2026-02-01T00:00:00+00:00",
        )
    )
    store.save(
        _saved_notion(
            "notion_prune",
            confidence=0.16,
            created="2026-01-01T00:00:00+00:00",
            last_reinforced="2026-01-01T00:00:00+00:00",
        )
    )

    results = apply_time_decay(store)

    decayed = store.get_by_id("notion_decay")
    pruned = store.get_by_id("notion_prune")

    assert decayed is not None
    assert decayed.confidence < 0.8
    assert pruned is None
    assert results == [("notion_decay", "decayed"), ("notion_prune", "pruned")]


def test_apply_time_decay_skips_recent_and_convictions_decay_more_slowly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ego_mcp.notion._now_iso",
        lambda: "2026-03-29T00:00:00+00:00",
    )
    store = NotionStore(tmp_path / "notions.json")
    store.save(
        _saved_notion(
            "recent",
            confidence=0.7,
            created="2026-03-28T12:00:00+00:00",
            last_reinforced="2026-03-28T12:00:00+00:00",
        )
    )
    store.save(
        _saved_notion(
            "conviction",
            confidence=0.8,
            created="2026-02-01T00:00:00+00:00",
            last_reinforced="2026-02-01T00:00:00+00:00",
            reinforcement_count=5,
        )
    )
    store.save(
        _saved_notion(
            "ordinary",
            confidence=0.8,
            created="2026-02-01T00:00:00+00:00",
            last_reinforced="2026-02-01T00:00:00+00:00",
            reinforcement_count=1,
        )
    )

    apply_time_decay(store)

    recent = store.get_by_id("recent")
    conviction = store.get_by_id("conviction")
    ordinary = store.get_by_id("ordinary")

    assert recent is not None
    assert conviction is not None
    assert ordinary is not None
    assert recent.confidence == 0.7
    assert conviction.confidence > ordinary.confidence


def test_find_duplicate_components_groups_connected_notions(tmp_path: Path) -> None:
    store = NotionStore(tmp_path / "notions.json")
    store.save(_saved_notion("a", source_memory_ids=["m1", "m2", "m3"]))
    store.save(_saved_notion("b", source_memory_ids=["m1", "m2", "m4"]))
    store.save(_saved_notion("c", source_memory_ids=["m2", "m4", "m5"]))
    store.save(_saved_notion("d", source_memory_ids=["z1", "z2", "z3"]))

    components = find_duplicate_components(store, jaccard_threshold=0.5)

    assert components == [["a", "b", "c"]]


def test_find_duplicates_returns_jaccard_pairs(tmp_path: Path) -> None:
    store = NotionStore(tmp_path / "notions.json")
    store.save(_saved_notion("a", source_memory_ids=["m1", "m2", "m3"]))
    store.save(_saved_notion("b", source_memory_ids=["m1", "m2", "m4"]))
    store.save(_saved_notion("c", source_memory_ids=["m2", "m4", "m5"]))
    store.save(_saved_notion("d", source_memory_ids=["z1", "z2", "z3"]))

    pairs = find_duplicates(store, jaccard_threshold=0.5)

    assert pairs == [("a", "b"), ("b", "c")]


def test_notion_store_exposes_design_method_api(tmp_path: Path) -> None:
    store = NotionStore(tmp_path / "notions.json")
    store.save(
        _saved_notion(
            "keep",
            source_memory_ids=["m1", "m2", "m3"],
            related_notion_ids=["linked"],
        )
    )
    store.save(_saved_notion("absorb", source_memory_ids=["m1", "m2", "m4"]))
    store.save(
        _saved_notion(
            "linked",
            source_memory_ids=["z1"],
            related_notion_ids=["keep"],
        )
    )
    store.save(_saved_notion("auto", source_memory_ids=["m2", "m3", "m5"]))

    assert store.find_duplicates(jaccard_threshold=0.5) == [("keep", "absorb"), ("keep", "auto")]
    assert [notion.id for notion in store.get_associated("keep", depth=1)] == ["linked"]

    merged = store.merge_notions("keep", "absorb")
    assert merged is not None

    created = store.auto_link_notions(overlap_threshold=2)
    associated = store.get_associated("keep", depth=1)

    assert created == 1
    assert [notion.id for notion in associated] == ["auto", "linked"]


def test_merge_notions_rewrites_related_links(tmp_path: Path) -> None:
    store = NotionStore(tmp_path / "notions.json")
    store.save(
        _saved_notion(
            "keep",
            source_memory_ids=["m1", "m2"],
            tags=["alpha"],
            related_notion_ids=["absorb", "other"],
            reinforcement_count=2,
            person_id="Master",
        )
    )
    store.save(
        _saved_notion(
            "absorb",
            source_memory_ids=["m2", "m3"],
            tags=["beta"],
            related_notion_ids=["keep"],
            reinforcement_count=4,
        )
    )
    store.save(
        _saved_notion(
            "other",
            source_memory_ids=["m8"],
            related_notion_ids=["absorb"],
        )
    )

    merged = merge_notions(store, "keep", "absorb")

    other = store.get_by_id("other")

    assert merged is not None
    assert merged.id == "keep"
    assert merged.source_memory_ids == ["m1", "m2", "m3"]
    assert merged.tags == ["alpha", "beta"]
    assert merged.related_notion_ids == ["other"]
    assert merged.reinforcement_count == 6
    assert merged.person_id == "Master"
    assert store.get_by_id("absorb") is None
    assert other is not None
    assert other.related_notion_ids == ["keep"]


def test_auto_link_notions_adds_bidirectional_edges(tmp_path: Path) -> None:
    store = NotionStore(tmp_path / "notions.json")
    store.save(_saved_notion("a", source_memory_ids=["m1", "m2", "m3"]))
    store.save(_saved_notion("b", source_memory_ids=["m2", "m3", "m4"]))
    store.save(_saved_notion("c", source_memory_ids=["m8"]))

    created = auto_link_notions(store, overlap_threshold=2)

    a = store.get_by_id("a")
    b = store.get_by_id("b")
    c = store.get_by_id("c")

    assert created == 1
    assert a is not None and a.related_notion_ids == ["b"]
    assert b is not None and b.related_notion_ids == ["a"]
    assert c is not None and c.related_notion_ids == []


def test_auto_link_notions_preserves_existing_manual_links(tmp_path: Path) -> None:
    store = NotionStore(tmp_path / "notions.json")
    store.save(
        _saved_notion(
            "a",
            source_memory_ids=["m1", "m2", "m3"],
            related_notion_ids=["c"],
        )
    )
    store.save(_saved_notion("b", source_memory_ids=["m2", "m3", "m4"]))
    store.save(
        _saved_notion(
            "c",
            source_memory_ids=["z1"],
            related_notion_ids=["a"],
        )
    )

    created = auto_link_notions(store, overlap_threshold=2)

    a = store.get_by_id("a")
    b = store.get_by_id("b")
    c = store.get_by_id("c")

    assert created == 1
    assert a is not None and a.related_notion_ids == ["b", "c"]
    assert b is not None and b.related_notion_ids == ["a"]
    assert c is not None and c.related_notion_ids == ["a"]


def test_auto_link_notions_skips_when_notion_count_exceeds_guard(tmp_path: Path) -> None:
    store = NotionStore(tmp_path / "notions.json")
    store.save(
        _saved_notion(
            "n0",
            source_memory_ids=["m0", "m1", "m2"],
            related_notion_ids=["n1"],
        )
    )
    store.save(
        _saved_notion(
            "n1",
            source_memory_ids=["m1", "m2", "m3"],
            related_notion_ids=["n0"],
        )
    )
    for index in range(2, 201):
        store.save(
            _saved_notion(
                f"n{index}",
                source_memory_ids=[f"m{index}", f"m{index + 1}", f"m{index + 2}"],
            )
        )

    created = auto_link_notions(store, overlap_threshold=2, max_notions=200)

    first = store.get_by_id("n0")
    second = store.get_by_id("n1")
    assert created == 0
    assert first is not None and first.related_notion_ids == ["n1"]
    assert second is not None and second.related_notion_ids == ["n0"]


def test_apply_time_decay_uses_exponential_half_life(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = NotionStore(tmp_path / "notions.json")
    store.save(
        _saved_notion(
            "half_life",
            confidence=0.8,
            created="2026-01-01T00:00:00+00:00",
            last_reinforced="2026-01-31T00:00:00+00:00",
        )
    )
    monkeypatch.setattr(
        "ego_mcp.notion.timezone_utils.now",
        lambda: datetime.fromisoformat("2026-03-02T00:00:00+00:00"),
    )

    outcomes = apply_time_decay(store)

    updated = store.get_by_id("half_life")
    assert outcomes == [("half_life", "decayed")]
    assert updated is not None
    assert updated.confidence == pytest.approx(0.4)


def test_get_associated_walks_breadth_first_by_depth(tmp_path: Path) -> None:
    store = NotionStore(tmp_path / "notions.json")
    store.save(_saved_notion("a", related_notion_ids=["b", "c"], confidence=0.9))
    store.save(_saved_notion("b", related_notion_ids=["a", "d"], confidence=0.7))
    store.save(_saved_notion("c", related_notion_ids=["a"], confidence=0.8))
    store.save(_saved_notion("d", related_notion_ids=["b"], confidence=0.6))

    depth_1 = get_associated(store, "a", depth=1)
    depth_2 = get_associated(store, "a", depth=2)

    assert [notion.id for notion in depth_1] == ["c", "b"]
    assert [notion.id for notion in depth_2] == ["c", "b", "d"]


def test_infer_person_id_requires_majority_overlap() -> None:
    assert (
        infer_person_id(
            ["m1", "m2", "m3"],
            {
                "Master": {"m1", "m2", "m9"},
                "Friend": {"m3"},
            },
        )
        == "Master"
    )
    assert (
        infer_person_id(
            ["m1", "m2", "m3", "m4"],
            {
                "Master": {"m1", "m2"},
                "Friend": {"m3", "m4"},
            },
        )
        == ""
    )


def test_merge_notions_rewrites_meta_fields_notion_ids(
    tmp_path: Path,
) -> None:
    store = NotionStore(tmp_path / "notions.json")
    store.save(
        Notion(
            id="keep",
            label="Keep notion",
            confidence=0.8,
            reinforcement_count=2,
            meta_fields={
                "ref": {"type": "notion_ids", "notion_ids": ["absorb"]},
            },
        )
    )
    store.save(
        Notion(
            id="absorb",
            label="Absorb notion",
            confidence=0.7,
            reinforcement_count=1,
            meta_fields={
                "self_ref": {"type": "notion_ids", "notion_ids": ["absorb"]},
            },
        )
    )
    store.save(
        Notion(
            id="other",
            label="Other notion",
            confidence=0.6,
            reinforcement_count=1,
            meta_fields={
                "points_to_absorb": {"type": "notion_ids", "notion_ids": ["absorb", "keep"]},
            },
        )
    )

    merged = merge_notions(store, "keep", "absorb")

    assert merged is not None
    assert merged.meta_fields["ref"] == {"type": "notion_ids", "notion_ids": []}
    assert merged.meta_fields["self_ref"] == {"type": "notion_ids", "notion_ids": []}
    other = store.get_by_id("other")
    assert other is not None
    assert other.meta_fields["points_to_absorb"] == {
        "type": "notion_ids",
        "notion_ids": ["keep"],
    }


def test_merge_notions_does_not_rewrite_unrelated_meta_fields(
    tmp_path: Path,
) -> None:
    store = NotionStore(tmp_path / "notions.json")
    store.save(
        Notion(
            id="keep",
            label="Keep notion",
            confidence=0.8,
            reinforcement_count=2,
            meta_fields={
                "note": {"type": "text", "value": "hello"},
                "path_ref": {"type": "file_path", "path": "data.txt"},
                "ids_ref": {"type": "notion_ids", "notion_ids": ["keep"]},
            },
        )
    )
    store.save(
        Notion(
            id="absorb",
            label="Absorb notion",
            confidence=0.7,
            reinforcement_count=1,
            meta_fields={
                "ids_ref": {"type": "notion_ids", "notion_ids": ["absorb"]},
            },
        )
    )

    merged = merge_notions(store, "keep", "absorb")

    assert merged is not None
    assert merged.meta_fields["note"] == {"type": "text", "value": "hello"}
    assert merged.meta_fields["path_ref"] == {"type": "file_path", "path": "data.txt"}
    assert merged.meta_fields["ids_ref"] == {"type": "notion_ids", "notion_ids": []}


def test_find_dead_links_reports_missing_file_path(tmp_path: Path) -> None:
    from ego_mcp.notion import find_dead_links

    store = NotionStore(tmp_path / "notions.json")
    store.save(
        Notion(
            id="n1",
            label="notion with dead file",
            confidence=0.5,
            created="2026-01-01T00:00:00+00:00",
            meta_fields={
                "bad_file": {"type": "file_path", "path": "nonexistent.txt"},
            },
        )
    )

    dead = find_dead_links(store, tmp_path)

    assert len(dead) == 1
    assert dead[0].notion_id == "n1"
    assert dead[0].meta_key == "bad_file"
    assert dead[0].link_type == "file_path"
    assert dead[0].dead_targets == ["nonexistent.txt"]


def test_find_dead_links_reports_directory_as_dead_file_path(tmp_path: Path) -> None:
    from ego_mcp.notion import find_dead_links

    store = NotionStore(tmp_path / "notions.json")
    sub_dir = tmp_path / "some_dir"
    sub_dir.mkdir()
    store.save(
        Notion(
            id="n1",
            label="notion with dir reference",
            confidence=0.5,
            created="2026-01-01T00:00:00+00:00",
            meta_fields={
                "dir_ref": {"type": "file_path", "path": "some_dir"},
            },
        )
    )

    dead = find_dead_links(store, tmp_path)

    assert len(dead) == 1
    assert dead[0].notion_id == "n1"
    assert dead[0].meta_key == "dir_ref"
    assert dead[0].link_type == "file_path"


def test_find_dead_links_reports_missing_notion_ids(tmp_path: Path) -> None:
    from ego_mcp.notion import find_dead_links

    store = NotionStore(tmp_path / "notions.json")
    store.save(
        Notion(
            id="n1",
            label="notion with dead notion_ids",
            confidence=0.5,
            created="2026-01-01T00:00:00+00:00",
            meta_fields={
                "bad_ids": {"type": "notion_ids", "notion_ids": ["ghost_notion"]},
            },
        )
    )

    dead = find_dead_links(store, tmp_path)

    assert len(dead) == 1
    assert dead[0].notion_id == "n1"
    assert dead[0].meta_key == "bad_ids"
    assert dead[0].link_type == "notion_ids"
    assert dead[0].dead_targets == ["ghost_notion"]


def test_find_dead_links_healthy_meta_fields_not_reported(tmp_path: Path) -> None:
    from ego_mcp.notion import find_dead_links

    store = NotionStore(tmp_path / "notions.json")
    store.save(
        Notion(
            id="n1",
            label="healthy notion",
            confidence=0.5,
            created="2026-01-01T00:00:00+00:00",
            meta_fields={
                "good_file": {"type": "file_path", "path": "exists.txt"},
                "good_ids": {"type": "notion_ids", "notion_ids": ["n1"]},
            },
        )
    )
    (tmp_path / "exists.txt").write_text("hello")

    dead = find_dead_links(store, tmp_path)

    assert len(dead) == 0
