# 住宅販売価格予測モデル 拡張版ガイド

`house_price_ex.py` で行っている手法を、「なぜその手法を使うのか」という思考の流れに沿って解説した学習教材です。  
`house_price.py`（2特徴量モデル）の改善版として、より多くのデータを活用して精度を高めています。

---

## 全体の流れ

```
① 欠損値の処理
   → データに穴が開いたままだと学習できない。「なぜ欠損しているか」を考えて補完する
    ↓
② 特徴量エンジニアリング
   → 既存の列を加工・組み合わせて「モデルが読み取りやすい情報」に変換する
    ↓
③ カテゴリ変数のエンコード
   → 文字列データ（地区名・品質ランクなど）を数値に変換する
    ↓
④ ハイパーパラメータチューニング
   → 各モデルのパラメータを自動で最適化する
    ↓
⑤ アンサンブル（VotingRegressor）
   → 複数のモデルの予測を平均して最終予測とする
```

---

## ステップ1: 欠損値の処理

### 問題：欠損値をどう扱うか

機械学習モデルの多くは `NaN`（欠損値）を直接扱えない。  
欠損値を補完する方法はいくつかあるが、**なぜ欠損しているか**によって正しい補完方法が変わる。

### 考え方：欠損の「意味」を読み取る

```
ガレージがない家 → GarageArea（ガレージ面積）が NaN
  → 「ガレージがないから面積がない」 → 0 で補完するのが正しい

電気設備の種類（Electrical）が稀に NaN
  → 「記録漏れや例外ケース」 → 最も多い値（最頻値）で補完するのが妥当
```

欠損値を一律に処理するのではなく、列ごとに意味を考えることが重要。

### 実装：2段階の補完

```python
# 「設備なし」を意味する列 → 0 で補完
ZERO_FILL_COLS = [
    "GarageArea", "GarageCars", "GarageYrBlt",
    "BsmtFinSF1", "BsmtFinSF2", "BsmtUnfSF", "TotalBsmtSF",
    "BsmtFullBath", "BsmtHalfBath",
    "MasVnrArea",
]

def fill_missing(df, num_medians=None, cat_modes=None):
    # ① 設備なしを意味する列は 0 で補完
    for col in ZERO_FILL_COLS:
        if col in df.columns:
            df[col] = df[col].fillna(0)
    # ② それ以外の数値列は train の中央値で補完
    if num_medians is None:
        num_medians = df[num_cols].median()      # train で計算
    df[num_cols] = df[num_cols].fillna(num_medians)
    # ③ カテゴリ列は train の最頻値で補完
    if cat_modes is None:
        cat_modes = df[cat_cols].mode().iloc[0]  # train で計算
    ...
```

### なぜ「train の統計値」で test を補完するのか（データリーク防止）

```
悪い例: test データを含めた全体の中央値で補完
  → test の情報が train の補完値に入り込む（データリーク）
  → モデルが test データの情報を「知っている」状態になる

良い例: train のみの中央値を計算し、test にもその値を使う
  → 現実的なシナリオ（本番環境では過去データの統計値しか使えない）を再現できる
```

```python
# train の統計値を計算し、test にも適用する
train_data, num_medians, cat_modes = fill_missing(train_data)
test_data,  _,           _         = fill_missing(test_data, num_medians, cat_modes)
#                                                   ↑ train の統計値を渡す
```

---

## ステップ2: 特徴量エンジニアリング

### 基本の考え方

> **「元の列をそのまま使うより、現実の意味を反映した形に変換すると、モデルが学習しやすくなる」**

モデルは数値の大小しか読み取れない。  
「2007 年建築」という数値より「17 年前に建築」という経過年数の方が、  
価格との関係をモデルが発見しやすい。

### 追加した派生特徴量の一覧

| 特徴量 | 計算方法 | なぜ有用か |
|---|---|---|
| `TotalSF` | 地下室 + 1階 + 2階の面積合計 | 住宅の「総大きさ」を1つの数値で表現できる |
| `TotalBath` | フルバス + 0.5×ハーフバス（地上・地下） | バスルームの「価値の重み」を考慮した合計 |
| `HouseAge` | 売却年 − 建築年 | 「建築年号」より「築何年か」の方が価格と直結 |
| `YearsSinceRemod` | 売却年 − リフォーム年 | 最近リフォームされた物件ほど高価格 |
| `HasGarage` | GarageArea > 0 なら 1 | 有無のフラグ（面積0と「なし」を区別） |
| `HasBasement` | TotalBsmtSF > 0 なら 1 | 地下室の有無フラグ |
| `Has2ndFlr` | 2ndFlrSF > 0 なら 1 | 2階の有無フラグ |
| `HasFireplace` | Fireplaces > 0 なら 1 | 暖炉の有無フラグ |
| `TotalPorchSF` | 全ポーチ面積の合計 | 屋外スペース全体を1つの数値で表現 |
| `QualArea` | OverallQual × GrLivArea | 「広さ × 品質」の相乗効果（交互作用項） |

