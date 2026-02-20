"""Tests for embedding providers."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import httpx
import pytest
import respx

from ego_mcp.config import EgoConfig
from ego_mcp.embedding import (
    GeminiEmbeddingProvider,
    OpenAIEmbeddingProvider,
    create_embedding_provider,
)


# --- Gemini Provider ---


class TestGeminiEmbeddingProvider:
    """Tests for GeminiEmbeddingProvider."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_single_text(self) -> None:
        route = respx.post(
            url__startswith="https://generativelanguage.googleapis.com/"
        ).respond(json={"embeddings": [{"values": [0.1, 0.2, 0.3]}]})

        provider = GeminiEmbeddingProvider(api_key="test-key")
        result = await provider.embed(["hello"])

        assert result == [[0.1, 0.2, 0.3]]
        assert route.called

    @respx.mock
    @pytest.mark.asyncio
    async def test_batch_embed(self) -> None:
        respx.post(
            url__startswith="https://generativelanguage.googleapis.com/"
        ).respond(
            json={
                "embeddings": [
                    {"values": [0.1, 0.2]},
                    {"values": [0.3, 0.4]},
                ]
            }
        )

        provider = GeminiEmbeddingProvider(api_key="test-key")
        result = await provider.embed(["hello", "world"])

        assert len(result) == 2
        assert result[0] == [0.1, 0.2]
        assert result[1] == [0.3, 0.4]

    @respx.mock
    @pytest.mark.asyncio
    async def test_429_retry(self) -> None:
        respx.post(
            url__startswith="https://generativelanguage.googleapis.com/"
        ).side_effect = [
            httpx.Response(429, json={"error": "rate limited"}),
            httpx.Response(200, json={"embeddings": [{"values": [0.5]}]}),
        ]

        provider = GeminiEmbeddingProvider(api_key="test-key")
        # Patch sleep to avoid actual waiting
        original_sleep = asyncio.sleep
        sleep_calls: list[float] = []

        async def mock_sleep(delay: float) -> None:
            sleep_calls.append(delay)

        asyncio.sleep = cast(Any, mock_sleep)
        try:
            result = await provider.embed(["hello"])
            assert result == [[0.5]]
            assert len(sleep_calls) == 1
            assert sleep_calls[0] == 1.0
        finally:
            asyncio.sleep = original_sleep


# --- OpenAI Provider ---


class TestOpenAIEmbeddingProvider:
    """Tests for OpenAIEmbeddingProvider."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_single_text(self) -> None:
        respx.post("https://api.openai.com/v1/embeddings").respond(
            json={"data": [{"index": 0, "embedding": [0.4, 0.5, 0.6]}]}
        )

        provider = OpenAIEmbeddingProvider(api_key="sk-test")
        result = await provider.embed(["hello"])

        assert result == [[0.4, 0.5, 0.6]]

    @respx.mock
    @pytest.mark.asyncio
    async def test_batch_embed_reorders_by_index(self) -> None:
        respx.post("https://api.openai.com/v1/embeddings").respond(
            json={
                "data": [
                    {"index": 1, "embedding": [0.3, 0.4]},
                    {"index": 0, "embedding": [0.1, 0.2]},
                ]
            }
        )

        provider = OpenAIEmbeddingProvider(api_key="sk-test")
        result = await provider.embed(["hello", "world"])

        assert result[0] == [0.1, 0.2]
        assert result[1] == [0.3, 0.4]

    @respx.mock
    @pytest.mark.asyncio
    async def test_429_retry(self) -> None:
        respx.post("https://api.openai.com/v1/embeddings").side_effect = [
            httpx.Response(429, json={"error": "rate limited"}),
            httpx.Response(429, json={"error": "rate limited"}),
            httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.9]}]}),
        ]

        provider = OpenAIEmbeddingProvider(api_key="sk-test")
        original_sleep = asyncio.sleep
        sleep_calls: list[float] = []

        async def mock_sleep(delay: float) -> None:
            sleep_calls.append(delay)

        asyncio.sleep = cast(Any, mock_sleep)
        try:
            result = await provider.embed(["hello"])
            assert result == [[0.9]]
            assert len(sleep_calls) == 2
        finally:
            asyncio.sleep = original_sleep


# --- Factory ---


class TestFactory:
    """Tests for create_embedding_provider."""

    def test_gemini(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        config = EgoConfig.from_env()
        provider = create_embedding_provider(config)
        assert isinstance(provider, GeminiEmbeddingProvider)

    def test_openai(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EGO_MCP_EMBEDDING_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        config = EgoConfig.from_env()
        provider = create_embedding_provider(config)
        assert isinstance(provider, OpenAIEmbeddingProvider)
