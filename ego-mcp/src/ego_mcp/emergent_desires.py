"""Shared emergent desire identifiers and sentence mappings."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EmergentDesireDefinition:
    """Stable internal ID plus the sentence shown to the model."""

    id: str
    sentence: str


EMERGENT_DESIRE_DEFINITIONS: tuple[EmergentDesireDefinition, ...] = (
    EmergentDesireDefinition(
        id="be_with_someone",
        sentence="You want to be with someone.",
    ),
    EmergentDesireDefinition(
        id="get_away_from_something",
        sentence="You want to get away from something.",
    ),
    EmergentDesireDefinition(
        id="feel_safe",
        sentence="You want to feel safe.",
    ),
    EmergentDesireDefinition(
        id="grasp_something",
        sentence="You want to grasp something.",
    ),
    EmergentDesireDefinition(
        id="stay_in_this",
        sentence="You want to stay in this.",
    ),
    EmergentDesireDefinition(
        id="go_back_to_something",
        sentence="You want to go back to something.",
    ),
)

EMERGENT_DESIRE_BY_ID: dict[str, EmergentDesireDefinition] = {
    item.id: item for item in EMERGENT_DESIRE_DEFINITIONS
}
EMERGENT_DESIRE_ID_BY_SENTENCE: dict[str, str] = {
    item.sentence: item.id for item in EMERGENT_DESIRE_DEFINITIONS
}


def canonical_emergent_desire_id(name: str) -> str:
    """Map a legacy sentence key to its stable emergent desire ID."""
    return EMERGENT_DESIRE_ID_BY_SENTENCE.get(name, name)


def emergent_desire_sentence(name: str) -> str | None:
    """Return the sentence for an emergent desire ID or legacy sentence."""
    definition = EMERGENT_DESIRE_BY_ID.get(canonical_emergent_desire_id(name))
    if definition is None:
        return None
    return definition.sentence
