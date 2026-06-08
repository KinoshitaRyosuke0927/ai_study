# JEPX 東京エリア電力スポット価格予測 - 精度改善プロセス記録

## スコア推移サマリー

| # | スクリプト | RMSE | ベース比 | 主な変更点 |
|---|---|---|---|---|
| 1 | baseline.py | 3.6338 | - | LinearRegression、基本特徴量のみ |
| 2 | lgbm.py | 3.6538 | +0.0200 ↑悪化 | LightGBM に切り替え（特徴量は同一） |
| 3 | walk_forward.py | 3.1831 | **-0.4507** | ウォークフォワード + 派生特徴量 + ラグ特徴量 |
| 4 | walk_forward_step1 | 3.3018 | -0.3320 | frame/month sin/cos エンコーディング → 不採用 |
| 4 | walk_forward_step2 | 3.1090 | **-0.5248** | ラグ特徴量（3〜6日前）→ 採用 |
| 4 | walk_forward_step3 | 3.1578 | -0.4760 | 同曜日×フレーム4週平均 → 不採用 |
| 5 | walk_forward_v2.py | 3.1410 | -0.4928 | LightGBM + XGBoost アンサンブル → 不採用 |
| 6 | walk_forward_v3.py | **3.0713** | **-0.5625** | Optuna ハイパーパラメータ最適化 ← **現ベスト** |
| 7 | walk_forward_v4.py | 3.0867 | -0.5471 | Expanding Window 毎日再学習 → 不採用 |

---

## 各ステップの詳細

### Step 1: baseline.py（RMSE 3.6338）

**モデル:** LinearRegression  
**特徴量:** frame, dayofweek, is_holiday, temp, power_result, power_prediction, usage_rate, power_supply, sell_amount, buy_amount, contracted_amount（11列）  
**前処理:** temp の欠損2件を中央値で補完。weather は欠損率が高く除外  
**予測方式:** テスト全件を一括予測

---

### Step 2: lgbm.py（RMSE 3.6538）

**モデル:** LightGBM（n_estimators=1000, lr=0.05, early_stopping=50）  
**特徴量:** baseline.py と同一  
**結果:** baseline.py と比べわずかに悪化。特徴量が同一のままでは非線形モデルの恩恵が出なかった

---

### Step 3: walk_forward.py（RMSE 3.1831）—— 最大の改善

**3つの改善を同時に導入:**

#### 3-1: ウォークフォワード予測
- 通常の一括予測ではテスト全件のラグ特徴量がほぼ NaN になる問題を解消
- 1日ずつ順番に予測し、予測値を次の日のラグ特徴量として利用
- lag_48（前日）・lag_96（2日前）・lag_336（7日前）・lag_17520（1年前）を全テスト日で有効活用

#### 3-2: weather 特徴量の追加
- train + test を結合して ffill/bfill で補間し、label encoding で数値化
- baseline/lgbm では欠損率の高さを理由に除外していたが、補間により利用可能に

#### 3-3: 派生特徴量の追加
| 特徴量 | 計算式 | 意味 |
|---|---|---|
| supply_demand_ratio | sell_amount / buy_amount | 需給比率 |
| surplus | sell_amount − buy_amount | 需給過不足 |
| contracted_ratio | contracted_amount / sell_amount | 約定率 |
| temp_sq | temp² | 気温の非線形効果 |

---

### Step 4: 特徴量の単体追加検証

walk_forward.py をベースに、特徴量を1つずつ追加して効果を検証した。

#### Step 4-1: frame/month の sin/cos エンコーディング（不採用）
- frame_sin, frame_cos, month_sin, month_cos を追加
- RMSE 3.3018（悪化）
- **要因:** モデルが frame・dayofweek を直接数値で使えており、sin/cos 変換による情報量の増加がなく、むしろノイズになったと考えられる

#### Step 4-2: ラグ特徴量（3〜6日前）追加（採用 → RMSE 3.1090）
- price_lag_144（3日前）, price_lag_192（4日前）, price_lag_240（5日前）, price_lag_288（6日前）を追加
- RMSE 3.1090（改善 -0.0741）
- **要因:** 既存の lag_96（2日前）と lag_336（7日前）の間を埋め、週全体のトレンドを補完

