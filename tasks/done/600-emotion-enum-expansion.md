# 600: Emotion enum 拡張

## 目的
valence-arousal 空間上のネガティブ象限の表現力が不足しているため、感情の種類を拡張する。後続の感情トレンド分析（604）やフィルタ強化（602）の土台となる。

## 前提
- `types.py` に `Emotion(str, Enum)` が定義済みであること
- `memory.py` に `EMOTION_BOOST_MAP` が定義済みであること

## 参照
- `design/phase3-enhancements.md` §1

## タスク

### T-600-1: `Emotion` enum に 4 値を追加
対象ファイル: `src/ego_mcp/types.py`

以下の 4 値を追加する:

| 値 | 文字列 | 概要 |
|---|---|---|
| `MELANCHOLY` | `"melancholy"` | 静かな物悲しさ。SAD より内省的 |
| `ANXIOUS` | `"anxious"` | 漠然とした不安。対象が不明確 |
| `CONTENTMENT` | `"contentment"` | 穏やかな満足。HAPPY より静的 |
| `FRUSTRATED` | `"frustrated"` | 明確な対象への苛立ち |

### T-600-2: `EMOTION_BOOST_MAP` に 4 エントリを追加
対象ファイル: `src/ego_mcp/memory.py`

記憶の想起しやすさ（検索スコアブースト）を追加する。値は感情の鮮烈さに比例させる。

```python
"frustrated": 0.28,
"anxious": 0.22,
"melancholy": 0.18,
"contentment": 0.08,
```

`contentment` の boost が低いのは意図的。穏やかな満足は個別の記憶としては印象が薄いが、集計した時に価値が出る。

### T-600-3: `_derive_desire_modulation` に新 Emotion を含める
対象ファイル: `src/ego_mcp/server.py`

`_derive_desire_modulation` 内の emotion 判定ロジックに新しい Emotion を反映する:
- `frustrated` を `surprised`, `excited` と同列の高覚醒感情として扱い、`prediction_error` に含める
- `anxious` が直近記憶に多い場合、`cognitive_coherence` と `social_thirst` にブーストを加える

## テスト
- [ ] `tests/test_types.py` に新 Emotion 値の一致確認を追加
- [ ] `tests/test_memory.py` に新 Emotion の `EMOTION_BOOST_MAP` 存在確認を追加
- [ ] `tests/test_integration.py` に新 Emotion での `remember` → `recall` の E2E を追加

## 完了確認
```bash
cd ego-mcp
uv run mypy src/ego_mcp/types.py
uv run pytest tests/test_types.py -v
uv run pytest tests/test_memory.py -k "emotion_boost" -v
uv run pytest tests/test_integration.py -k "emotion" -v
```
