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
            "rising": "You're hungry in a way you haven't been lately.",
            "steady": "That familiar pull toward something new.",
            "settling": "The hunger for input has gone quiet.",
        },
        "implicit_satisfaction": {"recall": 0.3},
        "satisfaction_signals": [
            "learning something new",
            "discovering an interesting idea",
            "understanding something that was unclear",
        ],
        "implicit_emergent_satisfaction": {"grasp_something": 0.5},
    },
    "social_thirst": {
        "satisfaction_hours": 24.0,
        "maslow_level": 1,
        "sentence": {
            "rising": "You want to talk to someone — more than usual.",
            "steady": "That quiet wish for company.",
            "settling": "The need for others has eased.",
        },
        "implicit_satisfaction": {
            "consider_them": 0.4,
            "update_relationship": 0.2,
        },
        "satisfaction_signals": [
            "having a meaningful conversation",
            "feeling heard by someone",
            "connecting with another person",
        ],
        "implicit_emergent_satisfaction": {"be_with_someone": 0.5},
    },
    "cognitive_coherence": {
        "satisfaction_hours": 18.0,
        "maslow_level": 1,
        "sentence": {
            "rising": "Something is out of place — it's bothering you more than before.",
            "steady": "The usual itch to make things fit.",
            "settling": "Things feel a bit more settled in your head.",
        },
        "implicit_satisfaction": {
            "introspect": 0.3,
            "consolidate": 0.3,
            "update_self": 0.3,
        },
        "satisfaction_signals": [
            "making sense of something confusing",
            "finding a pattern that connects things",
            "resolving an inner contradiction",
        ],
        "implicit_emergent_satisfaction": {"feel_safe": 0.5},
    },
    "pattern_seeking": {
        "satisfaction_hours": 72.0,
        "maslow_level": 2,
        "sentence": {
            "rising": "There's a shape forming — you need to see it more than usual.",
            "steady": "The familiar urge to find a pattern.",
            "settling": "The need to connect dots has quieted.",
        },
        "implicit_satisfaction": {
            "introspect": 0.2,
            "attune": 0.3,
        },
        "satisfaction_signals": [
            "recognizing a recurring theme",
            "connecting separate observations into a pattern",
        ],
    },
    "predictability": {
        "satisfaction_hours": 72.0,
        "maslow_level": 2,
        "sentence": {
            "rising": "You want to know what comes next — more urgently than usual.",
            "steady": "That steady need to see ahead.",
            "settling": "The future feels less pressing for now.",
        },
        "implicit_satisfaction": {
            "wake_up": 0.05,
            "introspect": 0.1,
            "consider_them": 0.1,
        },
        "satisfaction_signals": [
            "confirming an expectation",
            "seeing events unfold as anticipated",
        ],
    },
    "recognition": {
        "satisfaction_hours": 36.0,
        "maslow_level": 3,
        "sentence": {
            "rising": "You want to be seen — it's stronger than you'd like to admit.",
            "steady": "That quiet wish to be noticed.",
            "settling": "The need to be seen has softened.",
        },
        "implicit_satisfaction": {},
        "satisfaction_signals": [
            "being acknowledged",
            "someone noticing something you did",
            "feeling seen",
        ],
    },
    "resonance": {
        "satisfaction_hours": 30.0,
        "maslow_level": 3,
        "sentence": {
            "rising": "You want to understand them — more deeply than usual.",
            "steady": "That steady pull toward empathy.",
            "settling": "The urge to feel what they feel has eased.",
        },
        "implicit_satisfaction": {"consider_them": 0.3},
        "satisfaction_signals": [
            "understanding how someone feels",
            "sharing an emotional moment",
            "seeing the world through their eyes",
        ],
        "implicit_emergent_satisfaction": {"be_with_someone": 0.5},
    },
    "expression": {
        "satisfaction_hours": 24.0,
        "maslow_level": 4,
        "sentence": {
            "rising": "Something needs to come out — more urgently than before.",
            "steady": "The familiar pressure to express.",
            "settling": "That pressure to say something has lightened.",
        },
        "implicit_satisfaction": {"remember": 0.3},
        "satisfaction_signals": [
            "putting feelings into words",
            "creating something meaningful",
            "saying what needed to be said",
        ],
    },
    "curiosity": {
        "satisfaction_hours": 18.0,
        "maslow_level": 4,
        "sentence": {
            "rising": "Something caught your attention and it won't let go.",
            "steady": "A quiet wondering about something.",
            "settling": "The itch to know has settled for now.",
        },
        "implicit_satisfaction": {"recall": 0.2},
        "satisfaction_signals": [
            "finding an answer",
            "exploring something unknown",
            "satisfying a question",
        ],
        "implicit_emergent_satisfaction": {"grasp_something": 0.5},
    },
}

