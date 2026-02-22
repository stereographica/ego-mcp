# 604: emotion_trend バックエンドツール新設

## 目的
最近どんな感情が多かったか、変化の傾向を俯瞰できるバックエンドツールを新設する。3 層の時間窓（vivid / moderate / impressionistic）で解像度を逓減させ、人間の記憶特性を再現する。

## 前提
- 600（Emotion enum 拡張）が完了していること
- `MemoryStore.list_recent` が利用可能であること
- `calculate_time_decay` が `memory.py` に存在すること

## 参照
- `design/phase3-enhancements.md` §3

## タスク

### T-604-1: 加重感情カウント関数を実装
対象ファイル: `src/ego_mcp/memory.py`（または `src/ego_mcp/server.py` 内のヘルパー）

```python
def _count_emotions_weighted(memories: list[Memory]) -> dict[str, float]:
```

- primary 感情を 1.0、secondary 感情を各 0.4 の重みでカウント
- 返り値は `{"curious": 6.2, "happy": 4.8, "anxious": 2.4, ...}` の形式

### T-604-2: 月次印象語マッピング関数を実装
対象ファイル: `src/ego_mcp/server.py`

```python
def _valence_arousal_to_impression(avg_valence: float, avg_arousal: float) -> str:
```

valence と arousal の平均から「ぼやっとした印象語」を返す。マッピング:

| valence | arousal | 印象 |
|---|---|---|
| > 0.3 | > 0.5 | `"an energetic, fulfilling month"` |
| > 0.3 | <= 0.5 | `"a quietly content month"` |
| < -0.3 | > 0.5 | `"a turbulent, unsettled month"` |
| < -0.3 | <= 0.5 | `"a heavy, draining month"` |
| abs <= 0.3 | <= 0.3 | `"a numb, uneventful month"` |
| その他 | | `"a month of mixed feelings"` |

### T-604-3: 3 層時間窓のフォーマット関数を実装
対象ファイル: `src/ego_mcp/server.py`

3 つの時間窓それぞれに対応するフォーマット関数を実装する。

**Recent（vivid）— 直近 ~3 日:**
- 個別の感情イベントを列挙（最大 3 件）
- ピーク感情（intensity 最大）を必ず含める
- undercurrent（secondary 由来）を表示

**This week（moderate）— ~7 日:**
- 支配的感情の上位 2 件 + Undercurrent
- 感情の変化方向（shift）を矢印で表示
- 同一感情が 3 件以上連続するクラスタを検出・警告表示

**This month（impressionistic）— ~30 日:**
- `_valence_arousal_to_impression` による印象語
- **ピーク・エンドの法則**: intensity 最大の記憶（peak）と最新の記憶（end）だけ具体的に言及
- **fading タグ**: 該当期間の記憶の平均 `time_decay` が 0.5 未満、かつ直近 1 週間に同一感情が出現していない場合、`[fading]` を付与

### T-604-4: Graceful Degradation を実装
対象ファイル: `src/ego_mcp/server.py`

記憶件数に応じて出力を段階的に解放する:

| 記憶数 | 出力 |
|---|---|
| 0 件 | `"No emotional history yet."` + scaffold |
| 1〜4 件 | 感じた感情の列挙のみ + `"Too few data points for trends."` |
| 5〜14 件 | Recent 層のみ |
| 15〜29 件 | Recent + This week の 2 層 |
| 30 件以上 | 全 3 層 |

### T-604-5: ツール定義とハンドラを実装
対象ファイル: `src/ego_mcp/server.py`

`BACKEND_TOOLS` に以下を追加:
```python
Tool(
    name="emotion_trend",
    description="Analyze emotional patterns over time",
    inputSchema={"type": "object", "properties": {}, "required": []},
)
```

`_handle_emotion_trend` ハンドラを実装し、`_dispatch` に追加する。

### T-604-6: スキャフォールドを実装
対象ファイル: `src/ego_mcp/scaffolds.py`

```python
SCAFFOLD_EMOTION_TREND = (
    "What patterns do you notice? Any surprises?\n"
    "Are the undercurrents telling you something the surface emotions aren't?\n"
    "If something feels unresolved, consider running introspect."
)
```

### T-604-7: `introspect` から `emotion_trend` への誘導を追加
対象ファイル: `src/ego_mcp/scaffolds.py`

`SCAFFOLD_INTROSPECT` に以下の 1 行を追加:
```
Use emotion_trend for a deeper look at your emotional patterns.
```

## テスト
- [ ] `_count_emotions_weighted` が primary=1.0、secondary=0.4 でカウントすることを確認
- [ ] `_valence_arousal_to_impression` が各象限で正しい印象語を返すことを確認
- [ ] 記憶 0 件で graceful degradation メッセージが返ることを確認
- [ ] 記憶 5 件で Recent 層のみ返ることを確認
- [ ] 記憶 30 件以上で全 3 層が返ることを確認
- [ ] fading タグが条件を満たす場合に付与されることを確認
- [ ] ピーク・エンドの法則で intensity 最大の記憶が月次セクションに含まれることを確認

## 完了確認
```bash
cd ego-mcp
uv run pytest tests/test_integration.py -k "emotion_trend" -v
uv run mypy src/ego_mcp/server.py
```
