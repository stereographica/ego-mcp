"""Backend handler for configure_desires tool."""

from __future__ import annotations

import json
from typing import Any

from ego_mcp.desire_catalog import (
    DesireCatalog,
    load_desire_catalog,
)


def _handle_configure_desires(
    catalog_path: str,
    args: dict[str, Any],
) -> str:
    """View or configure desire settings."""
    from pathlib import Path

    path = Path(catalog_path)
    catalog = load_desire_catalog(path)

    action = str(args.get("action", "")).strip()

    if action == "show":
        desire_id = args.get("desire_id")
        if desire_id:
            return _show_one(catalog, str(desire_id))
        return _show_all(catalog)

    if action == "check":
        return _check_incomplete(catalog)

    if action == "set_sentence":
        desire_id = str(args.get("desire_id", "")).strip()
        direction = str(args.get("direction", "")).strip()
        sentence = str(args.get("sentence", "")).strip()
        if not desire_id or not direction or not sentence:
            return "set_sentence requires desire_id, direction, and sentence."
        return _set_sentence(path, catalog, desire_id, direction, sentence)

    if action == "set_signals":
        desire_id = str(args.get("desire_id", "")).strip()
        signals = args.get("signals")
        if not desire_id or not isinstance(signals, list):
            return "set_signals requires desire_id and signals (list of strings)."
        return _set_signals(path, catalog, desire_id, [str(s) for s in signals])

    return f"Unknown action: {action}. Use check, show, set_sentence, or set_signals."


def _show_one(catalog: DesireCatalog, desire_id: str) -> str:
    desire = catalog.fixed_desires.get(desire_id)
    if desire is None:
        known = ", ".join(sorted(catalog.fixed_desires.keys()))
        return f"Unknown desire: {desire_id}. Known: {known}"
    lines = [
        f"Desire: {desire_id}",
        f"  satisfaction_hours: {desire.satisfaction_hours}",
        f"  maslow_level: {desire.maslow_level}",
        f"  sentence.rising: {desire.sentence.rising!r}",
        f"  sentence.steady: {desire.sentence.steady!r}",
        f"  sentence.settling: {desire.sentence.settling!r}",
    ]
    if desire.satisfaction_signals:
        lines.append(f"  satisfaction_signals: {desire.satisfaction_signals}")
    else:
        lines.append("  satisfaction_signals: (not configured)")
    if desire.implicit_satisfaction:
        lines.append(f"  implicit_satisfaction: {desire.implicit_satisfaction}")
    return "\n".join(lines)


def _show_all(catalog: DesireCatalog) -> str:
    lines = [f"Desire catalog (version {catalog.version}):"]
    for desire_id, desire in sorted(catalog.fixed_desires.items()):
        incomplete = []
        if not desire.sentence.settling:
            incomplete.append("settling")
        if not desire.satisfaction_signals:
            incomplete.append("signals")
        status = " [incomplete: " + ", ".join(incomplete) + "]" if incomplete else ""
        lines.append(f"  {desire_id}: maslow={desire.maslow_level}{status}")
    return "\n".join(lines)


def _check_incomplete(catalog: DesireCatalog) -> str:
    issues: list[str] = []
    for desire_id, desire in sorted(catalog.fixed_desires.items()):
        if not desire.sentence.settling:
            issues.append(f"  {desire_id}: missing settling sentence")
        if not desire.satisfaction_signals:
            issues.append(f"  {desire_id}: missing satisfaction_signals")
    if not issues:
        return "All desires are fully configured."
    return "Incomplete configuration:\n" + "\n".join(issues)


def _set_sentence(
    path: "Any",
    catalog: DesireCatalog,
    desire_id: str,
    direction: str,
    sentence: str,
) -> str:
    from pathlib import Path

    desire = catalog.fixed_desires.get(desire_id)
    if desire is None:
        return f"Unknown desire: {desire_id}"
    if direction not in ("rising", "steady", "settling"):
        return f"Invalid direction: {direction}. Use rising, steady, or settling."

    payload = catalog.model_dump(mode="json", exclude_none=True)
    payload["fixed_desires"][desire_id]["sentence"][direction] = sentence
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return f"Updated {desire_id}.sentence.{direction}"


def _set_signals(
    path: "Any",
    catalog: DesireCatalog,
    desire_id: str,
    signals: list[str],
) -> str:
    from pathlib import Path

    desire = catalog.fixed_desires.get(desire_id)
    if desire is None:
        return f"Unknown desire: {desire_id}"

    payload = catalog.model_dump(mode="json", exclude_none=True)
    payload["fixed_desires"][desire_id]["satisfaction_signals"] = signals
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return f"Updated {desire_id}.satisfaction_signals ({len(signals)} signal(s))"
