"""Tests for the pre-dispatch XML-in-arguments validator."""

from __future__ import annotations

import pytest

from ego_mcp._server_param_validation import (
    ToolParameterFormatError,
    validate_tool_arguments,
)


class TestValidateToolArguments:
    def test_rejects_named_tag_wrapping_value(self) -> None:
        with pytest.raises(ToolParameterFormatError) as exc_info:
            validate_tool_arguments(
                "remember", {"content": "<content>hello</content>"}
            )
        message = str(exc_info.value)
        assert "[parameter_format_error]" in message
        assert "`remember`" in message
        assert "`content`" in message
        assert "Required: content" in message
        assert "<tag>" in message  # correction hint mentions tags
        assert "Example of a correct call" in message

    def test_rejects_self_closing_named_tag(self) -> None:
        with pytest.raises(ToolParameterFormatError):
            validate_tool_arguments("forget", {"memory_id": "<memory_id/>"})

    def test_rejects_named_tag_with_attributes(self) -> None:
        # XML wrappers occasionally arrive with attributes
        # (e.g. `<content type="text">...</content>`); the malformed
        # payload must still be flagged so the model can self-correct.
        with pytest.raises(ToolParameterFormatError) as exc_info:
            validate_tool_arguments(
                "remember",
                {"content": '<content type="text">hello</content>'},
            )
        message = str(exc_info.value)
        assert "`content`" in message

    def test_rejects_self_closing_named_tag_with_attributes(self) -> None:
        with pytest.raises(ToolParameterFormatError):
            validate_tool_arguments(
                "forget", {"memory_id": '<memory_id ref="abc"/>'}
            )

    def test_rejects_named_tag_with_whitespace_in_closing(self) -> None:
        # Some serializers emit `</content >` with trailing whitespace
        # before the closing `>`; treat it the same as `</content>`.
        with pytest.raises(ToolParameterFormatError):
            validate_tool_arguments(
                "remember", {"content": "<content>hi</content >"}
            )

    def test_sibling_tag_name_prefix_does_not_match(self) -> None:
        # `<contentx>` is a different tag name and must not collide with
        # `content`. The attribute branch requires a leading whitespace
        # separator, so this stays a non-match.
        validate_tool_arguments(
            "remember", {"content": "<contentx>noise</contentx>"}
        )

    def test_rejects_xml_wrapping_numeric_parameter(self) -> None:
        with pytest.raises(ToolParameterFormatError) as exc_info:
            validate_tool_arguments(
                "remember",
                {
                    "content": "plain content",
                    "importance": "<importance>3</importance>",
                },
            )
        message = str(exc_info.value)
        assert "`importance`" in message

    def test_reports_multiple_offenders(self) -> None:
        with pytest.raises(ToolParameterFormatError) as exc_info:
            validate_tool_arguments(
                "recall",
                {
                    "context": "<context>find me</context>",
                    "emotion_filter": "<emotion_filter>joy</emotion_filter>",
                },
            )
        message = str(exc_info.value)
        assert "`context`" in message
        assert "`emotion_filter`" in message

    def test_allows_xml_inside_nested_free_form_dict(self) -> None:
        # `update_self.value` / `update_relationship.value` are declared
        # as `{}` (any) in the tool schema — they carry arbitrary user
        # payload. Same-named tags inside a nested dict are legitimate
        # data, not wrapper misuse, and must not be rejected.
        validate_tool_arguments(
            "update_self",
            {"field": "notes", "value": {"note": "<note>remember this</note>"}},
        )
        validate_tool_arguments(
            "remember",
            {
                "content": "plain",
                "body_state": {
                    "time_phase": "<time_phase>morning</time_phase>"
                },
            },
        )

    def test_allows_xml_inside_array_items(self) -> None:
        # Array items are treated as user content; a string element that
        # happens to look like `<tags>...</tags>` is not a reliable
        # wrapper-misuse signal and must pass.
        validate_tool_arguments(
            "remember",
            {
                "content": "plain content",
                "tags": ["<tags>foo</tags>", "<tags>bar</tags>"],
            },
        )

    def test_plain_text_content_is_allowed(self) -> None:
        validate_tool_arguments(
            "remember", {"content": "普通の文章です", "emotion": "calm"}
        )

    def test_natural_angle_brackets_do_not_false_positive(self) -> None:
        # Prose with `<` characters must not trip the validator.
        validate_tool_arguments(
            "remember", {"content": "a < b < c and 3 > 2, but not <3"}
        )

    def test_allows_html_snippets_mentioned_in_content(self) -> None:
        # Content that legitimately mentions HTML/XML tags (but none
        # whose name is a `remember` parameter) must be accepted.
        validate_tool_arguments(
            "remember",
            {"content": "Use <div> and <span> for inline HTML structure."},
        )

    def test_allows_intentional_xml_snippet_when_tag_not_a_parameter(self) -> None:
        # Saving an XML snippet as a memory is legitimate when the tag
        # name doesn't collide with a tool parameter.
        validate_tool_arguments(
            "remember", {"content": "<note>important memo</note>"}
        )

    def test_allows_update_self_value_containing_html(self) -> None:
        # `update_self.value` accepts any type; an HTML-like string whose
        # tag names aren't parameter names must pass.
        validate_tool_arguments(
            "update_self",
            {"field": "bio", "value": "<user>Alice</user> says hi"},
        )

    def test_allows_sibling_parameter_tag_name_in_content(self) -> None:
        # `content` intentionally quoting another parameter name like
        # `emotion` must not be flagged. The scanner only matches a tag
        # against its own enclosing key.
        validate_tool_arguments(
            "remember", {"content": "<emotion>joy</emotion>"}
        )
        validate_tool_arguments(
            "recall", {"context": "look up <category>daily</category> notes"}
        )

    def test_valid_consider_them_passes(self) -> None:
        validate_tool_arguments("consider_them", {"person": "Alice"})

    def test_empty_args_passes(self) -> None:
        validate_tool_arguments("wake_up", {})
        validate_tool_arguments("wake_up", None)

    def test_unknown_tool_passes_through(self) -> None:
        # The dispatcher handles unknown names; validation must not block.
        validate_tool_arguments(
            "does_not_exist", {"anything": "<content>x</content>"}
        )

    def test_error_message_lists_required_and_optional(self) -> None:
        with pytest.raises(ToolParameterFormatError) as exc_info:
            validate_tool_arguments(
                "remember", {"content": "<content>x</content>"}
            )
        message = str(exc_info.value)
        assert "Required: content" in message
        # A few optional fields should appear in the listing
        for optional in ("emotion", "importance", "category"):
            assert optional in message

    def test_excerpt_is_truncated(self) -> None:
        long_value = "<content>" + ("x" * 500) + "</content>"
        with pytest.raises(ToolParameterFormatError) as exc_info:
            validate_tool_arguments("remember", {"content": long_value})
        message = str(exc_info.value)
        assert "..." in message
        # Excerpt shouldn't dump the entire payload
        assert message.count("x") < 200

    def test_configure_desires_enum_rendered_in_expected_shape(self) -> None:
        # When the schema has `enum`, the expected-shape section should
        # surface the allowed values as valid JSON string literals so an
        # LLM copying the sample produces a valid payload.
        with pytest.raises(ToolParameterFormatError) as exc_info:
            validate_tool_arguments(
                "configure_desires", {"action": "<action>check</action>"}
            )
        message = str(exc_info.value)
        assert '"check"' in message
        assert '"set_sentence"' in message
        # Double-quoted, not Python repr's single quotes.
        assert "'check'" not in message

    def test_enum_example_value_is_valid_json(self) -> None:
        # The sample "Example of a correct call" must actually parse as
        # JSON — otherwise an LLM mimicking it produces another malformed
        # request and loops.
        import json as _json
        import re as _re

        with pytest.raises(ToolParameterFormatError) as exc_info:
            validate_tool_arguments(
                "curate_notions", {"action": "<action>list</action>"}
            )
        message = str(exc_info.value)
        match = _re.search(r"Example of a correct call:\n(\s*\{.*\})", message)
        assert match is not None, message
        parsed = _json.loads(match.group(1).strip())
        assert parsed["action"] == "list"

    def test_oneof_type_description_lists_variants(self) -> None:
        # `remember.shared_with` uses `oneOf: [string, array<string>]`.
        # The description should derive that from the schema, not be a
        # hardcoded literal — so future schema edits stay accurate.
        with pytest.raises(ToolParameterFormatError) as exc_info:
            validate_tool_arguments(
                "remember",
                {
                    "content": "<content>x</content>",
                    "shared_with": "Master",
                },
            )
        message = str(exc_info.value)
        # The variants come from the schema, joined with " or ".
        assert "string or array of string" in message

    def test_offender_excerpt_uses_double_quotes_and_keeps_unicode(self) -> None:
        # The excerpt should be JSON-quoted (double quotes) for
        # consistency with the example block, and non-ASCII characters
        # should remain readable rather than be backslash-escaped.
        with pytest.raises(ToolParameterFormatError) as exc_info:
            validate_tool_arguments(
                "remember", {"content": "<content>今日は雨</content>"}
            )
        message = str(exc_info.value)
        assert '"<content>今日は雨</content>"' in message
        assert "\\u" not in message
