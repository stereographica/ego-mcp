# 500: ユニットテスト

## 目的
主要コンポーネントの単体テストを整備し、機能の正確性と退行耐性を確保する。

## 前提
- 100〜105 の実装が完了していること

## 参照
- `design/tasks.md` の T-500

## 仕様

### T-500-1: Embedding プロバイダーのテスト
- Gemini / OpenAI のモックを用意
- バッチ Embedding の動作を検証
- エラー時のリトライを検証

### T-500-2: MemoryStore のテスト
- `save` / `search` / `recall` / `list_recent` / `auto_link` を検証
- 感情トレース付き保存・検索を検証

### T-500-3: DesireEngine のテスト
- `compute_levels` / `satisfy` / `boost` / `format_summary` を検証
- シグモイド計算の期待値を検証（時間経過を固定して確認）

### T-500-4: スキャフォールドのテスト
- 各テンプレートが `data + scaffold` 形式を満たすことを検証
- `companion_name` の置換を検証

## 完了確認
```bash
cd ego-mcp
uv run pytest tests/test_embedding.py -v
uv run pytest tests/test_memory.py -v
uv run pytest tests/test_desire.py -v
uv run pytest tests/test_scaffolds.py -v
```
