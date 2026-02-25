# 903: スキャフォールド改善とドキュメント更新

## 目的
`consolidate` のマージ候補提示スキャフォールドに `forget` への導線を追加し、`tool-reference.md` に `forget` ツールのリファレンスを追加する。

## 前提
- 902（`forget` ツール）が完了していること

## 参照
- `design/forget-tool-design.md` §E

## タスク

### T-903-1: `_handle_consolidate` のスキャフォールド変更
対象ファイル: `ego-mcp/src/ego_mcp/server.py`

`_handle_consolidate` のマージ候補表示末尾のテキストを変更する。

**現行:**
```
Review each pair with recall. If one is redundant, consider which to keep.
```

**変更後:**
```
Review each pair with recall. If one is redundant, use forget to remove it.
If both have value, consider which perspective to keep.
```

### T-903-2: `tool-reference.md` の更新
対象ファイル: `ego-mcp/docs/tool-reference.md`

Backend Tools セクションに `forget` ツールのリファレンスを追加する。既存の Backend Tools（`satisfy_desire`, `consolidate` 等）のフォーマットに合わせる。以下の項目を含める:

- Description
- When to call（`consolidate` でマージ候補が見つかった後、または誤って保存された記憶の削除時）
- inputSchema
- Response example（正常削除、ID 不存在の 2 パターン）

また、Tool Flow Summary セクションの `Memory Management` フローに `forget` を追加する:

```
Memory Management:
  recall → [link_memories] → [consolidate] → [forget] → [remember merged version]
```

Backend Tools テーブル（README.md にもある）のツール数が増えるため、README.md のツール数表記も確認し、必要に応じて更新する。

### T-903-3: テスト
対象ファイル: `ego-mcp/tests/test_server.py`（または既存のスキャフォールドテスト）

- `consolidate` でマージ候補がある場合のレスポンスに `"use forget to remove it"` が含まれること

## 完了確認
```bash
cd ego-mcp
GEMINI_API_KEY=test-key uv run pytest tests/test_server.py -k "consolidate" -v
uv run mypy src/ego_mcp/server.py
```
