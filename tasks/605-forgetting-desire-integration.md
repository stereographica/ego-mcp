# 605: 忘却と欲求の連動

## 目的
忘却メカニズムを記憶・欲求・内省の 3 システムに横断的に統合する。忘れかけている問いが関連記憶の保存で再浮上する経路と、`cognitive_coherence` 欲求を通じて「何か引っかかる」感覚を生む経路の 2 つを実装する。

## 前提
- 603（未解決の問いの忘却）が完了していること
- 601（remember リンク記憶可視化）が完了していること
- `_derive_desire_modulation` が `server.py` に存在すること

## 参照
- `design/phase3-enhancements.md` §6

## タスク

### T-605-1: 経路 1 — 関連記憶の保存による再活性化
対象ファイル: `src/ego_mcp/server.py`

`_handle_remember` の末尾で、保存された記憶の content と Dormant/Fading 状態の問いとのセマンティック類似度を比較する。閾値（0.4）を超えた問いを「再浮上した問い」としてレスポンスに含める。

実装方針:
- `SelfModelStore` から Dormant/Fading な問い（`salience <= 0.3` かつ未解決）を取得
- `MemoryStore` の embedding 関数を使って問いのテキストと保存された記憶の content の類似度を計算
- 閾値を超えた問いがあれば、レスポンスの `Most related:` セクションの後に表示:

```
💭 This triggered a forgotten question: "What's the optimal heartbeat interval?"
   (dormant for 12 days, importance: 4)
```

- 該当する問いの salience を再ブーストする処理は**行わない**（問いを再び Active にするかは LLM が `update_self` で判断する）

パフォーマンス考慮:
- Dormant/Fading な問いが 0 件なら embedding 計算をスキップ
- 問いの数が多い場合は上位 10 件に制限

### T-605-2: 経路 2 — `cognitive_coherence` 欲求のブースト
対象ファイル: `src/ego_mcp/server.py`

`_derive_desire_modulation` に以下のロジックを追加する:

- `SelfModelStore` から Fading 状態（`0.1 < salience <= 0.3`）かつ importance >= 4 の問いを取得
- 該当する問いがある場合、`cognitive_coherence` に `min(0.12, count * 0.04)` のブーストを加える

### T-605-3: `feel_desires` のスキャフォールドに「引っかかり」表現を追加
対象ファイル: `src/ego_mcp/server.py`

`_handle_feel_desires` で `cognitive_coherence` が高い（>= 0.6）かつ Fading な問いが存在する場合、スキャフォールドに以下のニュアンスを追加する:

```
Something feels unresolved. You can't quite name it, but there's a nagging feeling.
Consider running introspect to see if anything surfaces.
```

具体的な問いの内容はここでは出さない（段階的開示の原則）。`introspect` を呼んだ時に初めて Resurfacing セクションに表示される。

### T-605-4: `introspect` の Resurfacing セクションの表示条件を追加
対象ファイル: `src/ego_mcp/server.py`

603 で実装した Resurfacing セクションに、表示条件の制御を追加する:

Resurfacing セクションは以下の**いずれか**の場合に表示する:
1. `cognitive_coherence` 欲求が高い（>= 0.6）
2. T-605-1 で関連記憶がトリガーされた直後（フラグ管理は不要。Fading な問いが存在すること自体が条件）

条件を満たさない場合、Resurfacing セクションは省略する。これにより「常に表示される」のではなく「ふとした瞬間に思い出す」体験になる。

## テスト
- [ ] remember 時に dormant な問いと類似した内容を保存した場合、レスポンスに再浮上表示が含まれることを確認
- [ ] remember 時に dormant な問いがない場合、再浮上表示が含まれないことを確認
- [ ] Fading かつ importance >= 4 の問いがある場合、`_derive_desire_modulation` が `cognitive_coherence` にブーストを返すことを確認
- [ ] `cognitive_coherence` が高い時に `feel_desires` のスキャフォールドに「引っかかり」表現が含まれることを確認
- [ ] introspect で Resurfacing セクションの表示条件が正しく動作することを確認

## 完了確認
```bash
cd ego-mcp
uv run pytest tests/test_self_model.py -v
uv run pytest tests/test_integration.py -k "remember or introspect or feel_desires" -v
uv run mypy src/ego_mcp/server.py
```