### 交互作用項（QualArea）の考え方

```
居住面積が広い → 高価格
品質が高い     → 高価格

では、「広くて品質も高い」場合は？
  → 単純な足し算以上の価値になる（相乗効果）
  → 掛け算で表現することで、その相乗効果をモデルに伝えられる

QualArea = OverallQual × GrLivArea
  → 面積が同じでも品質が高ければ高スコア
  → 品質が同じでも面積が大きければ高スコア
```

### 有無フラグの考え方

```
ガレージ面積（GarageArea）: 0 〜 1488 の数値
  → 面積が 0 の場合は「ガレージなし」と「小さいガレージ」が区別できない

HasGarage フラグ: 0 または 1
  → 「ガレージがあるか否か」という質的な違いを明示的に表現
  → 面積（量）とフラグ（質）を両方持つことで、異なる側面を学習できる
```

---

## ステップ3: カテゴリ変数のエンコード

### 問題：文字列はモデルに渡せない

機械学習モデルは数値しか扱えない。  
`"Neighborhood"` 列の値「`CollgCr`」「`OldTown`」などの文字列を数値に変換する必要がある。

### 採用した手法：One-Hot エンコード

```
変換前:
  Neighborhood = "CollgCr"
  Neighborhood = "OldTown"

変換後（One-Hot）:
  Neighborhood_CollgCr = 1, Neighborhood_OldTown = 0
  Neighborhood_CollgCr = 0, Neighborhood_OldTown = 1
```

各カテゴリが独立した列になり、それぞれ 0/1 の値を持つ。  
モデルはカテゴリ間に「大小関係」があると誤解しない（例：CollgCr > OldTown のような誤解）。

### train と test を結合してエンコードする理由

```python
# train と test を一時的に結合してエンコード
all_feat = pd.concat([train_feat[NUM_FEATURES + CAT_FEATURES],
                       test_feat[NUM_FEATURES + CAT_FEATURES]], ignore_index=True)
all_feat = pd.get_dummies(all_feat, columns=CAT_FEATURES)

# 分割して元に戻す
n_train  = len(train_feat)
X        = all_feat.iloc[:n_train].copy()
X_test   = all_feat.iloc[n_train:].copy()
```

```
なぜ結合するのか？

悪い例: train と test を別々にエンコード
  → train に "BldgType_TwnhsI" が出現
  → test には "BldgType_TwnhsI" が出現しない場合、列が消える
  → train と test で列数・列名がずれて学習できない

良い例: 結合してからエンコード
  → train + test 全体のカテゴリ一覧で列が作られる
  → どちらにも同じ列が存在し、列のズレが起きない
```

### 採用したカテゴリ特徴量

| 列名 | 採用理由 |
|---|---|
| `Neighborhood` | 地区によって価格帯が最も大きく異なる |
| `MSZoning` | 用途地域（住宅地・商業地等）は価格水準に影響 |
| `BldgType` | 一戸建て・タウンハウス等の種別が価格に影響 |
| `HouseStyle` | 平屋・2階建て等のスタイルは利便性・面積に直結 |
| `ExterQual` | 外壁品質は住宅全体の印象・耐久性に影響 |
| `KitchenQual` | キッチン品質は購入者が特に重視する箇所 |
| `BsmtQual` | 地下室品質は天井高・使いやすさを反映 |
| `GarageType` | 接続型・独立型等の種別が利便性・価格に影響 |
| `Foundation` | 基礎の種類は構造的な信頼性に関わる |
| `SaleCondition` | 通常売買か競売・差し押さえかで価格が大きく異なる |

---

## ステップ4: ハイパーパラメータのチューニング

`house_price.py` から引き継いだ手法。`RandomizedSearchCV` で各モデルを最適化する。

