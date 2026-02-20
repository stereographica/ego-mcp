# 009: バックエンドツール8個の実装

## 目的
表面ツールのレスポンスから案内されて使われるバックエンドツールを実装する。

## 前提
- 008（表面ツール）完了済み

## 参照
- `design/tool-design.md`「バックエンドツール」テーブル

## 仕様

全ツールの description は **1行以内**（token節約のため）。

| ツール名 | description | 引数 | 処理 |
|---|---|---|---|
| `satisfy_desire` | "Mark a desire as satisfied" | name(str), quality(float=0.7) | DesireEngine.satisfy() → 更新後 level を返す |
| `consolidate` | "Run memory consolidation" | なし | 参考実装の ConsolidationEngine.run() を移植 |
| `link_memories` | "Link two memories" | source_id(str), target_id(str), link_type(str="related") | 双方向リンク作成 |
| `update_relationship` | "Update relationship model" | person(str), field(str), value(any) | JSON永続化 |
| `update_self` | "Update self model" | field(str), value(any) | JSON永続化 |
| `search_memories` | "Search memories with filters" | query(str), emotion_filter, category_filter, date_from, date_to | MemoryStore.search() |
| `get_episode` | "Get episode details" | episode_id(str) | episode の記憶一覧を返す |
| `create_episode` | "Create episode from memories" | memory_ids(list[str]), summary(str) | エピソード作成 → ID を返す |

- `consolidate`, `get_episode`, `create_episode` は参考実装 `embodied-claude/memory-mcp/src/memory_mcp/` の `consolidation.py`, `episode.py` を移植

## テスト
- satisfy_desire で level が低下
- link_memories で双方向リンクが張られる
- search_memories のフィルタが動作

## 完了確認
```bash
pytest tests/test_backend_tools.py -v  # 全 pass
```
