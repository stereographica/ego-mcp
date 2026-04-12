from __future__ import annotations

# Source of truth is ego-mcp's DEFAULT_DESIRES in ego-mcp/src/ego_mcp/desire.py.
DESIRE_METRIC_KEYS: tuple[str, ...] = (
    "information_hunger",
    "social_thirst",
    "cognitive_coherence",
    "pattern_seeking",
    "predictability",
    "recognition",
    "resonance",
    "expression",
    "curiosity",
)

# ego-mcp used `feel_desires` historically, then moved desire telemetry into `attune`.
# Dashboard readers need to understand both so historical and v1.0.0 data render together.
DESIRE_TELEMETRY_TOOL_NAMES: tuple[str, ...] = (
    "feel_desires",
    "attune",
)
