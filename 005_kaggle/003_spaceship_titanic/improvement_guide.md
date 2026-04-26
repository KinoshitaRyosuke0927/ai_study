# 宇宙船タイタニック転送予測モデル 精度向上ガイド

機械学習初学者向けに、宇宙船タイタニックの乗客が異次元に転送されたかを予測するモデルの  
構築・精度向上プロセスを時系列でまとめた学習教材です。

---

## はじめに：このコンペティションで学べること

このコンペティションは**二値分類**問題です。タイタニックの生存予測と同じ種類の問題ですが、  
「直感的に関係する特徴量がわからない」という現実的な状況からスタートします。

| 観点 | タイタニック（生存予測） | 宇宙船タイタニック（転送予測） |
|---|---|---|
| 問題の種類 | 二値分類 | 二値分類 |
| 目的変数 | Survived（0/1） | Transported（True/False） |
| 評価指標 | Accuracy | Accuracy |
| 直感的なヒント | 「女性・子供優先」の歴史的事実がある | なし（架空の設定のため） |

> **このガイドで学ぶ最重要の問い**  
> 「どの特徴量が予測に関係するかわからないとき、どうやって探すか？」

---

## ステップ1: データの理解（EDA）

### なぜEDAから始めるのか

直感的・経験的な知識がない問題では、**まずデータそのものに語らせる**ことが出発点になります。  
EDA（Exploratory Data Analysis：探索的データ分析）とは、  
グラフや集計を使ってデータの構造・傾向・関係性を把握する作業です。

### データの概要

```
行数: 8,693件  列数: 13列（+ 前処理で追加する列）
```

| 列名 | 種類 | 説明 |
|---|---|---|
| PassengerId | ID | `gggg_pp` 形式。gggg=グループ番号、pp=グループ内番号 |
| HomePlanet | カテゴリ | 出発惑星（Earth / Europa / Mars） |
| CryoSleep | 二値 | 冷凍睡眠を選択したか（True/False） |
| Cabin | 文字列 | 客室番号（`デッキ/番号/側面` 形式） |
| Destination | カテゴリ | 目的地惑星 |
| Age | 数値 | 年齢 |
| VIP | 二値 | VIPサービス契約有無 |
| RoomService〜VRDeck | 数値 | 各アメニティの支出額（5列） |
| Transported | 二値 | **目的変数**：転送されたか（True/False） |

### 実施したEDAの種類と目的

#### 1. ターゲットの分布確認

まず目的変数のバランスを確認します。極端に偏っていると（例: 99%がFalse）、  
精度の測り方自体を変える必要があります。

```python
counts = df['Transported'].value_counts()
# False: 4,315件（49.6%）, True: 4,378件（50.4%）
# ほぼ均等のため Accuracy をそのまま使える
```

#### 2. カテゴリ列ごとの転送率

各カテゴリ列について「そのカテゴリに属する乗客の転送率」を集計します。  
**全体平均（50.4%）から大きく乖離しているカテゴリが重要な特徴量の候補**です。

```python
df.groupby('CryoSleep')['Transported'].mean()
# CryoSleep=False → 転送率 32.9%
# CryoSleep=True  → 転送率 81.8%  ← 差が約49ポイント！
```

| 列名 | 最大転送率 | 最小転送率 | 差 | 重要度 |
|---|---|---|---|---|
| CryoSleep | 81.8%（True） | 32.9%（False） | 約49pt | 高 |
| HomePlanet | 65.9%（Europa） | 42.4%（Earth） | 約23pt | 中 |
| Deck | 73.4%（B） | 20.0%（T） | 約53pt | 高 |
| Side | 55.5%（S） | 45.1%（P） | 約10pt | 低 |
| VIP | 50.6%（False） | 38.2%（True） | 約12pt | 低 |

#### 3. 数値列の分布比較（転送あり vs なし）

転送された乗客とされなかった乗客で、数値の分布が異なるかを確認します。  
分布が重なっていれば関係が弱く、分離していれば関係が強い特徴量です。

```python
for transported in [True, False]:
    data = df[df['Transported'] == transported]['Age'].dropna()
    ax.hist(data, bins=40, alpha=0.6)
```

#### 4. 相関係数の確認

数値列と目的変数（Transported）の相関係数を確認します。  
相関が強いほど（絶対値が大きいほど）、その列が予測に有用な可能性があります。

```
RoomService    -0.245  ← アメニティを使う人ほど転送されていない
Spa            -0.221
VRDeck         -0.207
TotalSpend     -0.200
Age            -0.075
```

> **注意**: 相関係数は**線形関係**しか捉えられません。  
> 非線形の関係（例: 「若者と高齢者は転送されやすいが中年は違う」等）は見えません。

