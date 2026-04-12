"""Tests for cognitive scaffold templates."""

from __future__ import annotations

import re

import pytest

from ego_mcp.scaffolds import (
    SCAFFOLD_ATTUNE,
    SCAFFOLD_CONSIDER_THEM,
    SCAFFOLD_CONSOLIDATE,
    SCAFFOLD_CURATE_NOTIONS,
    SCAFFOLD_INTROSPECT,
    SCAFFOLD_PAUSE,
    SCAFFOLD_REMEMBER,
    SCAFFOLD_WAKE_UP,
    compose_response,
    render,
    render_with_data,
)

# Surface tool names that must never appear in scaffolds.
_SURFACE_TOOL_NAMES = {
    "wake_up",
    "attune",
    "introspect",
    "pause",
    "consider_them",
    "curate_notions",
    "remember",
    "recall",
    "consolidate",
}

# Backend tool names that *may* appear in scaffolds.
_BACKEND_TOOL_NAMES = {
    "create_episode",
    "get_episode",
    "update_self",
    "update_relationship",
    "link_memories",
    "configure_desires",
}

# Imperative verbs that should not start scaffold sentences.
_IMPERATIVE_STARTS = re.compile(
    r"(?:^|\n)\s*(?:Try|Consider|Use|Run|Start|Save|Check|Remember|Reflect)\b",
    re.IGNORECASE,
)

ALL_SURFACE_SCAFFOLDS = [
    SCAFFOLD_WAKE_UP,
    SCAFFOLD_ATTUNE,
    SCAFFOLD_INTROSPECT,
    SCAFFOLD_REMEMBER,
    SCAFFOLD_CONSIDER_THEM,
    SCAFFOLD_PAUSE,
    SCAFFOLD_CURATE_NOTIONS,
    SCAFFOLD_CONSOLIDATE,
]


class TestScaffoldDesignPrinciples:
    """§12.1 design principles: no imperatives, no surface tool names, first-person."""

    def test_all_non_empty(self) -> None:
        for scaffold in ALL_SURFACE_SCAFFOLDS:
            assert len(scaffold.strip()) > 0

    def test_no_japanese(self) -> None:
        cjk_pattern = re.compile(r"[\u3000-\u9fff\uf900-\ufaff]")
        for scaffold in ALL_SURFACE_SCAFFOLDS:
            assert not cjk_pattern.search(scaffold), (
                f"Japanese found in scaffold: {scaffold!r}"
            )

    def test_no_imperative_verbs(self) -> None:
        for scaffold in ALL_SURFACE_SCAFFOLDS:
            match = _IMPERATIVE_STARTS.search(scaffold)
            assert match is None, (
                f"Imperative verb found: {match.group()!r} in {scaffold!r}"
            )

    def test_no_surface_tool_names(self) -> None:
        for scaffold in ALL_SURFACE_SCAFFOLDS:
            for name in _SURFACE_TOOL_NAMES:
                assert name not in scaffold.lower(), (
                    f"Surface tool name '{name}' found in scaffold: {scaffold!r}"
                )

    def test_backend_tool_names_allowed_in_introspect(self) -> None:
        assert "create_episode" in SCAFFOLD_INTROSPECT
        assert "get_episode" in SCAFFOLD_INTROSPECT

    def test_backend_tool_names_allowed_in_remember(self) -> None:
        assert "create_episode" in SCAFFOLD_REMEMBER

    def test_backend_tool_names_allowed_in_consolidate(self) -> None:
        assert "create_episode" in SCAFFOLD_CONSOLIDATE


class TestScaffoldContent:
    """Verify key content of each scaffold per §12.2."""

    def test_wake_up_reflective(self) -> None:
        assert "stayed with me" in SCAFFOLD_WAKE_UP.lower()

    def test_attune_self_inquiry(self) -> None:
        assert "actually feeling" in SCAFFOLD_ATTUNE.lower()

    def test_introspect_accumulation(self) -> None:
        assert "accumulating" in SCAFFOLD_INTROSPECT.lower()

    def test_pause_self_check(self) -> None:
        assert "template" in SCAFFOLD_PAUSE.lower()
        assert "mine" in SCAFFOLD_PAUSE.lower()

    def test_consider_them_empathy(self) -> None:
        assert "what would I need" in SCAFFOLD_CONSIDER_THEM

    def test_remember_connection(self) -> None:
        assert "connect" in SCAFFOLD_REMEMBER.lower()

    def test_curate_notions_ring_true(self) -> None:
        assert "ring true" in SCAFFOLD_CURATE_NOTIONS.lower()

    def test_consolidate_story(self) -> None:
        assert "story" in SCAFFOLD_CONSOLIDATE.lower()


class TestRender:
    """render() replaces {companion_name}."""

    def test_replace_companion_name(self) -> None:
        result = render(SCAFFOLD_ATTUNE, "Senpai")
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
        ALL_SURFACE_SCAFFOLDS,
    )
    def test_each_template_supports_data_scaffold_format(self, template: str) -> None:
        data = "runtime-data"
        result = render_with_data(data, template, "Master")
        assert result.startswith("runtime-data\n\n---\n")
        assert "{companion_name}" not in result
        assert result.endswith(render(template, "Master"))
