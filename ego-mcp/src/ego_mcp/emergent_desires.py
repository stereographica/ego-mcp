"""Shared emergent desire identifiers and sentence mappings."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class EmergentDesireDefinition:
    """Stable internal ID plus language surfaces for emergent desires."""

    id: str
    legacy_sentence: str
    fragment: str
    sentences: Mapping[str, str]


EMERGENT_DESIRE_DEFINITIONS: tuple[EmergentDesireDefinition, ...] = (
    EmergentDesireDefinition(
        id="be_with_someone",
        legacy_sentence="You want to be with someone.",
        fragment="be with someone",
        sentences={
            "rising": "Something in this reaches toward company.",
            "steady": "The wish for company sits quietly underneath.",
            "settling": "The reach toward others is easing.",
        },
    ),
    EmergentDesireDefinition(
        id="get_away_from_something",
        legacy_sentence="You want to get away from something.",
        fragment="get away from something",
        sentences={
            "rising": "Something here wants distance.",
            "steady": "That urge for distance is still around.",
            "settling": "The need for distance is loosening.",
        },
    ),
    EmergentDesireDefinition(
        id="feel_safe",
        legacy_sentence="You want to feel safe.",
        fragment="feel safe",
        sentences={
            "rising": "Something is asking for solid ground.",
            "steady": "The wish for steadier footing lingers.",
            "settling": "The ground feels a little steadier.",
        },
    ),
    EmergentDesireDefinition(
        id="grasp_something",
        legacy_sentence="You want to grasp something.",
        fragment="grasp something",
        sentences={
            "rising": "There's a pull toward something that doesn't have a name yet.",
            "steady": "That unnamed something is still there, quietly.",
            "settling": "Whatever was pulling — it's letting go.",
        },
    ),
    EmergentDesireDefinition(
        id="stay_in_this",
        legacy_sentence="You want to stay in this.",
        fragment="stay in this",
        sentences={
            "rising": "There's a wish to let this moment stay.",
            "steady": "The wish to linger is still here.",
            "settling": "That wish to linger is fading.",
        },
    ),
    EmergentDesireDefinition(
        id="go_back_to_something",
        legacy_sentence="You want to go back to something.",
        fragment="go back to something",
        sentences={
            "rising": "Something behind is calling back.",
            "steady": "That backward pull is still there, faint.",
            "settling": "The past is settling back into place.",
        },
    ),
)

EMERGENT_DESIRE_BY_ID: dict[str, EmergentDesireDefinition] = {
    item.id: item for item in EMERGENT_DESIRE_DEFINITIONS
}
EMERGENT_DESIRE_ID_BY_SENTENCE: dict[str, str] = {
    item.legacy_sentence: item.id for item in EMERGENT_DESIRE_DEFINITIONS
}


def canonical_emergent_desire_id(name: str) -> str:
    """Map a legacy sentence key to its stable emergent desire ID."""
    return EMERGENT_DESIRE_ID_BY_SENTENCE.get(name, name)


def emergent_desire_sentence(name: str, direction: str = "steady") -> str | None:
    """Return the sentence for an emergent desire ID or legacy sentence."""
    definition = EMERGENT_DESIRE_BY_ID.get(canonical_emergent_desire_id(name))
    if definition is None:
        return None
    return definition.sentences.get(direction, definition.sentences["steady"])


def emergent_desire_fragment(name: str) -> str | None:
    """Return the ember fragment for an emergent desire ID or legacy sentence."""
    definition = EMERGENT_DESIRE_BY_ID.get(canonical_emergent_desire_id(name))
    if definition is None:
        return None
    return definition.fragment
