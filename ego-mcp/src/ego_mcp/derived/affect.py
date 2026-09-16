"""Affect lens: how the emotion of shared memories has moved (P2 S1).

Per interlocutor, the mean valence and arousal of the memories shared in the
last thirty days are compared with those of the ninety days before them. The
lens emits ids, numbers and mechanism vocabulary only — ``brighter`` /
``darker`` / ``livelier`` / ``quieter`` / ``steady`` — never prose and never a
guess about the other person's state (P2 D3).

``compute`` is a pure function of the snapshot: the only clock it reads is
``snapshot.now``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ego_mcp import timezone_utils
from ego_mcp.derived.source import SourceSnapshot
from ego_mcp.types import Memory

LENS_NAME = "affect"
AFFECT_TTL_HOURS = 168.0
AFFECT_RECENT_DAYS = 30
AFFECT_PRIOR_DAYS = 90
AFFECT_MIN_PER_WINDOW = 4
AFFECT_VALENCE_STEP = 0.20
AFFECT_AROUSAL_STEP = 0.15

#: End of the prior window, in days of age: ``[30, 120)``.
AFFECT_PRIOR_END_DAYS = AFFECT_RECENT_DAYS + AFFECT_PRIOR_DAYS

#: ``dv`` / ``da`` are rounded to this many decimals *before* the thresholds are
#: applied, so the stored numbers and the stored directions always agree and
#: float noise cannot push an exact 0.20 below the step.
AFFECT_DECIMALS = 3

DIRECTION_STEADY = "steady"
DIRECTION_BRIGHTER = "brighter"
DIRECTION_DARKER = "darker"
DIRECTION_LIVELIER = "livelier"
DIRECTION_QUIETER = "quieter"

#: ``relation_kind`` of a person we actually talk with; ``mentioned`` people are
#: out of scope because there is no shared time to trace (P2 D1).
INTERLOCUTOR_KIND = "interlocutor"


def valence_direction(dv: float) -> str:
    """Name the valence movement: ``brighter`` / ``darker`` / ``steady``."""
    if dv >= AFFECT_VALENCE_STEP:
        return DIRECTION_BRIGHTER
    if dv <= -AFFECT_VALENCE_STEP:
        return DIRECTION_DARKER
    return DIRECTION_STEADY


def arousal_direction(da: float) -> str:
    """Name the arousal movement: ``livelier`` / ``quieter`` / ``steady``."""
    if da >= AFFECT_AROUSAL_STEP:
        return DIRECTION_LIVELIER
    if da <= -AFFECT_AROUSAL_STEP:
        return DIRECTION_QUIETER
    return DIRECTION_STEADY


def _parse_time(value: Any) -> datetime | None:
    """Parse an ISO timestamp, returning ``None`` for anything unusable."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return timezone_utils.localize(parsed)


def _age_days(memory: Memory, now: datetime) -> float | None:
    """Age of ``memory`` in days, or ``None`` when the timestamp is unusable.

    A memory we cannot place in time belongs in neither window: it would move a
    mean without being evidence of *when* that feeling happened.
    """
    parsed = _parse_time(memory.timestamp)
    if parsed is None:
        return None
    elapsed = (timezone_utils.localize(now) - parsed).total_seconds()
    return elapsed / 86400.0


def _interlocutor_ids(snapshot: SourceSnapshot) -> list[str]:
    """Person ids whose relationship model is (or defaults to) an interlocutor."""
    return sorted(
        person_id
        for person_id, raw in snapshot.relationships.items()
        if raw.get("relation_kind", INTERLOCUTOR_KIND) == INTERLOCUTOR_KIND
    )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _round(value: float) -> float:
    return round(value, AFFECT_DECIMALS)


class AffectLens:
    """The trajectory of the emotion carried by memories shared with a person."""

    name = LENS_NAME
    needs_embeddings = False
    ttl_hours = AFFECT_TTL_HOURS

    def compute(self, snapshot: SourceSnapshot) -> list[dict[str, Any]]:
        generated_date = snapshot.now.date().isoformat()

        # Age every memory once: the person loop below only re-filters.
        # Private memories are kept — this is a statistic of *our own* feeling.
        dated: list[tuple[Memory, float]] = []
        for memory in snapshot.memories:
            age = _age_days(memory, snapshot.now)
            if age is None or age >= AFFECT_PRIOR_END_DAYS:
                continue
            dated.append((memory, age))

        items: list[dict[str, Any]] = []
        for person_id in _interlocutor_ids(snapshot):
            recent_valence: list[float] = []
            recent_arousal: list[float] = []
            prior_valence: list[float] = []
            prior_arousal: list[float] = []
            for memory, age in dated:
                if person_id not in memory.involved_person_ids:
                    continue
                trace = memory.emotional_trace
                if age < AFFECT_RECENT_DAYS:
                    recent_valence.append(float(trace.valence))
                    recent_arousal.append(float(trace.arousal))
                else:
                    prior_valence.append(float(trace.valence))
                    prior_arousal.append(float(trace.arousal))

            n_recent = len(recent_valence)
            n_prior = len(prior_valence)
            if n_recent < AFFECT_MIN_PER_WINDOW or n_prior < AFFECT_MIN_PER_WINDOW:
                continue

            dv = _round(_mean(recent_valence) - _mean(prior_valence))
            da = _round(_mean(recent_arousal) - _mean(prior_arousal))
            # Both-steady persons stay in the file: the dashboard shows them,
            # consider_them simply says nothing (P2 D1 / D2).
            items.append(
                {
                    "key": f"{LENS_NAME}:{person_id}:{generated_date}",
                    "person_id": person_id,
                    "dv": dv,
                    "da": da,
                    "valence_direction": valence_direction(dv),
                    "arousal_direction": arousal_direction(da),
                    "n_recent": n_recent,
                    "n_prior": n_prior,
                }
            )
        return items
