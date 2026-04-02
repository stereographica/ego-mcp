from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

from ego_dashboard.constants import DESIRE_METRIC_KEYS

LEGACY_FIXED_DESIRE_IDS: tuple[str, ...] = DESIRE_METRIC_KEYS
_RESERVED_NUMERIC_METRIC_KEYS = frozenset(
    {
        "intensity",
        "emotion_intensity",
        "valence",
        "arousal",
        "impulse_boost_amount",
        "tool_output_chars",
    }
)


@dataclass(frozen=True)
class DesireCatalogItem:
    id: str
    display_name: str
    satisfaction_hours: float
    maslow_level: int


@dataclass(frozen=True)
class DesireCatalog:
    version: int | None
    fixed_desires: tuple[DesireCatalogItem, ...]
    status: Literal["ok", "missing", "invalid", "unconfigured"] = "ok"
    errors: tuple[str, ...] = ()
    source_path: str | None = None
    implicit_rules: tuple[dict[str, Any], ...] = ()
    emergent: dict[str, Any] = field(default_factory=dict)

    @property
    def fixed_ids(self) -> set[str]:
        return {item.id for item in self.fixed_desires}

    def is_visible_desire_metric(self, key: str) -> bool:
        if key in _RESERVED_NUMERIC_METRIC_KEYS:
            return False
        if key in self.fixed_ids:
            return True
        if key in LEGACY_FIXED_DESIRE_IDS:
            return False
        return True

    def split_desire_metrics(
        self,
        metrics: dict[str, float],
    ) -> tuple[dict[str, float], dict[str, float]]:
        fixed: dict[str, float] = {}
        emergent: dict[str, float] = {}
        for key, value in metrics.items():
            if not self.is_visible_desire_metric(key):
                continue
            if key in self.fixed_ids:
                fixed[key] = value
            else:
                emergent[key] = value
        return fixed, emergent

    def to_response(self) -> dict[str, object]:
        return {
            "version": self.version,
            "status": self.status,
            "errors": list(self.errors),
            "source_path": self.source_path,
            "fixed_desires": [asdict(item) for item in self.fixed_desires],
            "implicit_rules": list(self.implicit_rules),
            "emergent": self.emergent,
        }


def default_desire_catalog() -> DesireCatalog:
    return DesireCatalog(
        version=1,
        fixed_desires=tuple(
            DesireCatalogItem(
                id=desire_id,
                display_name=desire_id.replace("_", " "),
                satisfaction_hours=24.0,
                maslow_level=1,
            )
            for desire_id in LEGACY_FIXED_DESIRE_IDS
        ),
        status="unconfigured",
    )


def _fallback_catalog(
    *,
    status: Literal["missing", "invalid"],
    errors: tuple[str, ...],
    source_path: str | None,
    version: int | None = None,
) -> DesireCatalog:
    default_catalog = default_desire_catalog()
    return DesireCatalog(
        version=version,
        fixed_desires=default_catalog.fixed_desires,
        status=status,
        errors=errors,
        source_path=source_path,
        implicit_rules=default_catalog.implicit_rules,
        emergent=default_catalog.emergent,
    )


def load_desire_catalog(data_dir: str | None) -> DesireCatalog:
    if not data_dir:
        return default_desire_catalog()

    path = Path(data_dir) / "settings" / "desires.json"
    if not path.exists():
        return _fallback_catalog(
            status="missing",
            errors=(f"desire catalog not found: {path}",),
            source_path=str(path),
        )

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _fallback_catalog(
            status="invalid",
            errors=(f"failed to read desire catalog: {exc}",),
            source_path=str(path),
        )

    parsed = _parse_desire_catalog_payload(payload, source_path=str(path))
    return parsed