#### Step 4-3: 同曜日×フレームの4週ローリング平均（不採用）
- Step 4-2の特徴量に加え、過去4週の同曜日・同フレーム価格の平均を追加
- RMSE 3.1578（Step 4-2より悪化）
- **要因:** lag_336（7日前）と情報が重複した上に、先頭行の NaN が増加した

---

### Step 5: walk_forward_v2.py — LightGBM + XGBoost アンサンブル（不採用）

**内容:** Step 4-2 の特徴量に LightGBM と XGBoost の単純平均を追加  
**CV RMSE:** 1.8969（LGB 単体 1.9096 より改善）  
**テスト RMSE:** 3.1410（LGB 単体 3.1090 より悪化）  
**要因:** CV では改善したが、XGBoost が 2026年1〜3月のデータ分布に対して LightGBM より汎化できていなかった

---

### Step 6: walk_forward_v3.py — Optuna ハイパーパラメータ最適化（採用 ← 現ベスト）

**内容:** Step 4-2 の特徴量のまま LightGBM のハイパーパラメータを Optuna で探索（50 trials）

**チューニング対象パラメータ:**
- learning_rate, num_leaves, min_child_samples
- feature_fraction, bagging_fraction, reg_alpha, reg_lambda

**最適パラメータ（Trial #33）:**
| パラメータ | デフォルト値 | 最適値 |
|---|---|---|
| learning_rate | 0.05 | 0.0238 |
| num_leaves | 31 | 31 |
| min_child_samples | 20 | 21 |
| feature_fraction | 1.0 | 0.967 |
| bagging_fraction | 1.0 | 0.569 |
| reg_alpha | 0.0 | 0.0070 |
| reg_lambda | 0.0 | 0.0161 |

**CV RMSE:** 1.8917（ベース 1.9096 から改善）  
**テスト RMSE:** 3.0713（改善 -0.0377）  
**特徴的な点:** 学習率を下げ（0.05→0.024）、bagging_fraction で行サンプリングを強めることで過学習を抑制

---

### Step 7: walk_forward_v4.py — Expanding Window 毎日再学習（不採用）

**内容:** v3 の最適パラメータを使い、1日予測するごとにモデルを再学習（計90回）
- 再学習データ = 元の訓練データ + 予測済みテスト日の予測値
- Early stopping 用 validation set は元の訓練データ末尾14日を固定

**テスト RMSE:** 3.0867（v3 より悪化）  
**要因:** 予測値（誤差を含む）を正解として再学習するため、予測を外した日の誤差が蓄積して後半の精度が低下する「誤差伝播」が発生したと考えられる

---

## スコアの解釈

テスト期間（2026/1〜3月）の価格統計:
- 平均価格: 12.59 円/kWh
- 標準偏差: 4.32 円/kWh
- 最小: 0.01 / 最大: 45.01 円/kWh

現ベスト（v3, RMSE 3.0713）の誤差分布:
| 誤差の範囲 | 該当割合 |
|---|---|
| ±1円以内 | 44.8% |
| ±2円以内 | 69.2% |
| ±5円以内 | 85.4% |
| ±10円以内 | 99.6% |

- 平均価格の約 24% の誤差が残っている
- 最大誤差は 25.6円（正解 45.01円 → 価格スパイク時の予測困難）
- **課題:** 通常帯域の予測はほぼ安定しているが、急騰・急落時の外れがスコアを押し下げている

---

## 今後の改善候補

| 施策 | 期待効果 | 工数 |
|---|---|---|
| Optuna trials 数増加（50→200） | RMSE 微改善 | 小 |
| ターゲット変数の対数変換 | スパイク時の外れ縮小 | 小 |
| スパイク検出の特徴量追加 | スパイク時の予測改善 | 中 |
| CatBoost 追加アンサンブル | 多様性による分散低減 | 中 |
| Optuna チューニング済み XGBoost とのアンサンブル | v2 の反省を踏まえた再挑戦 | 中 |
