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
    """Detect ``<tag>...</tag>`` or ``<tag/>`` for an exact tag name."""
    pattern = rf"<{re.escape(tag)}\s*(?:/>|>.*?</{re.escape(tag)}>)"
    return re.search(pattern, value, flags=re.DOTALL) is not None


def _excerpt(value: str) -> str:
    collapsed = " ".join(value.split())
    if len(collapsed) <= _EXCERPT_LIMIT:
        return collapsed
    return collapsed[:_EXCERPT_LIMIT] + "..."


def _describe_type(schema: dict[str, Any]) -> str:
    if "enum" in schema and isinstance(schema["enum"], list):
        return "one of " + " | ".join(json.dumps(v) for v in schema["enum"])
    if "oneOf" in schema:
        return "string or array of strings"
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

    Detection is deliberately narrow: a value is flagged only when it
    contains an XML tag whose name is **also a parameter name of this
    tool, or a key of the enclosing dict**. That combination is the
    specific wrapper misuse we want to catch (e.g. ``content`` →
    ``"<content>...</content>"``). Free-form text that merely *mentions*
    HTML/XML (``"Use <div> and <span>"``) or stores an intentional XML
    snippet (``"<note>memo</note>"``) is left alone.
    """
    tool = _TOOL_INDEX.get(tool_name)
    known_params: set[str] = set()
    if tool is not None:
        known_params = set((tool.inputSchema or {}).get("properties", {}).keys())

    offenders: list[tuple[str, str]] = []

    def _scan(key: str, value: Any, tag_candidates: set[str]) -> None:
        if isinstance(value, str):
            for tag in tag_candidates:
                if _matches_named_tag(value, tag):
                    offenders.append((key, _excerpt(value)))
                    return
        elif isinstance(value, dict):
            # Allow the nested dict's own keys to act as tag candidates:
            # ``body_state.time_phase = "<time_phase>..."`` is a clear
            # misuse even though ``time_phase`` isn't a top-level param.
            for sub_key, sub_value in value.items():
                _scan(
                    f"{key}.{sub_key}",
                    sub_value,
                    tag_candidates | {sub_key},
                )
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                _scan(f"{key}[{idx}]", item, tag_candidates)

    for key, value in args.items():
        _scan(key, value, known_params)

    return offenders


def _format_correction_message(
    tool_name: str,
    offenders: list[tuple[str, str]],
    tool: Tool,
) -> str:
    offender_lines: list[str] = []
    for name, excerpt in offenders:
        offender_lines.append(f"  - `{name}`: {excerpt!r}")

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