def _parse_desire_catalog_payload(payload: object, *, source_path: str) -> DesireCatalog:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return _fallback_catalog(
            status="invalid",
            errors=("desire catalog root must be an object",),
            source_path=source_path,
        )

    version = payload.get("version")
    if not isinstance(version, int):
        errors.append("version must be an integer")

    raw_fixed_desires = payload.get("fixed_desires")
    if not isinstance(raw_fixed_desires, dict):
        errors.append("fixed_desires must be an object")
        raw_fixed_desires = {}

    raw_implicit_rules = payload.get("implicit_rules", [])
    if not isinstance(raw_implicit_rules, list):
        errors.append("implicit_rules must be an array")
        raw_implicit_rules = []

    raw_emergent = payload.get("emergent", {})
    if not isinstance(raw_emergent, dict):
        errors.append("emergent must be an object")
        raw_emergent = {}

    fixed_desires: list[DesireCatalogItem] = []
    for desire_id, raw in raw_fixed_desires.items():
        item_errors: list[str] = []
        if not isinstance(desire_id, str) or not desire_id:
            item_errors.append("fixed_desires keys must be non-empty strings")
            continue
        if not isinstance(raw, dict):
            item_errors.append(f"fixed_desires.{desire_id} must be an object")
            continue
        satisfaction_hours = raw.get("satisfaction_hours")
        maslow_level = raw.get("maslow_level")
        sentence = raw.get("sentence")
        implicit_satisfaction = raw.get("implicit_satisfaction")
        display_name = raw.get("display_name", desire_id.replace("_", " "))

        if not isinstance(display_name, str) or not display_name:
            item_errors.append(f"fixed_desires.{desire_id}.display_name must be a non-empty string")
        if not isinstance(satisfaction_hours, (int, float)) or isinstance(satisfaction_hours, bool):
            item_errors.append(f"fixed_desires.{desire_id}.satisfaction_hours must be numeric")
        if not isinstance(maslow_level, int) or isinstance(maslow_level, bool):
            item_errors.append(f"fixed_desires.{desire_id}.maslow_level must be an integer")
        if not isinstance(sentence, dict):
            item_errors.append(f"fixed_desires.{desire_id}.sentence must be an object")
        else:
            medium = sentence.get("medium")
            high = sentence.get("high")
            if not isinstance(medium, str) or not medium:
                item_errors.append(f"fixed_desires.{desire_id}.sentence.medium must be a string")
            if not isinstance(high, str) or not high:
                item_errors.append(f"fixed_desires.{desire_id}.sentence.high must be a string")
        if not isinstance(implicit_satisfaction, dict):
            item_errors.append(f"fixed_desires.{desire_id}.implicit_satisfaction must be an object")
        else:
            for tool_name, quality in implicit_satisfaction.items():
                if not isinstance(tool_name, str) or not tool_name:
                    item_errors.append(
                        f"fixed_desires.{desire_id}.implicit_satisfaction keys must be strings"
                    )
                if not isinstance(quality, (int, float)) or isinstance(quality, bool):
                    item_errors.append(
                        "fixed_desires."
                        f"{desire_id}.implicit_satisfaction.{tool_name} must be numeric"
                    )

        if item_errors:
            errors.extend(item_errors)
            continue

        parsed_satisfaction_hours = float(cast(int | float, satisfaction_hours))
        parsed_maslow_level = int(cast(int, maslow_level))
        fixed_desires.append(
            DesireCatalogItem(
                id=desire_id,
                display_name=display_name,
                satisfaction_hours=parsed_satisfaction_hours,
                maslow_level=parsed_maslow_level,
            )
        )

    if errors:
        return _fallback_catalog(
            version=version if isinstance(version, int) else None,
            status="invalid",
            errors=tuple(errors),
            source_path=source_path,
        )

    fixed_desires.sort(key=lambda item: (item.maslow_level, item.id))
    return DesireCatalog(
        version=version,
        fixed_desires=tuple(fixed_desires),
        status="ok",
        errors=(),
        source_path=source_path,
        implicit_rules=tuple(rule for rule in raw_implicit_rules if isinstance(rule, dict)),
        emergent=dict(raw_emergent),
    )
