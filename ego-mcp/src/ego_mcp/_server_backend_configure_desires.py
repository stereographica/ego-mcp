"""Backend handler for configure_desires tool."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ego_mcp.desire_catalog import (
    DesireConfigurationError,
    ensure_default_desire_catalog_file,
    load_desire_catalog,
)


def _handle_configure_desires(
    catalog_path: str,
    args: dict[str, Any],
) -> str:
    """View or configure desire settings."""
    path = Path(catalog_path)
    payload = _load_catalog_payload(path)
    action = str(args.get("action", "")).strip()
    catalog_error: str | None = None
    try:
        load_desire_catalog(path)
    except DesireConfigurationError as exc:
        catalog_error = str(exc)

    if action == "show":
        desire_id = args.get("desire_id")
        if desire_id:
            return _show_one(payload, str(desire_id), catalog_error=catalog_error)
        return _show_all(payload, catalog_error=catalog_error)

    if action == "check":
        return _check_incomplete(payload, catalog_error=catalog_error)

    if action == "set_sentence":
        desire_id = str(args.get("desire_id", "")).strip()
        direction = str(args.get("direction", "")).strip()
        sentence = str(args.get("sentence", "")).strip()
        if not desire_id or not direction or not sentence:
            return "set_sentence requires desire_id, direction, and sentence."
        return _set_sentence(path, payload, desire_id, direction, sentence)

    if action == "set_signals":
        desire_id = str(args.get("desire_id", "")).strip()
        signals = args.get("signals")
        if not desire_id or not isinstance(signals, list):
            return "set_signals requires desire_id and signals (list of strings)."
        return _set_signals(path, payload, desire_id, [str(s) for s in signals])

    return f"Unknown action: {action}. Use check, show, set_sentence, or set_signals."


def _load_catalog_payload(path: Path) -> dict[str, Any]:
    ensure_default_desire_catalog_file(path)
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise DesireConfigurationError(f"Invalid desire catalog at {path}: root must be an object")
    return payload


def _fixed_desire_payloads(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    fixed = payload.get("fixed_desires", {})
    if not isinstance(fixed, dict):
        return {}
    return {
        desire_id: raw
        for desire_id, raw in fixed.items()
        if isinstance(desire_id, str) and isinstance(raw, dict)
    }


def _show_one(
    payload: dict[str, Any],
    desire_id: str,
    *,
    catalog_error: str | None = None,
) -> str:
    desires = _fixed_desire_payloads(payload)
    desire = desires.get(desire_id)
    if desire is None:
        known = ", ".join(sorted(desires.keys()))
        return f"Unknown desire: {desire_id}. Known: {known}"
    sentence = desire.get("sentence", {})
    if not isinstance(sentence, dict):
        sentence = {}
    lines = [
        f"Desire: {desire_id}",
        f"  satisfaction_hours: {desire.get('satisfaction_hours', '(missing)')}",
        f"  maslow_level: {desire.get('maslow_level', '(missing)')}",
        f"  sentence.rising: {sentence.get('rising', '')!r}",
        f"  sentence.steady: {sentence.get('steady', '')!r}",
        f"  sentence.settling: {sentence.get('settling', '')!r}",
    ]
    signals = desire.get("satisfaction_signals", [])
    if isinstance(signals, list) and signals:
        lines.append(f"  satisfaction_signals: {signals}")
    else:
        lines.append("  satisfaction_signals: (not configured)")
    implicit = desire.get("implicit_satisfaction", {})
    if isinstance(implicit, dict) and implicit:
        lines.append(f"  implicit_satisfaction: {implicit}")
    if catalog_error is not None:
        lines.append(f"  validation: {catalog_error}")
    return "\n".join(lines)


def _show_all(payload: dict[str, Any], *, catalog_error: str | None = None) -> str:
    lines = [f"Desire catalog (version {payload.get('version', '(missing)')}):"]
    for desire_id, desire in sorted(_fixed_desire_payloads(payload).items()):
        incomplete = []
        sentence = desire.get("sentence", {})
        if not isinstance(sentence, dict) or not sentence.get("settling"):
            incomplete.append("settling")
        if not desire.get("satisfaction_signals"):
            incomplete.append("signals")
        status = " [incomplete: " + ", ".join(incomplete) + "]" if incomplete else ""
        lines.append(f"  {desire_id}: maslow={desire.get('maslow_level', '(missing)')}{status}")
    if catalog_error is not None:
        lines.append(f"Validation issues: {catalog_error}")
    return "\n".join(lines)


def _check_incomplete(payload: dict[str, Any], *, catalog_error: str | None = None) -> str:
    issues: list[str] = []
    for desire_id, desire in sorted(_fixed_desire_payloads(payload).items()):
        sentence = desire.get("sentence", {})
        if not isinstance(sentence, dict) or not sentence.get("settling"):
            issues.append(f"  {desire_id}: missing settling sentence")
        if not desire.get("satisfaction_signals"):
            issues.append(f"  {desire_id}: missing satisfaction_signals")
    if catalog_error is not None:
        issues.insert(0, f"  validation: {catalog_error}")
    if not issues:
        return "All desires are fully configured."
    return "Incomplete configuration:\n" + "\n".join(issues)


def _set_sentence(
    path: Path,
    payload: dict[str, Any],
    desire_id: str,
    direction: str,
    sentence: str,
) -> str:
    desires = _fixed_desire_payloads(payload)
    if desire_id not in desires:
        return f"Unknown desire: {desire_id}"
    if direction not in ("rising", "steady", "settling"):
        return f"Invalid direction: {direction}. Use rising, steady, or settling."

    desire = desires[desire_id]
    desire.setdefault("sentence", {})
    if not isinstance(desire["sentence"], dict):
        desire["sentence"] = {}
    desire["sentence"][direction] = sentence
    _write_payload(path, payload)
    return _write_result(path, f"Updated {desire_id}.sentence.{direction}")


def _set_signals(
    path: Path,
    payload: dict[str, Any],
    desire_id: str,
    signals: list[str],
) -> str:
    desires = _fixed_desire_payloads(payload)
    if desire_id not in desires:
        return f"Unknown desire: {desire_id}"

    desires[desire_id]["satisfaction_signals"] = signals
    _write_payload(path, payload)
    return _write_result(
        path,
        f"Updated {desire_id}.satisfaction_signals ({len(signals)} signal(s))",
    )


def _write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_result(path: Path, success_message: str) -> str:
    try:
        load_desire_catalog(path)
    except DesireConfigurationError as exc:
        return f"{success_message}\nCatalog still has validation issues: {exc}"
    return success_message
