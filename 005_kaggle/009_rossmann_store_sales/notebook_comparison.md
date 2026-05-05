# ハイスコアノートブック vs 我々のモデル 比較分析

`rossmann-sales-emblayer-xg-lgb.ipynb` の手法と、我々が構築した v1〜v5 の手法を比較する。

---

## スコア概況

| モデル | valid RMSPE | Kaggle LB |
|---|---|---|
| 我々 v1 baseline | 0.13670 | 0.12846 |
| 我々 v2 店舗統計量 | 0.13310 | 0.12274 |
| 我々 v4 Optuna | 0.12674 | 0.12172 |
| ハイスコアノートブック | 不明 | 不明（top 1% 相当と推定）|

---

## 全体アーキテクチャの比較

| 項目 | ハイスコアノートブック | 我々のモデル |
|---|---|---|
| 使用モデル | Neural Network + XGBoost + LightGBM | LightGBM のみ |
| アンサンブル | XGBoost と LightGBM の 0.5:0.5 平均 | なし（LightGBM 単体）|
| NN の役割 | 埋め込みを XGBoost/LightGBM の特徴量として注入 | 使用しない |
| 外部データ | Google Trends（州別・全国）+ 気象データ + 州マッピング | 使用しない |
| CV 戦略 | **なし**（ラウンド数をハードコーディング） | 時系列 Hold-out（直近6週）|
| 目的変数変換 | `log1p(Sales)` | `log1p(Sales)` ✓ 同一 |
| 学習データフィルタ | Open=1 かつ Sales>0 のみ | Open=1 かつ Sales>0 のみ ✓ 同一 |

---

## 特徴量エンジニアリングの比較

### ✅ 共通している特徴量

| 特徴量 | 内容 |
|---|---|
| `Year`, `Month`, `Day`, `WeekOfYear` | 日付分解 |
| `DayOfWeek` | 曜日 |
| `Promo` | 当日プロモフラグ |
| `SchoolHoliday` | 学校休暇フラグ |
| `StateHoliday` | 祝日種別 |
| `StoreType`, `Assortment` | 店舗タイプ・品揃え |
| `CompetitionDistance` の対数変換 | 競合距離の log 変換 |
| Promo2 関連特徴量 | Promo2SinceYear/Week の活用 |

---

### ❌ ノートブックにあって我々にない特徴量

#### 1. 外部データ由来の特徴量

```
Google Trends データ（Googleで「Rossmann」が検索された頻度）:
  state_trend : 各州のGoogleトレンド値（週単位）
  DE_trend    : ドイツ全国のGoogleトレンド値（週単位）

気象データ（州別・日次）:
  Max/Mean/Min_TemperatureC  : 最高・平均・最低気温
  Max/Mean/Min_Humidity      : 最高・平均・最低湿度
  Max_Wind_SpeedKm_h         : 最高風速
  Mean_Wind_SpeedKm_h        : 平均風速
  CloudCover                 : 雲量
  Events                     : 天気イベント（霧・雨・雷など22種）

州マッピング:
  State                      : 店舗が属するドイツの州（12州をラベルエンコード）
```

> **解説**: Rossmann はドイツの薬局チェーンであり、州によって購買行動・祝日・気候が異なる。
> Google Trends はプロモーション効果の代理変数として有効であり、気象は来店動機に影響する。

---

#### 2. 競合店・Promo2 の経過時間特徴量（より精密な設計）

| ハイスコアの特徴量 | 内容 | 我々の対応特徴量 |
|---|---|---|
| `hasCompetitionmonths` | 競合店オープンからの経過月数（上限24ヶ月） | `CompetitionOpen`（上限なし）|
| `hasPromo2weeks` | Promo2 開始からの経過週数（上限25週） | `Promo2OpenWeeks`（上限なし）|
| `latest_promo2_months` | 直近 Promo2 サイクル開始からの経過月数（0〜3） | なし |

```python
# hasCompetitionmonths: 競合店の影響は一定期間（24ヶ月）で飽和すると仮定
hasCompetitionmonths = min(24, (Year - CompetitionOpenSinceYear) * 12 + (Month - CompetitionOpenSinceMonth))

# latest_promo2_months: Promo2 は「最初から何ヶ月か」ではなく
#                       「今のサイクルで何ヶ月目か」が重要（毎年繰り返すため）
latest_promo2_months = (month_in_year - start_month_of_current_cycle) % cycle_length
```

> **解説**: 競合店の影響は無限に続くわけではなく、ある程度すると市場が安定する。
> Promo2 は繰り返しサイクルなので「累積経過週数」より「今のサイクルで何週目か」の方が有用。

---

#### 3. Entity Embedding Neural Network（最大の差別化要素）

```
通常のカテゴリ変数の扱い:
  Store ID（1115種）→ LightGBM のカテゴリ特徴として使う

ハイスコアのアプローチ:
  Store ID → Embedding（10次元ベクトル）← NN が学習
  DayOfWeek → Embedding（6次元ベクトル）
  month → Embedding（6次元ベクトル）
  ... (17カテゴリ、合計77次元)
  → この埋め込みベクトルを XGBoost/LightGBM の追加特徴量として使う
```

```python
# NN の埋め込み重みを抽出して XGBoost/LightGBM に注入
for col in emb_list:
    x_train = x_train.merge(we[col].reset_index(), how='left', on=[col])
    x_test  = x_test.merge(we[col].reset_index(),  how='left', on=[col])
```

**効果**: NN が学習した「Store 817 と Store 562 は類似した売上パターン」という情報を、
LightGBM の決定木が活用できるようになる。Store ID をそのまま使うより遥かに情報豊富。

---

#### 4. 特徴量の正規化

