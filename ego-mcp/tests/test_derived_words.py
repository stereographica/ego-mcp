"""Tests for derived/words.py (D1 S2 vocabulary)."""

from __future__ import annotations

import pytest

from ego_mcp.derived.words import count_words, span_words


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (1, "one"),
        (2, "two"),
        (3, "three"),
        (4, "four"),
        (5, "five"),
        (6, "six"),
        (7, "seven"),
        (8, "eight"),
        (9, "nine"),
        (10, "ten"),
        (11, "many"),
        (137, "many"),
        (0, "many"),
        (-3, "many"),
    ],
)
def test_count_words(n: int, expected: str) -> None:
    assert count_words(n) == expected


@pytest.mark.parametrize(
    ("period", "span", "expected"),
    [
        ("year", 1, "a year ago"),
        ("year", 2, "two years ago"),
        ("year", 3, "three years ago"),
        ("year", 10, "ten years ago"),
        ("year", 11, "many years ago"),
        ("half_year", 1, "half a year ago"),
        ("half_year", 7, "half a year ago"),
    ],
)
def test_span_words(period: str, span: int, expected: str) -> None:
    assert span_words(period, span) == expected


def test_span_words_treats_zero_span_as_one_year() -> None:
    assert span_words("year", 0) == "a year ago"


def test_span_words_unknown_period_falls_back_to_years() -> None:
    assert span_words("decade", 2) == "two years ago"
