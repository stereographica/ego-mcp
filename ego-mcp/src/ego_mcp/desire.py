"""Desire engine with catalog-backed fixed desires and persisted state."""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from ego_mcp import timezone_utils
from ego_mcp.desire_catalog import (
    DEFAULT_EMERGENT,
    DesireCatalog,
    DesireConfigurationError,
    default_desire_catalog,
    desire_catalog_settings_path,
    ensure_default_desire_catalog_file,
    load_desire_catalog,
)
from ego_mcp.types import Emotion, Notion

DESIRES: dict[str, dict[str, Any]] = default_desire_catalog().legacy_desires()
IMPLICIT_SATISFACTION_MAP: dict[str, list[tuple[str, float]]] = {}
for _desire_id, _config in default_desire_catalog().fixed_desires.items():
    for _tool_name, _quality in _config.implicit_satisfaction.items():
        IMPLICIT_SATISFACTION_MAP.setdefault(_tool_name, []).append(
            (_desire_id, _quality)
        )
REMEMBER_INTROSPECTION_IMPLICIT_SATISFACTION = ("cognitive_coherence", 0.4)
EMERGENT_EXPIRY_HOURS = float(DEFAULT_EMERGENT["expiry_hours"])
EMERGENT_SATISFACTION_HOURS = float(DEFAULT_EMERGENT["satisfaction_hours"])
EMERGENT_SATISFIED_TTL_HOURS = float(DEFAULT_EMERGENT["satisfied_ttl_hours"])


def _emergent_template_for_notion(notion: Notion) -> str | None:
    emotion = notion.emotion_tone
    valence = notion.valence
    if emotion in {Emotion.MELANCHOLY, Emotion.SAD} and valence < 0:
        return "You want to be with someone."
    if emotion == Emotion.FRUSTRATED and valence < 0:
        return "You want to get away from something."
    if emotion == Emotion.ANXIOUS and valence < 0:
        return "You want to feel safe."
    if emotion in {Emotion.EXCITED, Emotion.CURIOUS} and valence > 0:
        return "You want to grasp something."
    if emotion in {Emotion.HAPPY, Emotion.CONTENTMENT} and valence > 0:
        return "You want to stay in this."
    if emotion == Emotion.NOSTALGIC:
        return "You want to go back to something."
    return None


def _calculate_sigmoid_level(
    elapsed_hours: float,
    satisfaction_hours: float,
    satisfaction_quality: float = 0.5,
) -> float:
    """Non-linear desire level via sigmoid."""
    adjusted_hours = satisfaction_hours * (0.5 + 0.5 * satisfaction_quality)
    if adjusted_hours <= 0:
        return 1.0
    x = (elapsed_hours / adjusted_hours) * 6 - 3
    return 1.0 / (1.0 + math.exp(-x))


