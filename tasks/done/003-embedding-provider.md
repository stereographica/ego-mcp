# 003: Embedding プロバイダー

## 目的
Gemini / OpenAI の Embedding API を抽象化し、ChromaDB に接続する。

## 前提
- 002 完了済み（`EgoConfig` が使える）

## 仕様

`src/ego_mcp/embedding.py`:

```python
# Protocol
class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

# Implementations
class GeminiEmbeddingProvider:  # batchEmbedContents endpoint
class OpenAIEmbeddingProvider:  # /v1/embeddings endpoint

# Factory
def create_embedding_provider(config: EgoConfig) -> EmbeddingProvider: ...

# ChromaDB integration
class EgoEmbeddingFunction(EmbeddingFunction):  # sync wrapper
```

- 両 provider とも `httpx.AsyncClient` を使用
- 429 レート制限時に exponential backoff リトライ（最大3回、delay: 1s, 2s, 4s）
- `EgoEmbeddingFunction` は ChromaDB の同期インターフェース（`__call__`）に合わせて `asyncio.run` でラップ

## テスト（`tests/test_embedding.py`）
- `respx` でHTTPモック。実APIは呼ばない
- 単一テキスト / バッチ embed が動作
- 429 リトライが動作
- `create_embedding_provider` が provider に応じた型を返す

## 完了確認
```bash
pytest tests/test_embedding.py -v  # 全 pass
```
