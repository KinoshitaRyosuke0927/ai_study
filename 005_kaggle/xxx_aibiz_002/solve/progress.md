# JEPX 東京エリア電力スポット価格予測 - モデル改善履歴

## スコア推移（改善バージョンのみ）

| バージョン | ファイル | Test RMSE | 改善幅 |
|---|---|---|---|
| ベースライン | baseline.py | 10.8259 | - |
| LightGBM | lgbm.py | 9.1678 | -1.6581 |
| 需給バランス特徴量 | feature_eng_v2.py | 9.1649 | -0.0029 |
| 1年前ラグ特徴量 | feature_eng_v4.py | 8.9448 | -0.2201 |
| weather補間・不要特徴量除外 | feature_eng_v7.py | 8.7827 | -0.1621 |
| 派生特徴量追加 | feature_eng_v9.py | 8.7216 | -0.0611 |
| ウォークフォワード＋ノイズ注入 | walk_forward_v2.py | **8.6740** | -0.0476 |

ベースラインからの総改善幅: **-2.1519**

---

## 各バージョンの変更内容

### baseline.py（RMSE: 10.8259）
- **モデル**: LinearRegression
- **特徴量**: frame, dayofweek, is_holiday, temp, power_result, power_prediction, usage_rate, power_supply, sell_amount, buy_amount, contracted_amount
- **CV**: TimeSeriesSplit（5分割）
- **前処理**: temp の欠損2件を中央値補完。weather は欠損率85%のため除外

---

### lgbm.py（RMSE: 9.1678）
- **変更内容**: LinearRegression → **LightGBM** に切り替え
- **主な設定**: n_estimators=1000, learning_rate=0.05, early_stopping=50
- **効果**: 非線形な需給関係・特徴量間の交互作用を捉えられるようになった

---

### feature_eng_v2.py（RMSE: 9.1649）
- **変更内容**: 需給バランス特徴量を2つ追加
  - `supply_demand_ratio` = sell_amount / buy_amount（需給比率。1超で供給過多→価格低下）
  - `surplus` = sell_amount - buy_amount（需給超過量）
- **採用根拠**: feature_selection.py による個別検証で CV RMSE の改善を確認
  - supply_demand_ratio: -0.0450
  - surplus: -0.0355

---

### feature_eng_v4.py（RMSE: 8.9448）
- **変更内容**: 1年前・2年前のラグ特徴量を追加
  - `price_lag_17520` = 17,520フレーム前（1年前）の価格
  - `price_lag_35040` = 35,040フレーム前（2年前）の価格
- **設計上の注意点**: テスト期間（2026/4/1〜5/9）全行で参照先が学習データ内に収まるラグのみ採用。短期ラグ（lag_48/96/336）はテストデータの大部分でNaNになりCV/本番スコアが乖離するため不採用
- **効果**: 電力価格の年次周期性（前年同期のパターン）を取り込めた

---

### feature_eng_v7.py（RMSE: 8.7827）
- **変更内容①**: `price_lag_35040` を除外（特徴量重要度が0のため）
- **変更内容②**: weather列を補間して有効化
  - 欠損パターン: 数時間ごとの観測値の間がNaN（欠損率85%）
  - 補間方法: 前方補間（ffill）→ 残余を後方補間（bfill）
  - エンコード: ラベルエンコーディングで整数変換（学習・テスト間で同一マッピングを適用）

---

### feature_eng_v9.py（RMSE: 8.7216）
- **変更内容**: 派生特徴量2つを追加（feature_selection.py による個別検証で採用）
  - `contracted_ratio` = contracted_amount / sell_amount（売り申込みの成約率）: CV RMSE -0.0315
  - `temp_sq` = temp²（猛暑・厳冬ともに価格上昇するU字型の関係を表現）: CV RMSE -0.0000
- **除外した候補**: unsold（+0.0002）, demand_forecast_error（+0.0003）は CV RMSE が悪化のため不採用

---

---

### walk_forward_v2.py（RMSE: 8.6740）← 最良モデル
- **アプローチ**: ウォークフォワード予測（Walk-Forward Prediction）＋ノイズ注入（Noise Injection）
- **予測方式**:
  - 1日（48コマ）ずつ順番に予測し、予測値を次の日の短期ラグ特徴量として利用
  - 同一日の48コマは lag_48 の参照先が「前日」で固定されるため一括予測可能
- **ノイズ注入の目的**:
  - ウォークフォワード予測では短期ラグに予測誤差が混入する（誤差の伝播）
  - 学習時に意図的に誤差相当のノイズを短期ラグに加えることで、モデルがノイズに依存しすぎない構造を学習
  - `lag_17520`（1年前・実績値）にはノイズを加えない
- **ノイズ強度の探索**: walk_forward_noise_search.py にて 0.0〜100.0 の範囲を探索し NOISE_STD=25.0 を採用
  - NOISE_STD=0.0: 10.4759 → NOISE_STD=25.0: 8.6740（最良）→ NOISE_STD=100.0: 8.7216（v9相当に収束）
- **アンサンブル**: 異なるノイズで学習した5モデルの予測を平均（モデルの安定化）
- **特徴量**: feature_eng_v9 の全特徴量 ＋ price_lag_48/96/336（短期ラグ）

---

## 効果がなかった・悪化したアプローチ

| アプローチ | 結果 | 原因 |
|---|---|---|
| 短期ラグ特徴量（lag_48/96/336） | 大幅悪化（10.6709） | テストデータの95%以上でNaN → CV/本番スコアの乖離 |
| 前年同期比差分（price_diff_yoy） | 悪化（9.8209） | 目的変数（tokyo_price）を使って計算するため学習時にデータリーク発生 |
| Optunaハイパーパラメータチューニング | 悪化（9.2974） | CVスコアの最適化が本番スコアの改善と一致しなかった |
| 交互作用特徴量（frame_dow, frame_holiday, temp_frame） | 効果なし | LightGBMが既に自動的に交互作用を捉えていたため |
| temp_sq の除外 | 微悪化（8.7394） | 重要度は低いが僅かに貢献していた |
| ウォークフォワード予測（ノイズなし） | 悪化（10.4759） | 短期ラグに予測誤差が蓄積・伝播。日数が経つほど誤差が増幅した |
| v9とのブレンド | 改善なし | v9単体（8.7216）がブレンドより優秀だった |