```python
# 競合距離: 対数変換 + 10で割って [0, ~1] に正規化（NN 向け）
CompetitionDistance = log(CompetitionDistance + 1) / 10

# 年: 2013基準の相対値（0, 1, 2）
year = year - 2013

# 気温: [-1, 1] 付近に正規化
temperature = (temperature - 10) / 30
```

> **解説**: NN は特徴量のスケールに敏感なため、適切な正規化が学習安定性に影響する。
> 木モデル（LightGBM, XGBoost）はスケール不変なので我々は正規化不要。

---

#### 5. Open=NaN の扱い方（差異）

| | ハイスコアノートブック | 我々のモデル |
|---|---|---|
| `test['Open']` の NaN 補完 | **0（閉店とみなす）** | **1（開店とみなす）** |
| 根拠 | Open が不明な店は閉店の可能性 | EDA で11件の該当店舗（Store 622）を調査 |

> **補足**: どちらが正解かはデータ次第。EDA での調査結果（Store 622 の通常営業パターン）を
> 根拠に 1 を選んだ我々の判断は合理的。

---

### ❌ 我々にあってノートブックにない特徴量

| 特徴量 | 内容 | 効果 |
|---|---|---|
| `store_mean`, `store_median`, `store_std` | 店舗別の売上統計量 | ✅ v2 で大幅改善 |
| `store_dow_mean` | 店舗 × 曜日の平均売上 | ✅ 重要度 2位 |
| `store_month_mean` | 店舗 × 月の平均売上 | ✅ 有効 |
| `store_promo_mean` | 店舗 × プロモの平均売上 | ✅ 重要度 1位 |
| Optuna による探索 | 最適ハイパーパラメータ | ✅ v4 で大幅改善 |

---

## CV 戦略の詳細比較

### ハイスコアノートブック

```python
# バリデーションなしでフル訓練データを使用（num_round をハードコーディング）
num_round = 2528   # XGBoost
num_iterations = 15148  # LightGBM

# 事前に early stopping で決めたベストラウンドをそのまま使用
```

**リスク**: ラウンド数が最適かどうか不明。過学習の検出ができない。  
**メリット**: 全データで学習するため、汎化性能が向上する場合がある。

### 我々のモデル

```python
# 時系列 Hold-out（直近6週 = テスト期間と同じ長さ）
VAL_START = pd.Timestamp("2015-06-20")
tr_fold  = train_open[train_open["Date"] <  VAL_START]   # 学習
val_fold = train_open[train_open["Date"] >= VAL_START]   # 検証

# Early Stopping で最適ラウンド数を自動決定
lgb.early_stopping(stopping_rounds=300)
```

**メリット**: 過学習を検出でき、汎化性能の指標として機能する。  
**リスク**: 6週間分のデータを検証に使うため、学習データがやや少なくなる。

> **結論**: 時系列データでは我々の Hold-out 戦略の方が理論的に正しい。
> ただしノートブックのように全データ学習 + 固定ラウンドも実用的な選択肢。

---

## LightGBM パラメータの比較

| パラメータ | ハイスコアノートブック | 我々の v4（Optuna 最適値）|
|---|---|---|
| `learning_rate` | 0.02 | 0.0257 |
| `max_depth` | 8 | 10 |
| `num_leaves` | 800 | 359 |
| `min_data_in_leaf` | 20 | 146 |
| `bagging_fraction` | 0.7 | 0.901 |
| `bagging_freq` | 5 | 5 |
| `feature_fraction` | 0.5 | 0.562 |
| `lambda_l2` | 記載なし | 5.27（強い正則化）|
| `num_iterations` | **15148** | 4960（5000 上限内）|

> **注目**: ハイスコアノートブックは `num_iterations=15148` と非常に多い。
> 我々の v4 は 5000 が上限で 4960 に達しており、更なるイテレーションの余地がある。

---

## 改善のためのアクションプラン

ハイスコアノートブックとの比較から、我々が取り組める改善を優先度順に示す。

### 優先度 高

| # | 施策 | 根拠 |
|---|---|---|
| 1 | **XGBoost を追加してアンサンブル** | ノートブックも 0.5:0.5 ブレンドで精度向上 |
| 2 | **`latest_promo2_months` の追加** | 累積週数より「今のサイクルの何ヶ月目か」の方が有用 |
| 3 | **`hasCompetitionmonths` の上限設定（24ヶ月）** | 競合店の影響は飽和するという実ビジネス的知見 |

### 優先度 中

| # | 施策 | 根拠 |
|---|---|---|
| 4 | **州データ (`store_states.csv`) の追加** | 州別の購買行動・祝日の差異を捉える |
| 5 | **Google Trends データの追加** | プロモーション効果の代理変数として有効 |
| 6 | **num_boost_round をさらに増やして再探索** | ノートブックは 15,148 round、我々はまだ上限 |

### 優先度 低（難易度が高い）

| # | 施策 | 根拠 |
|---|---|---|
| 7 | **Entity Embedding NN の実装** | 最大の差別化要素だが Keras の知識が必要 |
| 8 | **気象データの追加** | 外部データの収集・前処理が複雑 |

---

## まとめ

```
ハイスコアノートブックの最大の差別化要素:
  1. Entity Embedding NN → 埋め込みを XGBoost/LightGBM に注入
  2. Google Trends + 気象データ（外部データ）
  3. Promo2 の「今のサイクルの何ヶ月目か」という特徴量設計

我々のモデルの強み:
  1. Optuna による体系的なハイパーパラメータ最適化
  2. 時系列 Hold-out による正しい CV 戦略
  3. 店舗別統計量（store_promo_mean が重要度 1位）

最も効果が高いと考えられる次の一手:
  → XGBoost アンサンブル + latest_promo2_months の追加
  （外部データなしで実装可能、かつ差が大きい要素）
```
