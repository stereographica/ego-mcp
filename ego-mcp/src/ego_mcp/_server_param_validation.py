"""Pre-dispatch validation for tool arguments.

LLMs occasionally call MCP tools with parameters wrapped in XML tags
(e.g. ``{"content": "<content>hello</content>"}``) instead of plain JSON
values. This module detects that specific failure mode and produces a
structured error message the model can act on in its next turn.

The validator is intentionally narrow: it only rejects clearly XML-shaped
strings. General JSON Schema type checking is out of scope.
"""

from __future__ import annotations

import json
import re
from typing import Any

from mcp.types import Tool

from ego_mcp._server_tools import BACKEND_TOOLS, SURFACE_TOOLS

_EXCERPT_LIMIT = 120
_ERROR_MARKER = "[parameter_format_error]"


class ToolParameterFormatError(Exception):
    """Raised when tool arguments are formatted in an unsupported shape.

    The string form of the exception is the full LLM-facing message,
    intended to be returned as tool output so the model can self-correct.
    """


def _build_tool_schema_index() -> dict[str, Tool]:
    index: dict[str, Tool] = {}
    for tool in (*SURFACE_TOOLS, *BACKEND_TOOLS):
        index[tool.name] = tool
    return index


_TOOL_INDEX: dict[str, Tool] = _build_tool_schema_index()


def _matches_named_tag(value: str, tag: str) -> bool:
    """Detect ``<tag>...</tag>`` or ``<tag/>`` for an exact tag name.

    Allows optional attributes on the opening tag so wrappers like
    ``<content type="text">hello</content>`` are still flagged. The
    attribute span is anchored to a leading whitespace character so
    sibling tag names (``<contentx>``) don't accidentally match.
    """
    escaped = re.escape(tag)
    pattern = (
        rf"<{escaped}"
        rf"(?:\s[^>]*?)?"  # optional attributes (must start with whitespace)
        rf"\s*"
        rf"(?:/>|>.*?</{escaped}\s*>)"
    )
    return re.search(pattern, value, flags=re.DOTALL) is not None


def _excerpt(value: str) -> str:
    collapsed = " ".join(value.split())
    if len(collapsed) <= _EXCERPT_LIMIT:
        return collapsed
    return collapsed[:_EXCERPT_LIMIT] + "..."


def _describe_type(schema: dict[str, Any]) -> str:
    if "enum" in schema and isinstance(schema["enum"], list):
        return "one of " + " | ".join(json.dumps(v) for v in schema["enum"])
    if "oneOf" in schema and isinstance(schema["oneOf"], list):
        # De-duplicate while preserving order so e.g.
        # `oneOf: [string, array<string>]` reads cleanly.
        seen: set[str] = set()
        unique: list[str] = []
        for variant in schema["oneOf"]:
            described = _describe_type(variant or {})
            if described not in seen:
                seen.add(described)
                unique.append(described)
        return " or ".join(unique) if unique else "any"
    t = schema.get("type")
    if t == "array":
        item_t = schema.get("items", {}).get("type", "any")
        return f"array of {item_t}"
    if isinstance(t, str):
        return t
    return "any"


def _render_expected_shape(tool: Tool) -> str:
    input_schema = tool.inputSchema or {}
    properties: dict[str, Any] = input_schema.get("properties", {}) or {}
    required = set(input_schema.get("required", []) or [])

    if not properties:
        return "  {}   # no parameters"

    lines = ["  {"]
    items = list(properties.items())
    for idx, (name, prop_schema) in enumerate(items):
        type_desc = _describe_type(prop_schema or {})
        qualifier = "required" if name in required else "optional"
        comma = "," if idx < len(items) - 1 else ""
        lines.append(f'    "{name}": <{type_desc}, {qualifier}>{comma}')
    lines.append("  }")
    return "\n".join(lines)


def _partition_params(tool: Tool) -> tuple[list[str], list[str]]:
    input_schema = tool.inputSchema or {}
    properties: dict[str, Any] = input_schema.get("properties", {}) or {}
    required = set(input_schema.get("required", []) or [])
    required_list = [n for n in properties if n in required]
    optional_list = [n for n in properties if n not in required]
    return required_list, optional_list