#### 5. RandomForest Feature Importance

最も実用的な特徴量の重要度評価手法です。  
全特徴量でモデルを学習させ、**モデル自身に「どの列が重要か」を判定させます**。

```python
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

importances = pd.Series(model.feature_importances_, index=X_train.columns)
# Age: 15.6%  TotalSpend: 15.0%  Spa: 9.3%  CryoSleep: 7.6% ...
```

**なぜ有効か**: 線形の相関係数と異なり、複雑な交互作用や非線形な関係も反映されます。

### EDAで得た重要な発見

```
1. CryoSleep が転送率に最大の影響（32% vs 82%）
2. 各アメニティの支出額が転送率と負の相関（使うほど転送されない）
3. Cabin の Deck・Side にも転送率の差がある
4. HomePlanet（出発惑星）によって転送率が異なる
5. 冷凍睡眠中の乗客はアメニティを使えないため、支出額は必然的に0
```

### 特徴量選択の3つのアプローチ（整理）

```
アプローチ1: 統計的探索（EDA）
  カテゴリ別集計・分布比較・相関係数で可視化して確認
  → 直感的にわかりやすいが、複雑な関係は見えない

アプローチ2: 統計的検定
  t検定・カイ二乗検定で「本当に関係があるか」を数値で判断
  → 線形・二値の関係に強い

アプローチ3: モデルベースの重要度（Feature Importance）
  RandomForestに全特徴量を投入して重要度を確認
  → 非線形・複雑な交互作用も捉えられる。最も実用的
```

---

## ステップ2: ベースラインモデルの作成

### 何をしたか

EDAで「重要そう」とわかった特徴量のうち、最もシンプルな2つで最初のモデルを作成しました。

```python
features = ["Age", "TotalSpend"]
model = RandomForestClassifier(random_state=1)
model.fit(X, y)
```

### なぜ Age と TotalSpend を選んだか

| 特徴量 | 転送との関係 |
|---|---|
| `Age` | Feature Importanceで最上位（15.6%）。若い乗客ほど転送されやすい可能性 |
| `TotalSpend` | Feature Importanceで2位（15.0%）。支出が多い乗客ほど転送されない傾向 |

> 相関係数だけでなく、Feature Importanceも参考にしたのがポイントです。  
> 相関係数の上位は個別アメニティ（Spa等）でしたが、  
> それらをまとめた TotalSpend の方が Feature Importance では高く出ました。

### ベースラインを作る重要性

> これ以降のすべての改善は「ベースラインと比べて Accuracy が高くなっているか」を  
> 基準に判断します。ベースラインがないと、改善の効果を測定できません。

---

## ステップ3: 多特徴量モデルへの拡張

### 何をしたか

EDAの結果を元に、特徴量を大幅に追加しました。

```python
# 数値特徴量（11列）
NUM_FEATURES = [
    "Age", "TotalSpend",
    "RoomService", "FoodCourt", "ShoppingMall", "Spa", "VRDeck",
    "GroupSize", "IsAlone", "NoSpend", "CabinNum",
]

# カテゴリ特徴量（6列、One-Hotエンコード後は多列に展開される）
CAT_FEATURES = ["CryoSleep", "HomePlanet", "Destination", "Deck", "Side", "VIP"]
```

### 新たに追加した前処理・特徴量

#### Cabinの分割

```python
# "B/0/P" → Deck="B", CabinNum=0, Side="P" に分割
cabin_split = df["Cabin"].str.split("/", expand=True)
df["Deck"]     = cabin_split[0]
df["CabinNum"] = pd.to_numeric(cabin_split[1], errors="coerce")
df["Side"]     = cabin_split[2]
```

EDAより Deck B（73.4%）と Deck E（35.7%）で転送率が大きく異なるため、  
Cabinの文字列から Deck を抽出して特徴量として使います。

#### グループ情報の活用

```python
# PassengerId の "0003_01" → グループ番号 "0003"
df["Group"]     = df["PassengerId"].str.split("_").str[0]
df["GroupSize"] = df.groupby("Group")["Group"].transform("count")
df["IsAlone"]   = (df["GroupSize"] == 1).astype(int)
```

同グループの乗客は家族が多く、行動パターンが類似する可能性があります。

#### ドメイン知識を活用した欠損値処理

```python
# CryoSleep=True の乗客はアメニティを物理的に使えないため支出は必ず0
cryo_true = df["CryoSleep"] == True
for col in AMENITIES:
    df.loc[cryo_true, col] = df.loc[cryo_true, col].fillna(0)
```

「冷凍睡眠中はアメニティを使えない」というドメイン知識を利用した補完です。  
全体中央値で補完するよりも正確な値になります。

