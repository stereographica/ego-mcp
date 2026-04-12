"""Deterministic language blending for desire summaries."""

from __future__ import annotations

from collections.abc import Sequence

from ego_mcp.desire_catalog import DesireCatalog, default_desire_catalog
from ego_mcp.emergent_desires import emergent_desire_sentence

_TEMPLATES: dict[str, dict[str, str]] = default_desire_catalog().template_map()

_DEFAULT_LOW_SIGNAL = "Nothing in particular pulls at you right now."
_AMBIGUOUS_TAIL = "Something else stirs, but you can't name it yet."


def _direction(level: float, ema: float) -> str:
    """Determine desire direction relative to EMA baseline."""
    if level > ema + 0.15:
        return "rising"
    if level < ema - 0.15:
        return "settling"
    return "steady"


def _render_sentence(
    name: str,
    level: float,
    *,
    ema: float | None = None,
    catalog: DesireCatalog | None = None,
) -> str:
    template_map = catalog.template_map() if catalog is not None else _TEMPLATES
    templates = template_map.get(name)
    if templates is None:
        emergent_sentence = emergent_desire_sentence(name)
        if emergent_sentence is not None:
            return emergent_sentence
        return name if name.endswith(".") else f"{name}."
    direction = _direction(level, ema if ema is not None else 0.5)
    return templates.get(direction, templates.get("steady", ""))


def _sorted_active(levels: dict[str, float]) -> list[tuple[str, float]]:
    return sorted(
        (
            (name, value)
            for name, value in levels.items()
            if isinstance(value, (int, float)) and float(value) >= 0.3
        ),
        key=lambda item: (-float(item[1]), item[0]),
    )


def _has_ambiguous_tail(active: Sequence[tuple[str, float]]) -> bool:
    remaining = active[3:]
    return bool(remaining) and any(float(level) > 0.5 for _, level in remaining)


def blend_desires(
    levels: dict[str, float],
    *,
    ema_levels: dict[str, float] | None = None,
    catalog: DesireCatalog | None = None,
) -> str:
    """Blend top desire signals into opaque, directional language."""
    active = _sorted_active(levels)
    if not active:
        return _DEFAULT_LOW_SIGNAL

    top = active[:3]
    sentences = [
        _render_sentence(
            name,
            float(level),
            ema=(ema_levels or {}).get(name),
            catalog=catalog,
        )
        for name, level in top
    ]
    if _has_ambiguous_tail(active):
        sentences.append(_AMBIGUOUS_TAIL)
    return " ".join(sentences)