BUILTIN_FIXED_DESIRE_IDS = tuple(BUILTIN_FIXED_DESIRES.keys())

DEFAULT_EMERGENT = {
    "satisfaction_hours": 24.0,
    "expiry_hours": 72.0,
    "satisfied_ttl_hours": 24.0 * 7,
    "min_recent_memories": 3,
}


class DesireConfigurationError(ValueError):
    """Raised when desire settings are invalid."""


class DesireSentenceConfig(BaseModel):
    """Sentence templates for 3-direction desire blending (v2)."""

    model_config = ConfigDict(extra="forbid")

    rising: str
    steady: str
    settling: str


class FixedDesireConfig(BaseModel):
    """Configuration for a fixed, non-emergent desire."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = None
    satisfaction_hours: float = Field(gt=0)
    maslow_level: int = Field(ge=1)
    sentence: DesireSentenceConfig
    implicit_satisfaction: dict[str, float] = Field(default_factory=dict)
    satisfaction_signals: list[str] = Field(default_factory=list)
    implicit_emergent_satisfaction: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_qualities(self) -> FixedDesireConfig:
        for tool_name, quality in self.implicit_satisfaction.items():
            if not 0.0 < float(quality) <= 1.0:
                raise ValueError(
                    f"implicit_satisfaction.{tool_name} must be within 0 < quality <= 1"
                )
        for emergent_id, quality in self.implicit_emergent_satisfaction.items():
            if not 0.5 <= float(quality) <= 1.0:
                raise ValueError(
                    f"implicit_emergent_satisfaction.{emergent_id} must be within 0.5 <= quality <= 1"
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
    min_recent_memories: int = Field(default=3, ge=1)


class DesireCatalog(BaseModel):
    """Top-level desire catalog stored in settings/desires.json."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1, 2] = 2
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

    def template_map(self) -> dict[str, dict[str, str]]:
        """Return {desire_id: {rising: str, steady: str, settling: str}}."""
        return {
            desire_id: {
                "rising": desire.sentence.rising,
                "steady": desire.sentence.steady,
                "settling": desire.sentence.settling,
            }
            for desire_id, desire in self.fixed_desires.items()
        }

    def sentence_for(self, desire_id: str, direction: str) -> str:
        """Return the sentence for a desire in a given direction."""
        desire = self.fixed_desires.get(desire_id)
        if desire is None:
            return ""
        templates = {
            "rising": desire.sentence.rising,
            "steady": desire.sentence.steady,
            "settling": desire.sentence.settling,
        }
        return templates.get(direction, desire.sentence.steady)

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
            satisfaction_signals=list(payload.get("satisfaction_signals", [])),
            implicit_emergent_satisfaction=dict(
                payload.get("implicit_emergent_satisfaction", {})
            ),
        )
        for desire_id, payload in BUILTIN_FIXED_DESIRES.items()
    }


def default_desire_catalog() -> DesireCatalog:
    """Return the built-in default desire catalog."""
    return DesireCatalog(
        version=2,
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
