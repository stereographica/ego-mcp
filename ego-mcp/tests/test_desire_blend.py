"""Tests for desire blending text generation."""

from __future__ import annotations

from ego_mcp.desire_blend import _direction, blend_desires


def test_blend_desires_uses_top_signals() -> None:
    text = blend_desires(
        {
            "curiosity": 0.82,
            "social_thirst": 0.52,
            "expression": 0.44,
        }
    )
    # With default ema (0.5), curiosity 0.82 is rising, social_thirst 0.52 is steady,
    # expression 0.44 is steady
    assert "Something caught your attention" in text
    assert "quiet wish for company" in text or "familiar pressure to express" in text
    assert not any(character.isdigit() for character in text)
    assert "curiosity" not in text.lower()
    assert "social_thirst" not in text.lower()
    assert "expression" not in text.lower()


def test_blend_desires_with_ema_rising() -> None:
    text = blend_desires(
        {"curiosity": 0.8},
        ema_levels={"curiosity": 0.5},
    )
    # 0.8 > 0.5 + 0.15 → rising
    assert "Something caught your attention and it won't let go." in text


def test_blend_desires_with_ema_steady() -> None:
    text = blend_desires(
        {"curiosity": 0.55},
        ema_levels={"curiosity": 0.5},
    )
    # |0.55 - 0.5| = 0.05 ≤ 0.15 → steady
    assert "A quiet wondering about something." in text


def test_blend_desires_with_ema_settling() -> None:
    text = blend_desires(
        {"curiosity": 0.32},
        ema_levels={"curiosity": 0.6},
    )
    # 0.32 < 0.6 - 0.15 → settling
    assert "The itch to know has settled for now." in text


def test_blend_desires_adds_ambiguity_tail() -> None:
    text = blend_desires(
        {
            "curiosity": 0.9,
            "social_thirst": 0.75,
            "expression": 0.7,
            "recognition": 0.55,
        }
    )
    # recognition (0.55 > 0.5) is 4th, so ambiguous tail fires
    assert "Something else stirs, but you can't name it yet." in text


def test_blend_desires_returns_low_signal_when_inactive() -> None:
    assert blend_desires({"curiosity": 0.1, "social_thirst": 0.2}) == (
        "Nothing in particular pulls at you right now."
    )


def test_threshold_is_0_3() -> None:
    """Desires at 0.3 should be included (lowered from 0.4)."""
    text = blend_desires({"curiosity": 0.3})
    assert text != "Nothing in particular pulls at you right now."


def test_below_threshold_excluded() -> None:
    text = blend_desires({"curiosity": 0.29})
    assert text == "Nothing in particular pulls at you right now."


def test_direction_rising() -> None:
    assert _direction(0.8, 0.5) == "rising"


def test_direction_steady() -> None:
    assert _direction(0.55, 0.5) == "steady"


def test_direction_settling() -> None:
    assert _direction(0.3, 0.6) == "settling"


def test_direction_boundary_rising() -> None:
    # Exactly at boundary: 0.65 + 0.15 = 0.80, so 0.66 is NOT > 0.65+0.15
    assert _direction(0.65 + 0.15, 0.65) == "steady"
    assert _direction(0.65 + 0.16, 0.65) == "rising"


def test_direction_boundary_settling() -> None:
    assert _direction(0.65 - 0.15, 0.65) == "steady"
    assert _direction(0.65 - 0.16, 0.65) == "settling"


def test_ema_none_falls_back_to_steady() -> None:
    """When ema_levels is None, all desires default to steady (ema=0.5)."""
    text = blend_desires({"curiosity": 0.55})
    assert "A quiet wondering about something." in text
