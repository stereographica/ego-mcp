# 601: remember リンク記憶の可視化

## 目的
`remember` 実行時、リンクした記憶のうち類似度が高い上位 3 件を内容の断片とともに返すようにする。これにより LLM が記憶間の連想を展開できるようになる。

## 前提
- `MemoryStore.save_with_auto_link` が動作していること
- `scaffolds.py` の `compose_response` が利用可能であること

## 参照
- `design/phase3-enhancements.md` §2

## タスク

### T-601-1: `save_with_auto_link` の返り値を拡張
対象ファイル: `src/ego_mcp/memory.py`

現行の返り値 `tuple[Memory, int]` を `tuple[Memory, int, list[MemorySearchResult]]` に拡張する。3番目の要素は、リンク作成時に使った `MemorySearchResult` のリスト（自分自身を除く、distance 閾値を通過したもの）。

呼び出し元の `_handle_remember` に影響するため、返り値の展開を修正する。

### T-601-2: `_handle_remember` のレスポンスを改修
対象ファイル: `src/ego_mcp/server.py`

リンクした記憶の上位 3 件を similarity（`1.0 - distance`）順で表示する。

表示ルール:
- content は 70 文字で truncate（既存の `_truncate_for_quote` を流用）
- timestamp は相対時間で表示（`2d ago`, `1w ago` 等）
- 上限 3 件
- リンク 0 件の場合は `"No similar memories found yet."` を返す

レスポンス末尾にスキャフォールドの問いかけを添える:
```
Do any of these connections surprise you? Is there a pattern forming?
```

### T-601-3: 相対時間フォーマット関数を実装
対象ファイル: `src/ego_mcp/server.py`（または適切なユーティリティモジュール）

ISO 8601 タイムスタンプから相対時間文字列を生成する `_relative_time(timestamp: str, now: datetime | None = None) -> str` を実装する。

出力例: `"2d ago"`, `"1w ago"`, `"3mo ago"`, `"1y ago"`

この関数は 602（recall 結果表示改善）でも使用する。

## テスト
- [ ] `save_with_auto_link` の返り値が 3 要素タプルであることを確認
- [ ] リンクあり時のレスポンスに `"Most related:"` と similarity が含まれることを確認
- [ ] リンクなし時のレスポンスに `"No similar memories found yet."` が含まれることを確認
- [ ] `_relative_time` のユニットテスト（各時間帯の出力を確認）

## 完了確認
```bash
cd ego-mcp
uv run pytest tests/test_memory.py -k "auto_link" -v
uv run pytest tests/test_integration.py -k "remember" -v
uv run mypy src/ego_mcp/server.py
```
