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
    monkeypatch.delenv("DASHBOARD_CORS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("EGO_MCP_LOG_DIR", raising=False)

    settings = load_settings()

    assert "http://localhost:4173" in settings.cors_allowed_origins
    assert settings.log_path == "/tmp/ego-mcp-*.log"
    assert settings.ingest_poll_seconds == 1.0


def test_load_settings_falls_back_to_ego_mcp_log_dir(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("DASHBOARD_LOG_PATH", raising=False)
    monkeypatch.setenv("EGO_MCP_LOG_DIR", "/var/log/ego-mcp")

    settings = load_settings()

    assert settings.log_path == "/var/log/ego-mcp/ego-mcp-*.log"


def test_load_settings_parses_cors_origins(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DASHBOARD_CORS_ALLOWED_ORIGINS",
        "http://localhost:4173, https://example.com  ,",
    )

    settings = load_settings()

    assert settings.cors_allowed_origins == (
        "http://localhost:4173",
        "https://example.com",
    )
