"""Transient impulse boosts triggered by Proust-style recall."""

from __future__ import annotations

from datetime import datetime, timedelta

from ego_mcp import timezone_utils
from ego_mcp.types import Emotion, Memory

_EMOTION_TO_DESIRE: dict[Emotion, tuple[str, float]] = {
    Emotion.EXCITED: ("curiosity", 0.15),
    Emotion.CURIOUS: ("information_hunger", 0.15),
    Emotion.SAD: ("social_thirst", 0.15),
    Emotion.MELANCHOLY: ("social_thirst", 0.15),
    Emotion.FRUSTRATED: ("expression", 0.10),
    Emotion.ANXIOUS: ("cognitive_coherence", 0.15),
    Emotion.HAPPY: ("expression", 0.10),
    Emotion.CONTENTMENT: ("expression", 0.10),
    Emotion.NOSTALGIC: ("resonance", 0.15),
    Emotion.SURPRISED: ("curiosity", 0.20),
    Emotion.MOVED: ("expression", 0.15),
}


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone_utils.app_timezone())
    return parsed


class ImpulseManager:
    def __init__(self) -> None:
        self._pending_boosts: dict[str, float] = {}
        self._cooldowns: dict[str, str] = {}
        self._pending_events: list[dict[str, object]] = []

    def _prune_cooldowns(self) -> None:
        now = timezone_utils.now()
        active: dict[str, str] = {}
        for memory_id, expiry in self._cooldowns.items():
            parsed = _parse_iso(expiry)
            if parsed is not None and parsed > now:
                active[memory_id] = expiry
        self._cooldowns = active

    def register_proust_event(
        self, memory: Memory, cooldown_hours: float = 72.0
    ) -> dict[str, float]:
        """Register a Proust event and schedule a one-shot desire boost."""
        self._prune_cooldowns()
        if memory.id in self._cooldowns:
            return {}

        mapping = _EMOTION_TO_DESIRE.get(memory.emotional_trace.primary)
        if mapping is None:
            return {}

        desire_name, amount = mapping
        clamped_amount = min(0.2, max(0.0, amount))
        current = self._pending_boosts.get(desire_name, 0.0)
        self._pending_boosts[desire_name] = min(0.2, current + clamped_amount)
        expiry = timezone_utils.now() + timedelta(hours=max(0.0, cooldown_hours))
        self._cooldowns[memory.id] = expiry.isoformat()
        self._pending_events.append(
            {
                "impulse_boost_triggered": True,
                "impulse_source_memory_id": memory.id,
                "impulse_boosted_desire": desire_name,
                "impulse_boost_amount": self._pending_boosts[desire_name],
            }
        )
        return dict(self._pending_boosts)

    def consume_boosts(self) -> dict[str, float]:
        boosts = dict(self._pending_boosts)
        self._pending_boosts.clear()
        return boosts

    def consume_event(self) -> dict[str, object]:
        if not self._pending_events:
            return {}

        events = [dict(event) for event in self._pending_events]
        self._pending_events.clear()
        if len(events) == 1:
            return events[0]

        memory_ids = [
            str(event["impulse_source_memory_id"])
            for event in events
            if event.get("impulse_source_memory_id")
        ]
        desires = [
            str(event["impulse_boosted_desire"])
            for event in events
            if event.get("impulse_boosted_desire")
        ]
        amounts: list[float] = []
        for event in events:
            raw_amount = event.get("impulse_boost_amount")
            if isinstance(raw_amount, (int, float)):
                amounts.append(float(raw_amount))
        merged = dict(events[-1])
        merged.update(
            {
                "impulse_boost_triggered": True,
                "impulse_event_count": len(events),
                "impulse_source_memory_ids": ",".join(memory_ids),
                "impulse_boosted_desires": ",".join(desires),
                "impulse_boost_amounts": ",".join(
                    f"{amount:.2f}" for amount in amounts
                ),
            }
        )
        return merged
