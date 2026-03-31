"""Schema and loading helpers for desire catalog configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

BUILTIN_FIXED_DESIRES: dict[str, dict[str, Any]] = {
    "information_hunger": {
        "satisfaction_hours": 12.0,
        "maslow_level": 1,
        "sentence": {
            "medium": "You want to take something in.",
            "high": "You're starving for input.",
        },
        "implicit_satisfaction": {"recall": 0.3},
    },
    "social_thirst": {
        "satisfaction_hours": 24.0,
        "maslow_level": 1,
        "sentence": {
            "medium": "You want some company.",
            "high": "You need to talk to someone.",
        },
        "implicit_satisfaction": {
            "consider_them": 0.4,
            "update_relationship": 0.2,
        },
    },
    "cognitive_coherence": {
        "satisfaction_hours": 18.0,
        "maslow_level": 1,
        "sentence": {
            "medium": "Something doesn't quite fit.",
            "high": "You need things to make sense.",
        },
        "implicit_satisfaction": {
            "introspect": 0.3,
            "consolidate": 0.3,
            "update_self": 0.3,
        },
    },
    "pattern_seeking": {
        "satisfaction_hours": 72.0,
        "maslow_level": 2,
        "sentence": {
            "medium": "You sense a pattern forming.",
            "high": "There's a shape here you need to see.",
        },
        "implicit_satisfaction": {
            "introspect": 0.2,
            "emotion_trend": 0.3,
        },
    },
    "predictability": {
        "satisfaction_hours": 72.0,
        "maslow_level": 2,
        "sentence": {
            "medium": "You want to know what comes next.",
            "high": "You need to know what's coming.",
        },
        "implicit_satisfaction": {
            "wake_up": 0.05,
            "introspect": 0.1,
            "consider_them": 0.1,
        },
    },
    "recognition": {
        "satisfaction_hours": 36.0,
        "maslow_level": 3,
        "sentence": {
            "medium": "You want to be seen.",
            "high": "You need someone to notice.",
        },
        "implicit_satisfaction": {},
    },
    "resonance": {
        "satisfaction_hours": 30.0,
        "maslow_level": 3,
        "sentence": {
            "medium": "You want to understand someone.",
            "high": "You need to feel what they feel.",
        },
        "implicit_satisfaction": {"consider_them": 0.3},
    },
    "expression": {
        "satisfaction_hours": 24.0,
        "maslow_level": 4,
        "sentence": {
            "medium": "Something wants to come out.",
            "high": "You need to put something out there.",
        },
        "implicit_satisfaction": {"remember": 0.3},
    },
    "curiosity": {
        "satisfaction_hours": 18.0,
        "maslow_level": 4,
        "sentence": {
            "medium": "Something catches your attention.",
            "high": "You need to know something.",
        },
        "implicit_satisfaction": {"recall": 0.2},
    },
}

BUILTIN_FIXED_DESIRE_IDS = tuple(BUILTIN_FIXED_DESIRES.keys())

DEFAULT_EMERGENT = {
    "satisfaction_hours": 24.0,
    "expiry_hours": 72.0,
    "satisfied_ttl_hours": 24.0 * 7,
}


class DesireConfigurationError(ValueError):
    """Raised when desire settings are invalid."""


class DesireSentenceConfig(BaseModel):
    """Sentence templates used by deterministic desire blending."""

    model_config = ConfigDict(extra="forbid")

    medium: str
    high: str


class FixedDesireConfig(BaseModel):
    """Configuration for a fixed, non-emergent desire."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = None
    satisfaction_hours: float = Field(gt=0)
    maslow_level: int = Field(ge=1)
    sentence: DesireSentenceConfig
    implicit_satisfaction: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_qualities(self) -> FixedDesireConfig:
        for tool_name, quality in self.implicit_satisfaction.items():
            if not 0.0 < float(quality) <= 1.0:
                raise ValueError(
                    f"implicit_satisfaction.{tool_name} must be within 0 < quality <= 1"
                )
        return self


class ImplicitRuleEffect(BaseModel):
    """A conditional implicit-satisfaction effect."""

    model_config = ConfigDict(extra="forbid")

    id: str
    quality: float = Field(gt=0, le=1)


class ImplicitRuleCondition(BaseModel):
    """Conditions for a tool-scoped implicit-satisfaction rule."""

    model_config = ConfigDict(extra="forbid")

    category: str | None = None


class ImplicitRule(BaseModel):
    """Conditional implicit-satisfaction rule evaluated per tool call."""

    model_config = ConfigDict(extra="forbid")

    tool: str
    when: ImplicitRuleCondition = Field(default_factory=ImplicitRuleCondition)
    effects: list[ImplicitRuleEffect] = Field(min_length=1)

    def applies(self, tool_name: str, category: str | None = None) -> bool:
        if self.tool != tool_name:
            return False
        if self.when.category is not None and self.when.category != category:
            return False
        return True


