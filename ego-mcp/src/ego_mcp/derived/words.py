"""Number-to-word helpers shared by derived lenses (future_plan article 4).

Numbers are never shown as digits in tool responses; both the recurrence lens
(D1) and the chapter lens (D5) render counts and spans as words.
"""

from __future__ import annotations

_NUMBER_WORDS: tuple[str, ...] = (
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
)

MANY = "many"


def count_words(n: int) -> str:
    """Render a count as a word: one..ten, anything else as "many".

    Zero and negative counts have no natural word here and fall back to "many"
    as well; callers gate on emptiness before rendering a count.
    """
    if 1 <= n <= len(_NUMBER_WORDS):
        return _NUMBER_WORDS[n - 1]
    return MANY


def span_words(period: str, span: int) -> str:
    """Render a calendar span as words.

    ``("year", 1)`` -> "a year ago", ``("year", 3)`` -> "three years ago",
    ``("year", 11)`` -> "many years ago", ``("half_year", _)`` ->
    "half a year ago". Unknown periods fall back to the year wording.
    """
    if period == "half_year":
        return "half a year ago"
    if span <= 1:
        return "a year ago"
    if span <= len(_NUMBER_WORDS):
        return f"{_NUMBER_WORDS[span - 1]} years ago"
    return f"{MANY} years ago"