def _example_call(tool: Tool) -> str:
    input_schema = tool.inputSchema or {}
    properties: dict[str, Any] = input_schema.get("properties", {}) or {}
    required = input_schema.get("required", []) or []

    fields: list[str] = []
    for name in required:
        prop = properties.get(name, {}) or {}
        fields.append(f'"{name}": {_example_value(prop)}')

    if not fields and properties:
        first_name, first_prop = next(iter(properties.items()))
        fields.append(f'"{first_name}": {_example_value(first_prop)}')

    if not fields:
        return "  {}"
    return "  {" + ", ".join(fields) + "}"


def _example_value(prop_schema: dict[str, Any]) -> str:
    if "enum" in prop_schema and isinstance(prop_schema["enum"], list) and prop_schema["enum"]:
        return json.dumps(prop_schema["enum"][0])
    t = prop_schema.get("type")
    if t == "string":
        return '"..."'
    if t == "integer":
        return "1"
    if t == "number":
        return "0.5"
    if t == "boolean":
        return "false"
    if t == "array":
        item_t = prop_schema.get("items", {}).get("type")
        if item_t == "string":
            return '["..."]'
        return "[]"
    if t == "object":
        return "{}"
    return '"..."'


def _find_offenders(tool_name: str, args: dict[str, Any]) -> list[tuple[str, str]]:
    """Return a list of ``(param_name, excerpt)`` tuples for XML-shaped values.

    Detection is intentionally limited to **top-level string arguments**:
    a value is flagged only when it's a string at the top level of
    ``args`` and contains ``<key>...</key>`` (or ``<key/>``) for its own
    key. Nested dicts and array items are not recursed into — free-form
    parameters such as ``update_self.value`` or ``remember.body_state``
    can carry arbitrary user payloads where same-named tags are
    legitimate data, and there is no reliable way to tell apart "the LLM
    wrapped a parameter in XML" from "the user really wants to store
    this XML-looking string" without a strict schema for the nested
    shape. The top-level check covers the dominant LLM failure mode.
    """
    if _TOOL_INDEX.get(tool_name) is None:
        return []

    offenders: list[tuple[str, str]] = []
    for key, value in args.items():
        if isinstance(value, str) and _matches_named_tag(value, key):
            offenders.append((key, _excerpt(value)))
    return offenders


def _format_correction_message(
    tool_name: str,
    offenders: list[tuple[str, str]],
    tool: Tool,
) -> str:
    offender_lines: list[str] = []
    for name, excerpt in offenders:
        # `json.dumps` keeps the message in the same JSON-style quoting
        # convention as the example block, and preserves non-ASCII
        # characters readably (`ensure_ascii=False`).
        quoted = json.dumps(excerpt, ensure_ascii=False)
        offender_lines.append(f"  - `{name}`: {quoted}")

    required_list, optional_list = _partition_params(tool)
    required_str = ", ".join(required_list) if required_list else "(none)"
    optional_str = ", ".join(optional_list) if optional_list else "(none)"

    return "\n".join(
        [
            f"{_ERROR_MARKER} Tool `{tool_name}` expects JSON arguments, not XML.",
            "",
            "Offending parameter(s) (value contains XML-style tags):",
            *offender_lines,
            "",
            "Do NOT wrap values in XML tags. Pass a JSON object whose keys are",
            "the parameter names and whose values are the raw values.",
            "",
            f"Expected JSON shape for `{tool_name}`:",
            _render_expected_shape(tool),
            "",
            f"Required: {required_str}",
            f"Optional: {optional_str}",
            "",
            "Example of a correct call:",
            _example_call(tool),
            "",
            "Please retry this tool call with plain JSON arguments "
            "(no `<tag>` wrappers).",
        ]
    )


def validate_tool_arguments(tool_name: str, args: dict[str, Any] | None) -> None:
    """Raise :class:`ToolParameterFormatError` when args look XML-shaped.

    Unknown tool names pass through silently; ``_dispatch`` already has a
    fallback path for them.
    """
    if not args:
        return
    tool = _TOOL_INDEX.get(tool_name)
    if tool is None:
        return

    offenders = _find_offenders(tool_name, args)
    if not offenders:
        return

    raise ToolParameterFormatError(
        _format_correction_message(tool_name, offenders, tool)
    )
