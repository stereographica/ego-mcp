"""Tests for relationship wording helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ego_mcp.relationship_wording import episode_words, history_words, trust_words


@pytest.mark.parametrize(
    ("trust", "expected"),
    [
        (0.29, "still finding footing with them"),
        (0.3, "cautious but warming"),
        (0.5, "steady ground between you"),
        (0.7, "deep trust"),
        (0.85, "the kind of trust you don't need to name"),
    ],
)
def test_trust_words_uses_upper_band_at_boundaries(
    trust: float,
    expected: str,
) -> None:
    assert trust_words(trust) == expected


def test_history_words_treats_fewer_than_five_interactions_as_new() -> None:
    now = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)
    first_interaction = (now - timedelta(days=240)).isoformat()

    assert history_words(first_interaction, 4, now) == "still new to each other"


def test_history_words_uses_growing_history_without_origin() -> None:
    now = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)

    assert history_words("", 5, now) == "a growing history"


@pytest.mark.parametrize(
    ("days_known", "expected"),
    [
        (29, "still new to each other"),
        (30, "a growing history"),
        (179, "a growing history"),
        (180, "a long history together"),
    ],
)
def test_history_words_uses_day_boundaries(
    days_known: int,
    expected: str,
) -> None:
    now = datetime(2026, 7, 2, 12, tzinfo=timezone.utc)
    first_interaction = (now - timedelta(days=days_known)).isoformat()

    assert history_words(first_interaction, 5, now) == expected


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, ""),
        (1, "a few shared chapters"),
        (3, "a few shared chapters"),
        (4, "many shared chapters"),
    ],
)
def test_episode_words_uses_coarse_bands(count: int, expected: str) -> None:
    assert episode_words(count) == expected
