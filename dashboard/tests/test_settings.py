from __future__ import annotations

from pytest import MonkeyPatch

from ego_dashboard.settings import DashboardSettings, load_settings


def test_use_external_store_requires_db_and_redis() -> None:
    assert DashboardSettings(database_url=None, redis_url=None).use_external_store is False
    assert (
        DashboardSettings(database_url="postgresql://a", redis_url=None).use_external_store is False
    )
    assert DashboardSettings(database_url=None, redis_url="redis://a").use_external_store is False
    assert (
        DashboardSettings(database_url="postgresql://a", redis_url="redis://a").use_external_store
        is True
    )


def test_load_settings_defaults(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("DASHBOARD_LOG_PATH", raising=False)
    monkeypatch.delenv("DASHBOARD_INGEST_POLL_SECONDS", raising=False)

    settings = load_settings()

    assert settings.log_path == "/tmp/ego-mcp/telemetry.jsonl"
    assert settings.ingest_poll_seconds == 1.0
