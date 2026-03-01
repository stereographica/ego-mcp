"""Unit tests for remember surface emotion defaults."""

from __future__ import annotations

import pytest

from ego_mcp._server_surface_memory import EMOTION_DEFAULTS
from ego_mcp.types import Emotion


def test_emotion_defaults_cover_all_enum_members() -> None:
    expected = {emotion.value for emotion in Emotion}
    missing = expected - set(EMOTION_DEFAULTS)
    assert not missing


def test_emotion_defaults_include_contentment_and_melancholy_values() -> None:
    assert EMOTION_DEFAULTS["contentment"] == pytest.approx((0.5, 0.5, 0.2))
    assert EMOTION_DEFAULTS["melancholy"] == pytest.approx((0.5, -0.4, 0.2))
