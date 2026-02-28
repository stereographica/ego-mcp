"""Public memory API.

This module re-exports the MemoryStore implementation and scoring helpers.
"""

from __future__ import annotations

from ego_mcp._memory_scoring import (
    EMOTION_BOOST_MAP,
    calculate_emotion_boost,
    calculate_final_score,
    calculate_importance_boost,
    calculate_time_decay,
    count_emotions_weighted,
)
from ego_mcp._memory_store import MemoryStore

__all__ = [
    "EMOTION_BOOST_MAP",
    "MemoryStore",
    "calculate_time_decay",
    "calculate_emotion_boost",
    "calculate_importance_boost",
    "calculate_final_score",
    "count_emotions_weighted",
]
