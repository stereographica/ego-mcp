"""Tests for cognitive scaffold templates."""

from __future__ import annotations

import re

import pytest

from ego_mcp.scaffolds import (
    SCAFFOLD_AM_I_GENUINE,
    SCAFFOLD_CONSIDER_THEM,
    SCAFFOLD_EMOTION_TREND,
    SCAFFOLD_FEEL_DESIRES,
    SCAFFOLD_INTROSPECT,
    SCAFFOLD_WAKE_UP,
    compose_response,
    render,
    render_with_data,
)

ALL_SCAFFOLDS = [
    SCAFFOLD_WAKE_UP,
    SCAFFOLD_FEEL_DESIRES,
    SCAFFOLD_INTROSPECT,
    SCAFFOLD_CONSIDER_THEM,
    SCAFFOLD_AM_I_GENUINE,
    SCAFFOLD_EMOTION_TREND,
]


class TestScaffoldConstants:
    """Each constant is non-empty."""

    def test_all_non_empty(self) -> None:
        for scaffold in ALL_SCAFFOLDS:
            assert len(scaffold.strip()) > 0, f"Empty scaffold: {scaffold!r}"

    def test_no_japanese(self) -> None:
        """All scaffolds must be English only (no CJK characters)."""
        cjk_pattern = re.compile(r"[\u3000-\u9fff\uf900-\ufaff]")
        for scaffold in ALL_SCAFFOLDS:
            assert not cjk_pattern.search(scaffold), (
                f"Japanese found in scaffold: {scaffold!r}"
            )

    def test_wake_up_mentions_private_memory_option(self) -> None:
        assert "remember(private=true)" in SCAFFOLD_WAKE_UP

    def test_introspect_mentions_emotion_trend(self) -> None:
        assert "Use emotion_trend" in SCAFFOLD_INTROSPECT

    def test_introspect_mentions_genuinely_new_insight_before_remember(self) -> None:
        assert "genuinely new insight" in SCAFFOLD_INTROSPECT

    def test_feel_desires_uses_awareness_prompt_for_satisfy_desire(self) -> None:
        assert (
            "Does any urge feel quieter than before? If something feels settled, "
            "acknowledge it with satisfy_desire."
        ) in SCAFFOLD_FEEL_DESIRES
        assert "After acting on a desire, use satisfy_desire." not in SCAFFOLD_FEEL_DESIRES


class TestRender:
    """render() replaces {companion_name}."""

    def test_replace_companion_name(self) -> None:
        result = render(SCAFFOLD_FEEL_DESIRES, "Senpai")
        assert "Senpai" in result
        assert "{companion_name}" not in result

    def test_no_placeholder_unchanged(self) -> None:
        result = render(SCAFFOLD_WAKE_UP, "Master")
        assert result == SCAFFOLD_WAKE_UP  # no placeholder in wake_up

    def test_multiple_placeholders(self) -> None:
        template = "{companion_name} said hi to {companion_name}"
        result = render(template, "Boss")
        assert result == "Boss said hi to Boss"


class TestDataScaffoldFormat:
    """Scaffolds can be returned in `data + scaffold` format."""

    def test_compose_response_shape(self) -> None:
        result = compose_response("data block", "scaffold block")
        assert result == "data block\n\n---\nscaffold block"

    @pytest.mark.parametrize(
        "template",
        [
            SCAFFOLD_WAKE_UP,
            SCAFFOLD_FEEL_DESIRES,
            SCAFFOLD_INTROSPECT,
            SCAFFOLD_CONSIDER_THEM,
            SCAFFOLD_AM_I_GENUINE,
            SCAFFOLD_EMOTION_TREND,
        ],
    )
    def test_each_template_supports_data_scaffold_format(self, template: str) -> None:
        data = "runtime-data"
        result = render_with_data(data, template, "Master")
        assert result.startswith("runtime-data\n\n---\n")
        assert "{companion_name}" not in result
        assert result.endswith(render(template, "Master"))
