# 303: 連想展開（Association）（Phase 3）

## 目的
記憶グラフの明示リンク・暗黙リンクを辿る連想展開を実装し、想起候補を広げる。

## 前提
- `Memory` にリンク情報が保持されていること
- 類似検索のベース API があること

## 参照
- `design/tasks.md` の T-303
- `memory-mcp/src/memory_mcp/association.py`

## タスク
- [ ] `src/ego_mcp/association.py` を作成
- [ ] `AssociationEngine.spread(seed_ids, depth, top_k)` を実装
- [ ] 明示リンク（`linked_ids`）探索を実装
- [ ] 埋め込み類似度ベースの暗黙リンク拡張を実装
- [ ] 展開結果の重複排除とスコアリングを実装
- [ ] 将来の `recall` 統合を見据えたインターフェースを定義

## テスト
- [ ] `tests/test_association.py` を作成
  - seed から複数 hop の取得
  - depth 制限の確認
  - 重複排除の確認

## 完了確認
```bash
cd ego-mcp
uv run pytest tests/test_association.py -v
```

