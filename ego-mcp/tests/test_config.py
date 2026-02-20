"""Tests for EgoConfig."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from ego_mcp.config import EgoConfig


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove ego-mcp related env vars before each test."""
    for key in [
        "EGO_MCP_EMBEDDING_PROVIDER",
        "EGO_MCP_EMBEDDING_MODEL",
        "GEMINI_API_KEY",
        "OPENAI_API_KEY",
        "EGO_MCP_DATA_DIR",
        "EGO_MCP_COMPANION_NAME",
        "EGO_MCP_WORKSPACE_DIR",
    ]:
        monkeypatch.delenv(key, raising=False)


class TestGeminiDefaults:
    """Gemini provider with default settings."""

    def test_default_provider_and_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
        config = EgoConfig.from_env()

        assert config.embedding_provider == "gemini"
        assert config.embedding_model == "gemini-embedding-001"
        assert config.api_key == "test-key-123"
        assert config.companion_name == "Master"
        assert config.data_dir == Path.home() / ".ego-mcp" / "data"
        assert config.workspace_dir is None


class TestOpenAIExplicit:
    """OpenAI provider with explicit settings."""

    def test_openai_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EGO_MCP_EMBEDDING_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-456")
        config = EgoConfig.from_env()

        assert config.embedding_provider == "openai"
        assert config.embedding_model == "text-embedding-3-small"
        assert config.api_key == "sk-test-456"

    def test_custom_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EGO_MCP_EMBEDDING_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-456")
        monkeypatch.setenv("EGO_MCP_EMBEDDING_MODEL", "text-embedding-3-large")
        config = EgoConfig.from_env()

        assert config.embedding_model == "text-embedding-3-large"


class TestValidation:
    """Validation error cases."""

    def test_missing_api_key_raises(self) -> None:
        with pytest.raises(ValueError, match="GEMINI_API_KEY is not set"):
            EgoConfig.from_env()

    def test_missing_openai_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EGO_MCP_EMBEDDING_PROVIDER", "openai")
        with pytest.raises(ValueError, match="OPENAI_API_KEY is not set"):
            EgoConfig.from_env()

    def test_invalid_provider_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EGO_MCP_EMBEDDING_PROVIDER", "invalid")
        with pytest.raises(ValueError, match="Invalid embedding provider"):
            EgoConfig.from_env()

    def test_error_includes_url(self) -> None:
        with pytest.raises(ValueError, match="aistudio.google.com"):
            EgoConfig.from_env()


class TestFrozen:
    """Config is immutable."""

    def test_frozen(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        config = EgoConfig.from_env()

        with pytest.raises(FrozenInstanceError):
            config.api_key = "new-key"  # type: ignore[misc]


class TestCustomSettings:
    """Custom data_dir and companion_name."""

    def test_custom_data_dir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setenv("EGO_MCP_DATA_DIR", "/tmp/ego-test")
        config = EgoConfig.from_env()

        assert config.data_dir == Path("/tmp/ego-test")

    def test_custom_companion_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setenv("EGO_MCP_COMPANION_NAME", "Senpai")
        config = EgoConfig.from_env()

        assert config.companion_name == "Senpai"

    def test_custom_workspace_dir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setenv("EGO_MCP_WORKSPACE_DIR", "/tmp/openclaw-workspace")
        config = EgoConfig.from_env()

        assert config.workspace_dir == Path("/tmp/openclaw-workspace")
