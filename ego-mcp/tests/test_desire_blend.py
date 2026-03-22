"""Tests for desire blending text generation."""

from __future__ import annotations

from ego_mcp.desire_blend import blend_desires


def test_blend_desires_uses_top_signals() -> None:
    text = blend_desires(
        {
            "curiosity": 0.82,
            "social_thirst": 0.52,
            "expression": 0.44,
            "predictability": 0.20,
        }
    )

    assert "You need to know something." in text
    assert "You want some company." in text
    assert "Something wants to come out." in text
    assert not any(character.isdigit() for character in text)
    assert "curiosity" not in text.lower()
    assert "social_thirst" not in text.lower()
    assert "expression" not in text.lower()


def test_blend_desires_adds_ambiguity_tail_for_mixed_pressure() -> None:
    text = blend_desires(
        {
            "curiosity": 0.9,
            "social_thirst": 0.52,
            "expression": 0.48,
            "recognition": 0.5,
        }
    )

    assert "Something else stirs, but you can't name it." in text


def test_blend_desires_returns_low_signal_when_inactive() -> None:
    assert blend_desires({"curiosity": 0.1, "social_thirst": 0.2}) == (
        "Nothing in particular pulls at you."
    )
