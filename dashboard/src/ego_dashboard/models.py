from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DashboardEvent(BaseModel):
    ts: datetime
    event_type: str = "tool_call_completed"
    tool_name: str = "unknown"
    ok: bool = True
    duration_ms: int | None = None
    emotion_primary: str | None = None
    emotion_intensity: float | None = None
    numeric_metrics: dict[str, float] = Field(default_factory=dict)
    string_metrics: dict[str, str] = Field(default_factory=dict)
    params: dict[str, str | int | float | bool] = Field(default_factory=dict)
    private: bool = False
    message: str | None = None


class LogEvent(BaseModel):
    ts: datetime
    level: str = "INFO"
    logger: str = "ego_dashboard"
    message: str
    private: bool = False
