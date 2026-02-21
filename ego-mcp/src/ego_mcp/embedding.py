"""Embedding providers for ego-mcp."""

from __future__ import annotations
# mypy: disable-error-code=import-not-found

import asyncio
from typing import Any, Protocol, runtime_checkable

import httpx

from ego_mcp.config import EgoConfig

Documents = list[str]
Embeddings = list[list[float]]


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol for embedding providers."""

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class GeminiEmbeddingProvider:
    """Google Gemini embedding provider using batchEmbedContents."""

    def __init__(self, api_key: str, model: str = "gemini-embedding-001") -> None:
        self._api_key = api_key
        self._model = model

    async def close(self) -> None:
        """No-op close hook for compatibility with provider protocol."""
        return

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts using Gemini batchEmbedContents endpoint."""
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"models/{self._model}:batchEmbedContents"
            f"?key={self._api_key}"
        )
        requests = [
            {"model": f"models/{self._model}", "content": {"parts": [{"text": t}]}}
            for t in texts
        ]
        payload = {"requests": requests}

        response = await self._request_with_retry(url, payload)
        return [e["values"] for e in response["embeddings"]]

    async def _request_with_retry(
        self, url: str, payload: dict[str, Any], max_retries: int = 3
    ) -> dict[str, Any]:
        """HTTP POST with exponential backoff on 429."""
        delays = [1.0, 2.0, 4.0]
        last_error: httpx.HTTPStatusError | None = None

        for attempt in range(max_retries + 1):
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=payload)
            try:
                resp.raise_for_status()
                return resp.json()  # type: ignore[no-any-return]
            except httpx.HTTPStatusError as e:
                if resp.status_code == 429 and attempt < max_retries:
                    last_error = e
                    await asyncio.sleep(delays[attempt])
                    continue
                raise

        assert last_error is not None
        raise last_error  # pragma: no cover


class OpenAIEmbeddingProvider:
    """OpenAI embedding provider using /v1/embeddings endpoint."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        self._api_key = api_key
        self._model = model

    async def close(self) -> None:
        """No-op close hook for compatibility with provider protocol."""
        return

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts using OpenAI embeddings endpoint."""
        url = "https://api.openai.com/v1/embeddings"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        payload = {"model": self._model, "input": texts}

        response = await self._request_with_retry(url, payload, headers)
        sorted_data = sorted(response["data"], key=lambda x: x["index"])
        return [d["embedding"] for d in sorted_data]

    async def _request_with_retry(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """HTTP POST with exponential backoff on 429."""
        delays = [1.0, 2.0, 4.0]
        last_error: httpx.HTTPStatusError | None = None

        for attempt in range(max_retries + 1):
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
            try:
                resp.raise_for_status()
                return resp.json()  # type: ignore[no-any-return]
            except httpx.HTTPStatusError as e:
                if resp.status_code == 429 and attempt < max_retries:
                    last_error = e
                    await asyncio.sleep(delays[attempt])
                    continue
                raise

        assert last_error is not None
        raise last_error  # pragma: no cover


def create_embedding_provider(config: EgoConfig) -> EmbeddingProvider:
    """Factory: create the appropriate embedding provider from config."""
    if config.embedding_provider == "gemini":
        return GeminiEmbeddingProvider(config.api_key, config.embedding_model)
    elif config.embedding_provider == "openai":
        return OpenAIEmbeddingProvider(config.api_key, config.embedding_model)
    else:
        raise ValueError(f"Unknown provider: {config.embedding_provider}")


class EgoEmbeddingFunction:
    """ChromaDB-compatible sync wrapper around an async EmbeddingProvider."""

    def __init__(self, provider: EmbeddingProvider) -> None:
        self._provider = provider

    def name(self) -> str:
        """Return embedding function name for ChromaDB compatibility."""
        return "ego_embedding"

    def get_config(self) -> dict[str, str]:
        """Return serializable config for ChromaDB compatibility."""
        return {"name": self.name()}

    def is_legacy(self) -> bool:
        """Use legacy embedding-function config path for compatibility."""
        return True

    def embed_query(self, input: Documents) -> Embeddings:
        """ChromaDB query embedding hook."""
        return self.__call__(input)

    def __call__(self, input: Documents) -> Embeddings:
        """Synchronous embedding call for ChromaDB."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            # Already in an async context — run in a new thread
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self._provider.embed(list(input)))
                return future.result()
        else:
            return asyncio.run(self._provider.embed(list(input)))
