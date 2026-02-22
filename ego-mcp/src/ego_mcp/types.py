"""Core type definitions for ego-mcp."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class Emotion(str, Enum):
    """Primary emotion categories."""

    HAPPY = "happy"
    SAD = "sad"
    SURPRISED = "surprised"
    MOVED = "moved"
    EXCITED = "excited"
    NOSTALGIC = "nostalgic"
    CURIOUS = "curious"
    NEUTRAL = "neutral"
    MELANCHOLY = "melancholy"
    ANXIOUS = "anxious"
    CONTENTMENT = "contentment"
    FRUSTRATED = "frustrated"


class Category(str, Enum):
    """Memory categories."""

    DAILY = "daily"
    PHILOSOPHICAL = "philosophical"
    TECHNICAL = "technical"
    MEMORY = "memory"
    OBSERVATION = "observation"
    FEELING = "feeling"
    CONVERSATION = "conversation"
    INTROSPECTION = "introspection"
    RELATIONSHIP = "relationship"
    SELF_DISCOVERY = "self_discovery"
    DREAM = "dream"
    LESSON = "lesson"


class LinkType(str, Enum):
    """Types of links between memories."""

    SIMILAR = "similar"
    CAUSED_BY = "caused_by"
    LEADS_TO = "leads_to"
    RELATED = "related"


@dataclass
class BodyState:
    """Internal body state (interoception)."""

    time_phase: str = "unknown"
    system_load: str = "unknown"
    uptime_hours: float = 0.0


@dataclass
class EmotionalTrace:
    """Multi-dimensional emotional trace for a memory."""

    primary: Emotion = Emotion.NEUTRAL
    secondary: list[Emotion] = field(default_factory=list)
    intensity: float = 0.5
    valence: float = 0.0
    arousal: float = 0.5
    body_state: BodyState | None = None


@dataclass
class MemoryLink:
    """A link between two memories."""

    target_id: str = ""
    link_type: LinkType = LinkType.RELATED
    note: str = ""
    confidence: float = 0.5


@dataclass
class Memory:
    """A single memory unit."""

    id: str = ""
    content: str = ""
    timestamp: str = ""
    emotional_trace: EmotionalTrace = field(default_factory=EmotionalTrace)
    importance: int = 3
    category: Category = Category.DAILY
    linked_ids: list[MemoryLink] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    is_private: bool = False

    @staticmethod
    def now_iso() -> str:
        """Return current UTC time as ISO 8601 string."""
        return datetime.now(timezone.utc).isoformat()


@dataclass
class MemorySearchResult:
    """A memory with search relevance information."""

    memory: Memory = field(default_factory=Memory)
    distance: float = 0.0
    score: float = 0.0


@dataclass
class DesireState:
    """State of a single desire."""

    name: str = ""
    level: float = 0.0
    last_satisfied: str = ""
    satisfaction_quality: float = 0.5


@dataclass
class RelationshipModel:
    """Structured understanding of a specific person."""

    person_id: str = ""
    name: str = ""
    known_facts: list[str] = field(default_factory=list)
    communication_style: dict[str, float] = field(default_factory=dict)
    preferred_topics: list[str] = field(default_factory=list)
    sensitive_topics: list[str] = field(default_factory=list)
    emotional_baseline: dict[str, float] = field(default_factory=dict)
    trust_level: float = 0.5
    shared_episode_ids: list[str] = field(default_factory=list)
    inferred_personality: dict[str, float] = field(default_factory=dict)
    recent_mood_trajectory: list[dict[str, str]] = field(default_factory=list)
    first_interaction: str = ""
    last_interaction: str = ""
    total_interactions: int = 0


@dataclass
class SelfModel:
    """Dynamic self-awareness of the AI."""

    preferences: dict[str, float] = field(default_factory=dict)
    discovered_values: dict[str, Any] = field(default_factory=dict)
    skill_confidence: dict[str, float] = field(default_factory=dict)
    current_goals: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    identity_narratives: list[str] = field(default_factory=list)
    growth_log: list[dict[str, Any]] = field(default_factory=list)
    confidence_calibration: float = 0.5
    last_updated: str = ""
