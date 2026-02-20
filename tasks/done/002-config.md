# 002: 設定管理（config.py）

## 目的
環境変数から設定を読み込む `EgoConfig` を実装する。

## 仕様

`src/ego_mcp/config.py` に `EgoConfig` dataclass（frozen=True）を作成:

| 環境変数 | フィールド | デフォルト |
|---|---|---|
| `EGO_MCP_EMBEDDING_PROVIDER` | `embedding_provider` | `"gemini"` |
| `EGO_MCP_EMBEDDING_MODEL` | `embedding_model` | provider依存（gemini: `gemini-embedding-001`, openai: `text-embedding-3-small`） |
| `GEMINI_API_KEY` or `OPENAI_API_KEY` | `api_key` | **必須**（未設定は ValueError） |
| `EGO_MCP_DATA_DIR` | `data_dir: Path` | `~/.ego-mcp/data` |
| `EGO_MCP_COMPANION_NAME` | `companion_name` | `"Master"` |

- `EgoConfig.from_env()` クラスメソッドで構築
- provider が `"gemini"` / `"openai"` 以外なら ValueError
- API キー未設定時のエラーメッセージに取得先 URL を含める

## テスト（`tests/test_config.py`）
- Gemini デフォルト設定で正常構築
- OpenAI 明示指定で正常構築
- API キー未設定で ValueError
- 不正 provider で ValueError
- frozen なので再代入不可

## 完了確認
```bash
pytest tests/test_config.py -v  # 全 pass
```