class DesireEngine:
    """Manages fixed and emergent desires with catalog-backed configuration."""

    def __init__(self, state_path: Path, catalog_path: Path | None = None) -> None:
        self._state_path = state_path
        self._catalog_path = catalog_path or state_path.parent / "settings" / "desires.json"
        ensure_default_desire_catalog_file(self._catalog_path)
        self._catalog: DesireCatalog | None = None
        self._catalog_error: DesireConfigurationError | None = None
        self._state: dict[str, dict[str, Any]] = {}
        self._refresh_catalog()
        self.load_state()

    @classmethod
    def from_data_dir(cls, data_dir: Path) -> DesireEngine:
        """Create a desire engine using the runtime config/state file layout."""
        return cls(
            state_path=data_dir / "desire_state.json",
            catalog_path=desire_catalog_settings_path(data_dir),
        )

    @property
    def catalog(self) -> DesireCatalog:
        """Return the validated catalog, or raise a config error."""
        return self.require_valid_catalog()

    def require_valid_catalog(self) -> DesireCatalog:
        """Reload and validate the catalog before desire-heavy operations."""
        self._refresh_catalog()
        if self._catalog is None:
            assert self._catalog_error is not None
            raise self._catalog_error
        if self._sync_state_to_catalog(self._catalog):
            self.save_state()
        return self._catalog

    def _refresh_catalog(self) -> None:
        try:
            self._catalog = load_desire_catalog(self._catalog_path)
            self._catalog_error = None
        except DesireConfigurationError as exc:
            self._catalog = None
            self._catalog_error = exc

    def _catalog_for_state(self) -> DesireCatalog:
        return self._catalog if self._catalog is not None else default_desire_catalog()

    def _default_fixed_state(
        self,
        catalog: DesireCatalog,
    ) -> dict[str, dict[str, Any]]:
        now = timezone_utils.now().isoformat()
        return {
            name: {
                "last_satisfied": now,
                "satisfaction_quality": 0.5,
                "boost": 0.0,
                "is_emergent": False,
                "created": "",
            }
            for name in catalog.fixed_desires
        }

    def _sync_state_to_catalog(self, catalog: DesireCatalog) -> bool:
        defaults = self._default_fixed_state(catalog)
        merged: dict[str, dict[str, Any]] = dict(defaults)
        changed = set(self._state) != set(defaults)
        for name, raw in self._state.items():
            if not isinstance(raw, dict):
                changed = True
                continue
            if bool(raw.get("is_emergent", False)):
                merged[name] = dict(raw)
                continue
            if name not in defaults:
                changed = True
                continue
            merged[name] = {**defaults[name], **raw}
        if merged != self._state:
            changed = True
        self._state = merged
        return changed

    def _is_known_desire(self, name: str) -> bool:
        catalog = self._catalog_for_state()
        if name in catalog.fixed_desires:
            return True
        return bool(self._state.get(name, {}).get("is_emergent", False))

    def _desire_names(self) -> list[str]:
        catalog = self.require_valid_catalog()
        names = list(catalog.fixed_desires.keys())
        for name, state in self._state.items():
            if state.get("is_emergent", False):
                names.append(name)
        return names

    def expire_emergent_desires(self) -> list[str]:
        catalog = self.require_valid_catalog()
        now = timezone_utils.now()
        expired: list[str] = []
        for name, state in list(self._state.items()):
            if not state.get("is_emergent", False):
                continue
            created_str = str(state.get("created", ""))
            if not created_str:
                continue
            try:
                created = datetime.fromisoformat(created_str)
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone_utils.app_timezone())
            except ValueError:
                continue
            last_satisfied = str(state.get("last_satisfied", ""))
            if last_satisfied:
                try:
                    satisfied_at = datetime.fromisoformat(last_satisfied)
                    if satisfied_at.tzinfo is None:
                        satisfied_at = satisfied_at.replace(
                            tzinfo=timezone_utils.app_timezone()
                        )
                except ValueError:
                    satisfied_at = created
                age_hours = (now - satisfied_at).total_seconds() / 3600
                if age_hours < catalog.emergent.satisfied_ttl_hours:
                    continue
            else:
                age_hours = (now - created).total_seconds() / 3600
                if age_hours < catalog.emergent.expiry_hours:
                    continue
            expired.append(name)
            del self._state[name]
        if expired:
            self.save_state()
        return expired

    def generate_emergent_desires(self, notions: list[Notion]) -> list[str]:
        catalog = self.require_valid_catalog()
        created: list[str] = []
        for notion in notions:
            if notion.confidence < 0.7:
                continue
            label = _emergent_template_for_notion(notion)
            if label is None or self._is_known_desire(label):
                continue
            self._state[label] = {
                "last_satisfied": "",
                "satisfaction_quality": 0.5,
                "boost": 0.0,
                "is_emergent": True,
                "created": timezone_utils.now().isoformat(),
                "satisfaction_hours": catalog.emergent.satisfaction_hours,
            }
            created.append(label)
        if created:
            self.save_state()
        return created

    def compute_levels(self) -> dict[str, float]:
        return self.compute_levels_with_modulation()

    def compute_levels_with_modulation(
        self,
        context_boosts: dict[str, float] | None = None,
        emotional_modulation: dict[str, float] | None = None,
        prediction_error: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """Compute current levels for all fixed and emergent desires."""
        catalog = self.require_valid_catalog()
        self.expire_emergent_desires()
        now = timezone_utils.now()
        levels: dict[str, float] = {}
        context_boosts = context_boosts or {}
        emotional_modulation = emotional_modulation or {}
        prediction_error = prediction_error or {}

        for name in self._desire_names():
            desire_state = self._state.get(name, {})
            fixed = catalog.fixed_desires.get(name)
            if fixed is not None:
                satisfaction_hours = fixed.satisfaction_hours
            else:
                satisfaction_hours = float(
                    desire_state.get(
                        "satisfaction_hours",
                        catalog.emergent.satisfaction_hours,
                    )
                )

            last_str = desire_state.get("last_satisfied", "")
            quality = float(desire_state.get("satisfaction_quality", 0.5))
            boost = float(desire_state.get("boost", 0.0))

            if last_str:
                try:
                    last = datetime.fromisoformat(last_str)
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=timezone_utils.app_timezone())
                    elapsed = (now - last).total_seconds() / 3600
                except ValueError:
                    elapsed = satisfaction_hours
            else:
                elapsed = satisfaction_hours

            base = _calculate_sigmoid_level(elapsed, satisfaction_hours, quality)
            level = min(
                1.0,
                max(
                    0.0,
                    base
                    + boost
                    + float(context_boosts.get(name, 0.0))
                    + float(emotional_modulation.get(name, 0.0))
                    + float(prediction_error.get(name, 0.0)),
                ),
            )
            levels[name] = round(level, 3)
        return levels

    def satisfy(self, name: str, quality: float = 0.7) -> float:
        """Mark a desire as satisfied. Returns new level."""
        self.require_valid_catalog()
        if not self._is_known_desire(name):
            raise ValueError(f"Unknown desire: {name}")
        now = timezone_utils.now().isoformat()
        if name not in self._state:
            self._state[name] = {}
        self._state[name]["last_satisfied"] = now
        self._state[name]["satisfaction_quality"] = max(0.0, min(1.0, quality))
        self._state[name]["boost"] = 0.0
        self.save_state()
        return self.compute_levels().get(name, 0.0)

    def satisfy_implicit(self, tool_name: str, category: str | None = None) -> None:
        """Partially satisfy desires based on a tool usage pattern."""
        catalog = self.require_valid_catalog()
        for desire_name, quality in catalog.tool_implicit_effects(
            tool_name,
            category=category,
        ):
            self.satisfy(desire_name, quality=quality)

    def boost(self, name: str, amount: float) -> float:
        """Temporarily boost a desire level. Returns new level."""
        catalog = self.require_valid_catalog()
        if not self._is_known_desire(name):
            raise ValueError(f"Unknown desire: {name}")
        if name not in self._state:
            self._state[name] = {
                "last_satisfied": timezone_utils.now().isoformat(),
                "satisfaction_quality": 0.5,
                "boost": 0.0,
                "is_emergent": name not in catalog.fixed_desires,
                "created": "",
            }
        current_boost = float(self._state[name].get("boost", 0.0))
        self._state[name]["boost"] = min(1.0, current_boost + amount)
        self.save_state()
        return self.compute_levels().get(name, 0.0)

    def format_summary(self) -> str:
        """Format desire levels as sorted English summary."""
        levels = self.compute_levels()

        def tag(level: float) -> str:
            if level >= 0.7:
                return "high"
            if level >= 0.4:
                return "mid"
            return "low"

        sorted_desires = sorted(levels.items(), key=lambda x: -x[1])
        return " ".join(f"{name}[{tag(level)}]" for name, level in sorted_desires)

    def save_state(self) -> None:
        """Persist state to JSON file."""
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._state_path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, ensure_ascii=False, indent=2)

    def load_state(self) -> None:
        """Load state from JSON file, or initialize defaults."""
        catalog = self._catalog_for_state()
        defaults = self._default_fixed_state(catalog)
        if self._state_path.exists():
            try:
                with open(self._state_path, encoding="utf-8") as f:
                    parsed = json.load(f)
                if isinstance(parsed, dict):
                    merged = dict(defaults)
                    for name, raw in parsed.items():
                        if not isinstance(raw, dict):
                            continue
                        if bool(raw.get("is_emergent", False)):
                            merged[name] = dict(raw)
                        elif name in defaults:
                            merged[name] = {**defaults[name], **raw}
                    self._state = merged
                else:
                    self._state = defaults
                return
            except (json.JSONDecodeError, OSError):
                pass
        self._state = defaults
        self.save_state()
