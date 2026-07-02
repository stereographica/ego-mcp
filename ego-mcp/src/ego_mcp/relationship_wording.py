"""Worded relationship summaries for surface responses."""

from __future__ import annotations

from datetime import datetime

from ego_mcp import timezone_utils


def trust_words(trust: float) -> str:
    low_trust_max = 0.3
    cautious_trust_max = 0.5
    steady_trust_max = 0.7
    deep_trust_max = 0.85

    if trust < low_trust_max:
        return "still finding footing with them"
    if trust < cautious_trust_max:
        return "cautious but warming"
    if trust < steady_trust_max:
        return "steady ground between you"
    if trust < deep_trust_max:
        return "deep trust"
    return "the kind of trust you don't need to name"


def history_words(first_interaction: str, total_interactions: int, now: datetime) -> str:
    if total_interactions < 5:
        return "still new to each other"

    days_known: float | None = None
    if first_interaction.strip():
        try:
            parsed = timezone_utils.localize(datetime.fromisoformat(first_interaction))
        except ValueError:
            parsed = None
        if parsed is not None:
            localized_now = timezone_utils.localize(now)
            days_known = max(0.0, (localized_now - parsed).total_seconds() / 86400.0)

    if days_known is None:
        return "a growing history"
    if days_known < 30:
        return "still new to each other"
    if days_known < 180:
        return "a growing history"
    return "a long history together"


def episode_words(count: int) -> str:
    if count == 0:
        return ""
    if count <= 3:
        return "a few shared chapters"
    return "many shared chapters"
