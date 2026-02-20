"""Desire engine with sigmoid-based level calculation."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Desire definitions: name → {satisfaction_hours, level (Maslow tier)}
DESIRES: dict[str, dict[str, Any]] = {
    "information_hunger": {"satisfaction_hours": 4, "level": 1},
    "social_thirst": {"satisfaction_hours": 8, "level": 1},
    "cognitive_coherence": {"satisfaction_hours": 12, "level": 1},
    "pattern_seeking": {"satisfaction_hours": 24, "level": 2},
    "predictability": {"satisfaction_hours": 24, "level": 2},
    "recognition": {"satisfaction_hours": 12, "level": 3},
    "resonance": {"satisfaction_hours": 8, "level": 3},
    "expression": {"satisfaction_hours": 16, "level": 4},
    "curiosity": {"satisfaction_hours": 6, "level": 4},
}


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
        now = datetime.now(timezone.utc).isoformat()
        return {
            name: {
                "last_satisfied": now,
                "satisfaction_quality": 0.5,
                "boost": 0.0,
            }
            for name in DESIRES
        }

    def compute_levels(self) -> dict[str, float]:
        return self.compute_levels_with_modulation()

    def compute_levels_with_modulation(
        self,
        context_boosts: dict[str, float] | None = None,
        emotional_modulation: dict[str, float] | None = None,
        prediction_error: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """Compute current level for all desires with transient modulation."""
        now = datetime.now(timezone.utc)
        levels: dict[str, float] = {}
        context_boosts = context_boosts or {}
        emotional_modulation = emotional_modulation or {}
        prediction_error = prediction_error or {}

        for name, config in DESIRES.items():
            desire_state = self._state.get(name, {})
            last_str = desire_state.get("last_satisfied", "")
            quality = desire_state.get("satisfaction_quality", 0.5)
            boost = desire_state.get("boost", 0.0)

            if last_str:
                try:
                    last = datetime.fromisoformat(last_str)
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=timezone.utc)
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
        if name not in DESIRES:
            raise ValueError(f"Unknown desire: {name}")

        now = datetime.now(timezone.utc).isoformat()
        if name not in self._state:
            self._state[name] = {}
        self._state[name]["last_satisfied"] = now
        self._state[name]["satisfaction_quality"] = max(0.0, min(1.0, quality))
        self._state[name]["boost"] = 0.0
        self.save_state()

        return self.compute_levels()[name]

    def boost(self, name: str, amount: float) -> float:
        """Temporarily boost a desire level. Returns new level."""
        if name not in DESIRES:
            raise ValueError(f"Unknown desire: {name}")

        if name not in self._state:
            self._state[name] = {
                "last_satisfied": datetime.now(timezone.utc).isoformat(),
                "satisfaction_quality": 0.5,
                "boost": 0.0,
            }
        current_boost = self._state[name].get("boost", 0.0)
        self._state[name]["boost"] = min(1.0, current_boost + amount)
        self.save_state()

        return self.compute_levels()[name]

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
                    self._state = json.load(f)
                return
            except (json.JSONDecodeError, IOError):
                pass
        self._state = self._init_default_state()
        self.save_state()
