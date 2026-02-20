# 301: Consolidation（記憶統合）（Phase 3）

## 目的
記憶の replay と共起更新を定期実行できる `ConsolidationEngine` を整備する。

## 前提
- `MemoryStore` が記憶取得とリンク更新を提供していること
- バックエンドツール `consolidate` が呼び出し可能であること

## 参照
- `design/tasks.md` の T-301
- `memory-mcp/src/memory_mcp/consolidation.py`

## タスク
- [ ] 参考実装から `src/ego_mcp/consolidation.py` へ必要機能を移植
- [ ] `ConsolidationEngine.run(memory_store, window=...)` を実装
- [ ] replay 対象抽出ロジックを実装（時間窓ベース）
- [ ] co-activation 更新ロジックを実装
- [ ] Embedding プロバイダー差し替えを可能にする
- [ ] `consolidate` ツールの返却統計（件数）を整合させる

## テスト
- [ ] `tests/test_consolidation.py` を作成
  - replay 実行で共起 weight が増えること
  - 空データ時に安全に完了すること
- [ ] `tests/test_integration.py` に `consolidate` 呼び出し確認を追加/更新

## 完了確認
```bash
cd ego-mcp
uv run pytest tests/test_consolidation.py -v
uv run pytest tests/test_integration.py -k consolidate -v
```

