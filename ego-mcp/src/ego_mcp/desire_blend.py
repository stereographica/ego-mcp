"""Deterministic language blending for desire summaries."""

from __future__ import annotations

from collections.abc import Sequence

from ego_mcp.desire_catalog import DesireCatalog, default_desire_catalog
from ego_mcp.emergent_desires import emergent_desire_sentence

_TEMPLATES: dict[str, tuple[str, str]] = default_desire_catalog().template_map()

_DEFAULT_LOW_SIGNAL = "Nothing in particular pulls at you."
_AMBIGUOUS_TAIL = "Something else stirs, but you can't name it."


def _render_sentence(
    name: str,
    level: float,
    catalog: DesireCatalog | None = None,
) -> str:
    template_map = catalog.template_map() if catalog is not None else _TEMPLATES
    templates = template_map.get(name)
    if templates is None:
        emergent_sentence = emergent_desire_sentence(name)
        if emergent_sentence is not None:
            return emergent_sentence
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


def blend_desires(
    levels: dict[str, float],
    *,
    catalog: DesireCatalog | None = None,
) -> str:
    """Blend top desire signals into opaque, directional language."""
    active = _sorted_active(levels)
    if not active:
        return _DEFAULT_LOW_SIGNAL

    top = active[:3]
    sentences = [
        _render_sentence(name, float(level), catalog=catalog) for name, level in top
    ]
    if _has_ambiguous_tail(active):
        sentences.append(_AMBIGUOUS_TAIL)
    return " ".join(sentences)
