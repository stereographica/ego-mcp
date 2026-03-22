"""Deterministic language blending for desire summaries."""

from __future__ import annotations

from collections.abc import Sequence

_TEMPLATES: dict[str, tuple[str, str]] = {
    "curiosity": (
        "Something catches your attention.",
        "You need to know something.",
    ),
    "social_thirst": (
        "You want some company.",
        "You need to talk to someone.",
    ),
    "expression": (
        "Something wants to come out.",
        "You need to put something out there.",
    ),
    "cognitive_coherence": (
        "Something doesn't quite fit.",
        "You need things to make sense.",
    ),
    "information_hunger": (
        "You want to take something in.",
        "You're starving for input.",
    ),
    "pattern_seeking": (
        "You sense a pattern forming.",
        "There's a shape here you need to see.",
    ),
    "predictability": (
        "You want to know what comes next.",
        "You need to know what's coming.",
    ),
    "recognition": (
        "You want to be seen.",
        "You need someone to notice.",
    ),
    "resonance": (
        "You want to understand someone.",
        "You need to feel what they feel.",
    ),
}

_DEFAULT_LOW_SIGNAL = "Nothing in particular pulls at you."
_AMBIGUOUS_TAIL = "Something else stirs, but you can't name it."


def _render_sentence(name: str, level: float) -> str:
    templates = _TEMPLATES.get(name)
    if templates is None:
        return name if name.endswith(".") else f"{name}."
    return templates[1] if level >= 0.7 else templates[0]


def _sorted_active(levels: dict[str, float]) -> list[tuple[str, float]]:
    return sorted(
        (
            (name, value)
            for name, value in levels.items()
            if isinstance(value, (int, float)) and float(value) >= 0.4
        ),
        key=lambda item: (-float(item[1]), item[0]),
    )


def _has_ambiguous_tail(active: Sequence[tuple[str, float]]) -> bool:
    has_high = any(float(level) >= 0.7 for _, level in active)
    medium_count = sum(1 for _, level in active if 0.4 <= float(level) < 0.55)
    return has_high and medium_count >= 2


def blend_desires(levels: dict[str, float]) -> str:
    """Blend top desire signals into opaque, directional language."""
    active = _sorted_active(levels)
    if not active:
        return _DEFAULT_LOW_SIGNAL

    top = active[:3]
    sentences = [_render_sentence(name, float(level)) for name, level in top]
    if _has_ambiguous_tail(active):
        sentences.append(_AMBIGUOUS_TAIL)
    return " ".join(sentences)