```python
gs = RandomizedSearchCV(
    estimator, param_dist,
    n_iter=50,                              # 50回ランダムサンプリング
    cv=5,                                   # 5分割交差検証
    scoring="neg_root_mean_squared_error",  # RMSE で評価
    n_jobs=-1,                              # 全CPUコアを使用
    random_state=1
)
gs.fit(X, y)
```

詳しい解説は `house_price_improvement_guide.md` のステップ5を参照。

---

## ステップ5: VotingRegressor によるアンサンブル

`house_price.py` から引き継いだ手法。チューニング済みの3モデルを平均する。

```
RandomForest → 予測価格 ─┐
XGBoost      → 予測価格 ─┼─ 平均 → 最終予測
LightGBM     → 予測価格 ─┘
```

詳しい解説は `house_price_improvement_guide.md` のステップ4を参照。

---

## house_price.py との比較

| 観点 | house_price.py | house_price_ex.py |
|---|---|---|
| 数値特徴量の数 | 5列 | 30列以上 |
| カテゴリ特徴量 | なし | 10列（One-Hot後は50列以上） |
| 欠損値処理 | なし（データに欠損がほぼない列のみ使用） | 2段階補完（0補完 + 中央値/最頻値） |
| 派生特徴量 | 3種類 | 10種類 |
| 交互作用項 | Area_x_RemodYear のみ | QualArea（品質 × 面積） |
| モデルアーキテクチャ | 同じ（RF / XGB / LGBM + VotingRegressor） | 同じ |

### なぜ特徴量を増やすと精度が上がるのか

```
少ない特徴量でのモデル（house_price.py）:
  "LotArea" と "YearRemodAdd" の2列しか使っていない
  → 住宅価格を左右する要因の多くを無視している
  → モデルが「見えていない情報」が多い状態

多い特徴量でのモデル（house_price_ex.py）:
  品質・面積・地区・バス数・ガレージなど多角的な情報を利用
  → 住宅価格の決定要因を幅広くカバーできる
  → モデルが「総合的な判断」を下せる
```

### なぜタイタニックとは逆に特徴量を増やして効果があるのか

タイタニックのデータ（891行）では、特徴量を増やすと過学習しやすかった。  
住宅価格データ（1460行）でも同様のリスクはあるが、  
今回追加した特徴量は**物理的・直感的に価格と関係が深い列**に絞っており、  
ノイズとなる情報の混入を抑えている。

```
追加して効果がある特徴量の条件:
  ① 価格と直感的に関係がある（根拠がある）
  ② 欠損値や外れ値が少ない（ノイズが少ない）
  ③ 他の特徴量と異なる情報を持つ（冗長でない）
```

---

## 精度向上のための工夫まとめ

| 工夫 | 内容 | 効果 |
|---|---|---|
| 欠損値の意味を考えた補完 | 設備なし→0、記録漏れ→中央値/最頻値 | 誤った補完によるノイズを防ぐ |
| データリーク防止 | test に train の統計値を適用 | 現実的な予測精度を保つ |
| 派生特徴量の作成 | TotalSF・TotalBath・HouseAge 等 | 1列では表現できない情報を統合 |
| 交互作用項の追加 | QualArea = 品質 × 面積 | 特徴量間の相乗効果を明示 |
| 有無フラグの追加 | HasGarage・HasBasement 等 | 量（面積）と質（有無）の両面をカバー |
| カテゴリ変数の活用 | Neighborhood・KitchenQual 等 | 価格帯の違いを地区・品質ランクで捉える |
| train+test 結合エンコード | pd.get_dummies 後に分割 | 列のズレによる学習エラーを防ぐ |

---

## まとめ：精度を高めるための思考プロセス

```
「なぜこのデータが住宅価格と関係するのか」を常に考える

例: なぜ Neighborhood（地区）を使うのか？
  → 同じ広さでも、人気エリアの物件は高い
  → 「場所」は住宅価格の最重要要因の1つ

例: なぜ TotalSF（総床面積）を作るのか？
  → 地下室・1階・2階を別々に使うより
    「この家は全体的に何平方フィートか」という総合指標が価格予測に有効

例: なぜ QualArea（品質 × 面積）を作るのか？
  → 面積だけでも品質だけでもなく、「広くて高品質」という組み合わせが価格に影響する
```

> **重要な原則**  
> 特徴量を増やすことが目的ではなく、「価格を決める本質的な要因を、モデルが理解できる形で伝える」ことが目的。  
> 根拠のない特徴量追加はノイズとなり、精度を下げることもある。