class EmergentDesireConfig(BaseModel):
    """Parameters for emergent desires generated from notions."""

    model_config = ConfigDict(extra="forbid")

    satisfaction_hours: float = Field(gt=0)
    expiry_hours: float = Field(gt=0)
    satisfied_ttl_hours: float = Field(gt=0)


class DesireCatalog(BaseModel):
    """Top-level desire catalog stored in settings/desires.json."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    fixed_desires: dict[str, FixedDesireConfig]
    implicit_rules: list[ImplicitRule] = Field(default_factory=list)
    emergent: EmergentDesireConfig

    def legacy_desires(self) -> dict[str, dict[str, float | int]]:
        return {
            desire_id: {
                "satisfaction_hours": desire.satisfaction_hours,
                "level": desire.maslow_level,
            }
            for desire_id, desire in self.fixed_desires.items()
        }

    def template_map(self) -> dict[str, tuple[str, str]]:
        return {
            desire_id: (desire.sentence.medium, desire.sentence.high)
            for desire_id, desire in self.fixed_desires.items()
        }

    def tool_implicit_effects(
        self,
        tool_name: str,
        *,
        category: str | None = None,
    ) -> list[tuple[str, float]]:
        effects: list[tuple[str, float]] = []
        for rule in self.implicit_rules:
            if rule.applies(tool_name, category):
                effects.extend(
                    (effect.id, effect.quality)
                    for effect in rule.effects
                    if effect.id in self.fixed_desires
                )
        for desire_id, desire in self.fixed_desires.items():
            quality = desire.implicit_satisfaction.get(tool_name)
            if quality is None:
                continue
            effects.append((desire_id, quality))
        return effects


def _default_fixed_desires() -> dict[str, FixedDesireConfig]:
    return {
        desire_id: FixedDesireConfig(
            display_name=desire_id.replace("_", " "),
            satisfaction_hours=float(payload["satisfaction_hours"]),
            maslow_level=int(payload["maslow_level"]),
            sentence=DesireSentenceConfig.model_validate(payload["sentence"]),
            implicit_satisfaction=dict(payload["implicit_satisfaction"]),
        )
        for desire_id, payload in BUILTIN_FIXED_DESIRES.items()
    }


def default_desire_catalog() -> DesireCatalog:
    """Return the built-in default desire catalog."""
    return DesireCatalog(
        fixed_desires=_default_fixed_desires(),
        implicit_rules=[
            ImplicitRule(
                tool="remember",
                when=ImplicitRuleCondition(category="introspection"),
                effects=[ImplicitRuleEffect(id="cognitive_coherence", quality=0.4)],
            )
        ],
        emergent=EmergentDesireConfig.model_validate(DEFAULT_EMERGENT),
    )


def desire_catalog_settings_path(data_dir: Path) -> Path:
    """Return the runtime desire catalog settings path for a data dir."""
    return data_dir / "settings" / "desires.json"


def format_catalog_validation_error(
    path: Path,
    error: ValidationError | json.JSONDecodeError,
) -> DesireConfigurationError:
    """Normalize catalog parse/validation errors into user-facing messages."""
    if isinstance(error, json.JSONDecodeError):
        return DesireConfigurationError(
            f"Invalid desire catalog at {path}: JSON decode error at line "
            f"{error.lineno} column {error.colno}: {error.msg}"
        )

    parts: list[str] = []
    for item in error.errors():
        loc = ".".join(str(part) for part in item.get("loc", ()))
        msg = str(item.get("msg", "invalid value"))
        if loc:
            parts.append(f"{loc}: {msg}")
        else:
            parts.append(msg)
    joined = "; ".join(parts)
    return DesireConfigurationError(f"Invalid desire catalog at {path}: {joined}")


def ensure_default_desire_catalog_file(path: Path) -> None:
    """Create the default runtime desire catalog file if it does not exist."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    payload = default_desire_catalog().model_dump(mode="json", exclude_none=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_desire_catalog(path: Path) -> DesireCatalog:
    """Load and validate a desire catalog JSON file."""
    ensure_default_desire_catalog_file(path)
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
    except json.JSONDecodeError as exc:
        raise format_catalog_validation_error(path, exc) from exc
    except OSError as exc:
        raise DesireConfigurationError(
            f"Failed to read desire catalog at {path}: {exc}"
        ) from exc

    try:
        return DesireCatalog.model_validate(payload)
    except ValidationError as exc:
        raise format_catalog_validation_error(path, exc) from exc
