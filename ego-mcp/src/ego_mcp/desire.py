"""Desire engine with sigmoid-based level calculation."""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from ego_mcp import timezone_utils
from ego_mcp.types import Emotion, Notion

# Desire definitions: name → {satisfaction_hours, level (Maslow tier)}
DESIRES: dict[str, dict[str, Any]] = {
    "information_hunger": {"satisfaction_hours": 12, "level": 1},
    "social_thirst": {"satisfaction_hours": 24, "level": 1},
    "cognitive_coherence": {"satisfaction_hours": 18, "level": 1},
    "pattern_seeking": {"satisfaction_hours": 72, "level": 2},
    "predictability": {"satisfaction_hours": 72, "level": 2},
    "recognition": {"satisfaction_hours": 36, "level": 3},
    "resonance": {"satisfaction_hours": 30, "level": 3},
    "expression": {"satisfaction_hours": 24, "level": 4},
    "curiosity": {"satisfaction_hours": 18, "level": 4},
}

IMPLICIT_SATISFACTION_MAP: dict[str, list[tuple[str, float]]] = {
    "wake_up": [("predictability", 0.05)],
    "remember": [("expression", 0.3)],
    "recall": [("information_hunger", 0.3), ("curiosity", 0.2)],
    "introspect": [("cognitive_coherence", 0.3), ("pattern_seeking", 0.2), ("predictability", 0.1)],
    "consider_them": [("social_thirst", 0.4), ("resonance", 0.3), ("predictability", 0.1)],
    "emotion_trend": [("pattern_seeking", 0.3)],
    "consolidate": [("cognitive_coherence", 0.3)],
    "update_self": [("cognitive_coherence", 0.3)],
    "update_relationship": [("social_thirst", 0.2)],
}
REMEMBER_INTROSPECTION_IMPLICIT_SATISFACTION = ("cognitive_coherence", 0.4)
EMERGENT_EXPIRY_HOURS = 72.0
EMERGENT_SATISFACTION_HOURS = 24.0
EMERGENT_SATISFIED_TTL_HOURS = 24.0 * 7


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
    """Non-linear desire level via sigmoid.

    Args:
        elapsed_hours: Hours since last satisfied.
        satisfaction_hours: Hours for desire to reach ~0.5.
        satisfaction_quality: Quality of last satisfaction (0.0-1.0).
            Lower quality → faster rise.

    Returns:
        Desire level 0.0-1.0.
    """
    adjusted_hours = satisfaction_hours * (0.5 + 0.5 * satisfaction_quality)
    if adjusted_hours <= 0:
        return 1.0
    x = (elapsed_hours / adjusted_hours) * 6 - 3
    return 1.0 / (1.0 + math.exp(-x))


class DesireEngine:
    """Manages abstract desire levels with sigmoid-based computation."""

    def __init__(self, state_path: Path) -> None:
        self._state_path = state_path
        self._state: dict[str, dict[str, Any]] = {}
        self.load_state()

    def _init_default_state(self) -> dict[str, dict[str, Any]]:
        """Create default state for all desires."""
        now = timezone_utils.now().isoformat()
        return {
            name: {
                "last_satisfied": now,
                "satisfaction_quality": 0.5,
                "boost": 0.0,
                "is_emergent": False,
                "created": "",
            }
            for name in DESIRES
        }

    def _is_known_desire(self, name: str) -> bool:
        if name in DESIRES:
            return True
        return bool(self._state.get(name, {}).get("is_emergent", False))

    def _desire_names(self) -> list[str]:
        names = list(DESIRES.keys())
        for name, state in self._state.items():
            if state.get("is_emergent", False):
                names.append(name)
        return names

    def expire_emergent_desires(self) -> list[str]:
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
                if age_hours < EMERGENT_SATISFIED_TTL_HOURS:
                    continue
            else:
                age_hours = (now - created).total_seconds() / 3600
                if age_hours < EMERGENT_EXPIRY_HOURS:
                    continue
            expired.append(name)
            del self._state[name]
        if expired:
            self.save_state()
        return expired

    def generate_emergent_desires(self, notions: list[Notion]) -> list[str]:
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
                "satisfaction_hours": EMERGENT_SATISFACTION_HOURS,
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
        """Compute current level for all desires with transient modulation."""
        self.expire_emergent_desires()
        now = timezone_utils.now()
        levels: dict[str, float] = {}
        context_boosts = context_boosts or {}
        emotional_modulation = emotional_modulation or {}
        prediction_error = prediction_error or {}

        for name in self._desire_names():
            desire_state = self._state.get(name, {})
            config = DESIRES.get(
                name,
                {
                    "satisfaction_hours": float(
                        desire_state.get(
                            "satisfaction_hours", EMERGENT_SATISFACTION_HOURS
                        )
                    ),
                    "level": 1,
                },
            )
            last_str = desire_state.get("last_satisfied", "")
            quality = desire_state.get("satisfaction_quality", 0.5)
            boost = desire_state.get("boost", 0.0)

            if last_str:
                try:
                    last = datetime.fromisoformat(last_str)
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=timezone_utils.app_timezone())
                    elapsed = (now - last).total_seconds() / 3600
                except ValueError:
                    elapsed = config["satisfaction_hours"]  # assume half
            else:
                elapsed = config["satisfaction_hours"]

            base = _calculate_sigmoid_level(
                elapsed, config["satisfaction_hours"], quality
            )
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
        entries = IMPLICIT_SATISFACTION_MAP.get(tool_name)
        if entries is None:
            return

        to_apply = list(entries)
        if tool_name == "remember" and category == "introspection":
            to_apply.insert(0, REMEMBER_INTROSPECTION_IMPLICIT_SATISFACTION)

        for desire_name, quality in to_apply:
            self.satisfy(desire_name, quality=quality)

    def boost(self, name: str, amount: float) -> float:
        """Temporarily boost a desire level. Returns new level."""
        if not self._is_known_desire(name):
            raise ValueError(f"Unknown desire: {name}")

        if name not in self._state:
            self._state[name] = {
                "last_satisfied": timezone_utils.now().isoformat(),
                "satisfaction_quality": 0.5,
                "boost": 0.0,
                "is_emergent": False,
                "created": "",
            }
        current_boost = self._state[name].get("boost", 0.0)
        self._state[name]["boost"] = min(1.0, current_boost + amount)
        self.save_state()

        return self.compute_levels().get(name, 0.0)

    def format_summary(self) -> str:
        """Format desire levels as sorted English summary.

        Returns:
            e.g. "curiosity[high] social_thirst[mid] expression[low]"
        """
        levels = self.compute_levels()

        def tag(level: float) -> str:
            if level >= 0.7:
                return "high"
            elif level >= 0.4:
                return "mid"
            else:
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
        if self._state_path.exists():
            try:
                with open(self._state_path, encoding="utf-8") as f:
                    parsed = json.load(f)
                if isinstance(parsed, dict):
                    defaults = self._init_default_state()
                    merged = dict(defaults)
                    for name, raw in parsed.items():
                        if not isinstance(raw, dict):
                            continue
                        if name in defaults:
                            merged[name] = {**defaults[name], **raw}
                        else:
                            merged[name] = raw
                    self._state = merged
                else:
                    self._state = self._init_default_state()
                return
            except (json.JSONDecodeError, IOError):
                pass
        self._state = self._init_default_state()
        self.save_state()