#### カテゴリ特徴量のOne-Hotエンコード

機械学習モデルは文字列をそのまま扱えません。  
カテゴリ列を「その値かどうか」の0/1列に変換します。

```python
# train+test を結合してダミー変数化（列の種類を統一するため）
all_feat = pd.concat([train_feat, test_feat], ignore_index=True)
all_feat = pd.get_dummies(all_feat, columns=CAT_FEATURES)
```

> **なぜ train+test を結合するか**  
> test にしか存在しないカテゴリ値があると列の数が一致せず、  
> モデルが予測できなくなります。結合してダミー変数化することで列を統一します。  
> ただし、補完に使う統計量（中央値・最頻値）は **train だけで計算**します（データリーク防止）。

---

## ステップ4: さらなる精度向上（特徴量の追加と欠損補完の改善）

### 改善1: 特徴量エンジニアリングの追加

#### 年齢層（AgeGroup）

```python
df["AgeGroup"] = pd.cut(
    df["Age"],
    bins=[-1, 12, 17, 64, 200],
    labels=["Child", "Teen", "Adult", "Senior"],
)
```

年齢の連続値をそのまま使うより、「子供か大人か」という区分で  
グループごとの行動パターンを捉えやすくなります。

#### CryoSleep × HomePlanet の交互作用特徴量

```python
df["Cryo_x_Planet"] = df["CryoSleep"].astype(str) + "_" + df["HomePlanet"].astype(str)
# "True_Europa", "False_Earth", "True_Mars" など 6パターンが生成される
```

CryoSleep と HomePlanet はそれぞれ単独でも重要ですが、  
「Europa出身かつ冷凍睡眠=True」というパターンは単独特徴量では捉えられません。

**交互作用特徴量の考え方**:

```
CryoSleep（単独）: True / False の2パターン
HomePlanet（単独）: Earth / Europa / Mars の3パターン

交互作用: True_Earth / True_Europa / True_Mars
          False_Earth / False_Europa / False_Mars
  → 6パターン。「どの惑星のどんな乗客が転送されやすいか」を学習できる
```

#### グループが同じCabinに乗っているか（FamilyInSameCabin）

```python
df["FamilyInSameCabin"] = (
    df.groupby("Group")["Cabin"].transform("nunique") == 1
).astype(int)
```

同グループ全員が同じ客室ブロックにいるか（家族の結束度）を表す特徴量です。

### 改善2: グループ内補完による欠損値処理の高度化

#### 従来の方法の問題点

```python
# 従来: 全体の最頻値で一律補完
df["HomePlanet"] = df["HomePlanet"].fillna(df["HomePlanet"].mode()[0])
# → 全員に「最も多い惑星（Earth）」を割り当てる → 多くの場合は不正確
```

#### 改善後: 2段階補完

```python
def group_fill(df, col):
    # ステップ1: 同グループ内の既知の値で前後補完
    df[col] = df.groupby("Group")[col].transform(lambda x: x.ffill().bfill())
    return df

for col in ["HomePlanet", "Destination", "Cabin", "CryoSleep"]:
    group_fill(df, col)

# ステップ2: それでも残った欠損は全体統計で補完
```

**なぜこれが有効か**:

```
例: グループ "0003" に 3人の乗客がいる場合
  0003_01: HomePlanet = "Europa"
  0003_02: HomePlanet = NaN（欠損）
  0003_03: HomePlanet = "Europa"

  従来: NaN → "Earth"（最頻値、不正確）
  改善: NaN → "Europa"（同グループの値、正確）
```

同グループ（家族）なら同じ惑星から来ている可能性が高いため、  
中央値補完より正確な値が得られます。

### 欠損値処理の原則まとめ

| 方法 | 使う状況 |
|---|---|
| 0で補完 | 「設備なし」を意味する欠損（例: CryoSleep=True のアメニティ支出） |
| グループ内補完 | 同グループ（家族）なら同じ値を持つ可能性が高い列 |
| 中央値補完 | 数値列の一般的な欠損 |
| 最頻値補完 | カテゴリ列の一般的な欠損 |

> **重要**: 補完に使う統計量（中央値・最頻値）は **train データだけで計算** し、  
> test データにも同じ値を適用する（データリーク防止）。

---

## ステップ5: モデルの選択と評価

### 3モデル + アンサンブルの構成

| モデル | 特徴 |
|---|---|
| RandomForest | 複数の決定木を**独立して**学習し、多数決で予測する |
| XGBoost | 前の木の「失敗」を次の木が補正しながら学習する（勾配ブースティング） |
| LightGBM | XGBoostと同じ手法だが高速・大規模データに強い |

### Nested CV（二重交差検証）による評価

