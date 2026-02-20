"""Configuration management for ego-mcp."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


_DEFAULT_MODELS: dict[str, str] = {
    "gemini": "gemini-embedding-001",
    "openai": "text-embedding-3-small",
}

_API_KEY_ENV: dict[str, str] = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
}

_API_KEY_URLS: dict[str, str] = {
    "gemini": "https://aistudio.google.com/apikey",
    "openai": "https://platform.openai.com/api-keys",
}


@dataclass(frozen=True)
class EgoConfig:
    """Immutable configuration loaded from environment variables.

    Environment variables:
        EGO_MCP_EMBEDDING_PROVIDER: "gemini" or "openai" (default: "gemini")
        EGO_MCP_EMBEDDING_MODEL: Model name (default: provider-dependent)
        GEMINI_API_KEY / OPENAI_API_KEY: API key (required)
        EGO_MCP_DATA_DIR: Data directory (default: ~/.ego-mcp/data)
        EGO_MCP_COMPANION_NAME: Companion name (default: "Master")
        EGO_MCP_WORKSPACE_DIR: OpenClaw workspace root for Markdown sync (optional)
    """

    embedding_provider: str
    embedding_model: str
    api_key: str
    data_dir: Path
    companion_name: str
    workspace_dir: Path | None

    @classmethod
    def from_env(cls) -> EgoConfig:
        """Construct EgoConfig from environment variables."""
        provider = os.environ.get("EGO_MCP_EMBEDDING_PROVIDER", "gemini").lower()

        if provider not in ("gemini", "openai"):
            raise ValueError(
                f"Invalid embedding provider: '{provider}'. "
                "Must be 'gemini' or 'openai'."
            )

        model = os.environ.get(
            "EGO_MCP_EMBEDDING_MODEL",
            _DEFAULT_MODELS[provider],
        )

        api_key_env = _API_KEY_ENV[provider]
        api_key = os.environ.get(api_key_env, "")
        if not api_key:
            url = _API_KEY_URLS[provider]
            raise ValueError(f"{api_key_env} is not set. Get your API key at: {url}")

        data_dir_str = os.environ.get(
            "EGO_MCP_DATA_DIR",
            str(Path.home() / ".ego-mcp" / "data"),
        )
        data_dir = Path(data_dir_str)

        companion_name = os.environ.get("EGO_MCP_COMPANION_NAME", "Master")
        workspace_dir_raw = os.environ.get("EGO_MCP_WORKSPACE_DIR", "").strip()
        workspace_dir = Path(workspace_dir_raw) if workspace_dir_raw else None

        return cls(
            embedding_provider=provider,
            embedding_model=model,
            api_key=api_key,
            data_dir=data_dir,
            companion_name=companion_name,
            workspace_dir=workspace_dir,
        )
