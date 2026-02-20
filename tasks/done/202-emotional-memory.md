# 202: 感情記憶拡張（Phase 2）

## 目的
記憶保存と想起で感情次元を扱えるようにし、感情に基づく検索精度を上げる。

## 前提
- `remember` / `recall` / `search_memories` が動作していること
- `Memory` / `EmotionalTrace` 型が既に定義済みであること

## 参照
- `design/tasks.md` の T-202

## タスク

### T-202-1: `remember` の感情トレース完全実装
- [ ] `secondary`, `intensity`, `valence`, `arousal`, `body_state` を受け取り保存
- [ ] ChromaDB metadata に `valence` / `arousal` を格納
- [ ] `Memory` 復元時に全フィールドを戻す

### T-202-2: `recall` に感情次元フィルタ追加
- [ ] `valence_range`（例: `[-1.0, -0.3]`）を inputSchema に追加
- [ ] `arousal_range` を inputSchema に追加
- [ ] `MemoryStore.search/recall` 側でレンジフィルタを適用
- [ ] レスポンス整形時の互換性を維持（既存 scaffold あり）

## テスト
- [ ] `tests/test_memory.py` に感情トレース保存ケースを追加
- [ ] `tests/test_memory.py` に `valence_range` / `arousal_range` 検索ケースを追加
- [ ] `tests/test_integration.py` に `remember -> recall` の感情フィルタ E2E を追加

## 完了確認
```bash
cd ego-mcp
uv run pytest tests/test_memory.py -k "valence or arousal or emotional" -v
uv run pytest tests/test_integration.py -k "remember and recall" -v
```