```
外側CV（cross_val_score）: 汎化性能の評価
  └─ 内側CV（RandomizedSearchCV）: ハイパーパラメータ探索

→ パラメータ選択に使ったデータで評価しないため、正直なスコアになる
```

```python
inner_cv = RandomizedSearchCV(estimator, param_dist, n_iter=100, cv=5)
outer_scores = cross_val_score(inner_cv, X, y, cv=5, scoring="accuracy")
```

> **注意**: Nested CV のスコアは通常の CV より低く出ます。  
> これは「精度が下がった」のではなく「より正直なスコアになった」ということです。  
> Kaggle 提出スコアに近い値が得られます。

### VotingClassifier（ソフト投票）によるアンサンブル

```python
voting = VotingClassifier(
    estimators=[(name, model) for name, model in tuned_models.items()],
    voting="soft",  # 予測確率の平均で判定
)
```

```
RandomForest → 転送確率 0.65 ─┐
XGBoost      → 転送確率 0.72 ─┼─ 平均 0.68 → 転送（0.68 > 0.5）
LightGBM     → 転送確率 0.67 ─┘
```

3つのモデルはそれぞれ異なるアルゴリズムで学習するため、  
**異なる種類のエラーを犯します**。多数決（平均）を取ることで互いのエラーを打ち消せます。

---

## 精度改善プロセス全体の振り返り

### 時系列まとめ

```
ステップ1: EDA（データ探索）
  → カテゴリ別転送率・相関係数・Feature Importance で重要な特徴量を特定
    ↓
ステップ2: ベースラインモデルの作成
  → Age + TotalSpend の2特徴量でシンプルなモデルを構築
    ↓
ステップ3: 多特徴量モデルへの拡張
  → CryoSleep・各アメニティ・Deck・Side・HomePlanet 等を追加
  → Cabin分割・グループ情報・ドメイン知識を活かした欠損補完
    ↓
ステップ4: 特徴量と欠損補完のさらなる改善
  → AgeGroup・交互作用特徴量・FamilyInSameCabin を追加
  → グループ内補完による欠損値精度の向上
    ↓
ステップ5: モデルのチューニングとアンサンブル
  → RandomizedSearchCV で 3モデルを個別チューニング
  → VotingClassifier（ソフト投票）でアンサンブル → 最終モデル
```

### 各ステップで使った手法と目的

| ステップ | 主な手法 | 目的 |
|---|---|---|
| 1 | カテゴリ別集計・相関係数・Feature Importance | 「どの特徴量が重要か」をデータから発見する |
| 2 | RandomForest・Nested CV | 比較の基準（ベースライン）を確立する |
| 3 | Cabin分割・One-Hotエンコード・中央値補完 | 元データに含まれる情報を活用できる形に加工する |
| 4 | AgeGroup・交互作用特徴量・グループ内補完 | より精密な情報をモデルに与える |
| 5 | RandomizedSearchCV・VotingClassifier | モデル自体の性能を最大化する |

### 失敗から学ぶこと（他のコンペとの比較）

| 落とし穴 | 原因 | 防ぎ方 |
|---|---|---|
| CVスコアは高いのに提出スコアが低い | データリーク（test情報が前処理に混入） | 統計量は train だけで計算する |
| 特徴量を増やしたら精度が下がった | 過学習（ノイズまで学習してしまう） | Nested CVで正直に評価・特徴量を逐次検証 |
| チューニング後のCVスコアが楽観的 | モデル選択バイアス | Nested CVでパラメータ選択と評価を分離 |

---

## 機械学習改善の一般的な進め方（まとめ）

精度改善は以下のサイクルを繰り返すことで行う。

```
① EDA でデータを理解する
  → 転送率の差・相関・Feature Importance で重要な列を特定
    ↓
② シンプルなベースラインを作る
  → 重要度上位の2〜3特徴量 × RandomForest から始める
    ↓
③ 仮説を立てて特徴量を追加する
  → CV スコアを測定 → 改善したら採用、しなければ却下
    ↓
④ ドメイン知識で前処理を改善する
  → 「冷凍睡眠中はアメニティを使えない」→ 欠損を0で補完
    ↓
⑤ モデルとアンサンブルを改善する
  → RandomizedSearchCV でチューニング → Voting で組み合わせる
    ↓
⑥ Kaggle に提出して実際のスコアを確認する
  → CV スコアと乖離が大きい場合はデータリーク・過学習を疑う
    ↓
⑦ ① に戻る
```

> **最も大切なこと**  
> 「なぜこの手法を使うのか」「何の問題を解決しようとしているのか」を  
> 常に意識しながら改善を進めること。  
> 手法を目的にするのではなく、**「精度を上げるための手段」として使うことが重要**。
