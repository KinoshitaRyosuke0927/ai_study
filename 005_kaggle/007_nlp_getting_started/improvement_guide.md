# 災害ツイート分類モデル 精度向上ガイド

機械学習初学者向けに、NLP（自然言語処理）コンペで  
テキストデータからモデルの精度を段階的に高めていった  
思考プロセス・手法・実践を時系列でまとめた学習資料です。

---

## はじめに：このコンペで学べること

| 観点 | 内容 |
|------|------|
| 問題の種類 | 二値分類（Binary Classification） |
| 目的変数 | target（1=災害ツイート、0=非災害ツイート） |
| 評価指標 | F1 スコア |
| 特徴 | **テキストデータ**を扱う点がこれまでと根本的に異なる |

> **このガイドで学ぶ中心的な問い**  
> 「テキストデータはどうやって機械が理解できる形に変換するの？」  
> 「TF-IDF と BERT、どう違うの？どう選ぶの？」

---

## コンペの概要

### データ

| カラム | 内容 |
|--------|------|
| `id` | ツイートの識別番号 |
| `keyword` | ツイート内の特定キーワード（空欄あり） |
| `location` | 送信元の場所（空欄あり） |
| `text` | ツイートの本文 |
| `target` | 1=本物の災害、0=災害ではない（trainのみ） |

```
件数:
  学習データ: 7,613 件
  テストデータ: 3,263 件

目的変数の分布:
  0（非災害）: 4,342 件（57.0%）
  1（災害）  : 3,271 件（43.0%）
```

### F1 スコアとは

```
F1 = 2 × (Precision × Recall) / (Precision + Recall)

Precision（適合率）= TP / (TP + FP)
  → 「災害と予測したうち、本当に災害だった割合」

Recall（再現率）= TP / (TP + FN)
  → 「本当に災害のうち、正しく検知できた割合」

TP: 災害と予測 → 実際も災害   FP: 災害と予測 → 実際は非災害
FN: 非災害と予測 → 実際は災害  TN: 非災害と予測 → 実際も非災害
```

どちらか一方だけ高くても F1 は上がらない。  
「見逃しを減らす（Recall↑）」と「誤報を減らす（Precision↑）」のバランスが重要。

---

## テキストデータの扱いかた：2つのアプローチ

テキストは数値ではないため、機械学習モデルに渡す前に  
**数値への変換**が必要。主に2つのアプローチがある。

```
アプローチ①: TF-IDF（統計的手法）
  テキスト → 単語の出現頻度に基づくベクトル → 機械学習モデル

  "wildfire near canada"
  → {"wildfire": 0.8, "near": 0.2, "canada": 0.5, ...}（20,000次元）

アプローチ②: BERT（ディープラーニング）
  テキスト → トークン列 → Transformer → 文脈を理解したベクトル

  "wildfire near canada"
  → [101, 2748, 2379, 3003, 102] → [0.32, -0.51, 0.88, ...（768次元）]
```

| 比較項目 | TF-IDF | BERT |
|----------|--------|------|
| 単語の理解 | 出現頻度（文脈なし） | 文脈を考慮 |
| 「bank（銀行）」と「bank（川岸）」 | 同じ単語として扱う | 使われ方で区別 |
| 学習速度 | 数秒 | 数時間（CPU） |
| 精度 | 中程度 | 高精度 |
| 必要な知識 | sklearn | PyTorch + Transformers |

---

## ステップ1：ベースラインモデルの作成（TF-IDF + ロジスティック回帰）

### 何をしたか

まず最もシンプルな方法で動くモデルを作り、比較の基準を作った。

### TF-IDF とは

> **TF-IDF（Term Frequency – Inverse Document Frequency）**  
> 単語の「重要度」を数値化する手法。

```
TF（単語頻度）: そのツイート内での単語の出現頻度
IDF（逆文書頻度）: 全ツイートでの出現頻度の逆数（希少な単語ほど高い）

TF-IDF = TF × IDF

例:
  "fire"    → 多くのツイートに登場 → IDF 低い → TF-IDF 小さい
  "wildfire" → 少数のツイートのみ → IDF 高い → TF-IDF 大きい
  → 「特定ツイートにしか現れない単語」ほど重要とみなす
```

### N-gram とは

```python
ngram_range=(1, 2)   # 1-gram と 2-gram を同時に使う
```

```
1-gram（単語単体）: "forest", "fire"
2-gram（2単語の組）: "forest fire", "near canada"

→ "forest fire" を1つの意味のある単語として扱える
→ 「forest（森）」と「fire（火）」がバラバラより意味が通じやすい
```

### テキスト前処理

```python
URL_RE      = re.compile(r"https?://\S+")
MENTION_RE  = re.compile(r"@\w+")
HASHTAG_RE  = re.compile(r"#(\w+)")
NONALPHA_RE = re.compile(r"[^a-zA-Z\s]")

def clean_text(text: str) -> str:
    text = URL_RE.sub("", text)          # URL を除去
    text = MENTION_RE.sub("", text)      # @メンション を除去
    text = HASHTAG_RE.sub(r"\1", text)   # #hashtag → hashtag
    text = NONALPHA_RE.sub(" ", text)    # 記号・数字を空白に
    return text.lower().strip()          # 小文字化
```

**前処理の理由**：URL・@メンション・記号は意味を持たず、  
モデルの学習を妨げるノイズになる。

### sklearn Pipeline とは

```python
pipeline = Pipeline([
    ("tfidf", TfidfVectorizer(...)),
    ("clf",   LogisticRegression(...)),
])
```

Pipeline を使うと「TF-IDF 変換 → モデル学習」を1つのオブジェクトとして扱える。

```
Pipeline なし（データリーク発生）:
  1. 全データで TF-IDF を fit ← テストデータの情報が混入！
  2. 学習データで学習
  3. テストデータで予測

Pipeline あり（データリーク防止）:
  CV の各 fold で:
    1. 学習データのみで TF-IDF を fit
    2. 検証データは学習済み TF-IDF で transform のみ
```

> **データリークとは**  
> 本来知れないはずのテストデータの情報が学習に混入すること。  
> CV スコアが実際より高く見えてしまう「嘘のスコア」になる。

### 結果

```
=== 5-Fold CV F1 Score ===
  Fold 1: 0.7492
  Fold 2: 0.7568
  Fold 3: 0.7459
  Fold 4: 0.7380
  Fold 5: 0.7449
  Mean : 0.7470  ±0.0063

Train F1 : 0.8389
CV F1    : 0.7470
差分     : 0.0919  （過学習の目安）
```

**Kaggle スコア: 0.80171**

### 分析：災害ツイートに寄与する上位単語

```
災害クラスに寄与する単語（係数が大きい）:
  fire, flood, earthquake, typhoon, wildfire, ...

非災害クラスに寄与する単語（係数が小さい）:
  love, new, just, like, ...
```

ロジスティック回帰は「どの単語が災害らしいか」を係数で学習している。  
ただし「文脈」は無視している（"burning" が比喩かどうか判断できない）。

---

## ステップ2：BERT ファインチューニング（DistilBERT）

### なぜ BERT に移行したか

TF-IDF の根本的な限界：

```
"I'm on fire！" （比喩）
"The building is on fire." （本物の災害）

→ TF-IDF はどちらも "fire" が含まれている → 同じように扱う
→ BERT は前後の文脈（"I'm", "building"）を見て区別できる
```

### BERT とは

> **BERT（Bidirectional Encoder Representations from Transformers）**  
> 大量のテキスト（Wikipedia など）で事前学習した言語モデル。  
> 文章中の各単語を「前後の文脈を考慮した」ベクトルに変換する。

```
通常の埋め込み:
  "bank" → [0.5, -0.3, 0.8, ...]  常に同じベクトル

BERT の埋め込み:
  "I went to the bank." → bank = [0.2, 0.9, -0.1, ...] （金融機関の意味）
  "Fish near the bank."  → bank = [-0.3, 0.1, 0.7, ...] （川岸の意味）
  → 同じ単語でも文脈によって異なるベクトルになる
```

### DistilBERT とは

BERT の「軽量版」。元の BERT の 97% の性能を維持しながら、  
パラメータ数を40%削減、速度を60%向上させたモデル。

```
BERT:          1億1,000万パラメータ  1 epoch ≈ 60 分（CPU）
DistilBERT:    6,600万パラメータ    1 epoch ≈ 30 分（CPU）
```

### ファインチューニングとは

```
事前学習済みの BERT の重みをベースに、
タスク専用のデータで「微調整」する手法。

事前学習: 大量テキストで言語の「意味」を学ぶ（Wikipedia など）
     ↓
ファインチューニング: 災害ツイートのデータで「0か1か」を学ぶ
     ↓
結果: 言語理解の基礎力 + 災害分類の専門知識
```

### トークナイザーとは

```python
tokenizer = AutoTokenizer.from_pretrained("distilbert-base-uncased")
encoding  = tokenizer("wildfire near canada", ...)
```

```
テキスト: "wildfire near canada"
      ↓ トークナイザー
input_ids:      [101, 2748, 2379, 3003, 102]
                 [CLS]  単語  単語  単語  [SEP]
attention_mask: [  1,    1,    1,    1,   1]
                （1=実際のトークン, 0=パディング）
```

- `[CLS]`: 文章の先頭を示す特殊トークン（最終的な分類に使われる）
- `[SEP]`: 文章の終端を示す特殊トークン
- `attention_mask`: パディングを無視するためのマスク

### Dataset クラスと DataLoader

```python
class TweetDataset(Dataset):
    def __init__(self, texts, labels, tokenizer, max_len):
        self.texts     = texts
        ...

    def __getitem__(self, idx):
        encoding = self.tokenizer(self.texts[idx], ...)
        return {"input_ids": ..., "attention_mask": ..., "labels": ...}

# DataLoader: バッチ単位でデータを取り出す仕組み
train_loader = DataLoader(train_dataset, batch_size=16, shuffle=True)
```

**バッチ学習**：16件ずつまとめて計算することで効率化。  
GPU/CPU のメモリに収まるサイズに調整する。

### AdamW オプティマイザーと学習率スケジューラー

```python
optimizer = AdamW(model.parameters(), lr=2e-5, weight_decay=0.01)
scheduler = get_linear_schedule_with_warmup(
    optimizer,
    num_warmup_steps=warmup_steps,   # 最初はゆっくり学習率を上げる
    num_training_steps=total_steps,  # その後線形に下げる
)
```

```
学習率の変化:
  0.0000 → 0.00002 → 0.00001 → 0.000001 → ...
  ウォームアップ  最大値    線形に減衰

なぜウォームアップが必要か:
  BERT は学習済みの重みを持っている。
  最初から大きな学習率で更新すると、せっかくの重みを壊してしまう。
  最初はゆっくり微調整し、徐々に学習率を上げて本格的に学習する。
```

### 勾配クリッピングとは

```python
nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
```

```
勾配が異常に大きくなると学習が不安定になる（勾配爆発）。
→ 勾配のノルムが 1.0 を超えたら、1.0 に収まるようにスケールダウンする。
```

### 学習ループと診断出力

```python
for epoch in range(1, EPOCHS + 1):
    train_loss = train_one_epoch(model, train_loader, ...)
    val_f1, val_loss, val_preds, val_labels, val_probs = evaluate(model, val_loader)
```

**診断出力の目的**：次の改善に向けた手がかりを得る

| 診断情報 | 何がわかるか |
|----------|------------|
| 学習曲線（loss の推移） | 過学習・未学習の判断 |
| クラス別 Precision / Recall | どちらの誤りが多いか |
| 混同行列（FP / FN） | 具体的な誤りのパターン |
| 予測確率の分布 | モデルの自信度の偏り |
| 誤分類サンプル | 誤りの傾向・改善の手がかり |

### 全データで再学習してテスト予測

```python
# 検証で best_epoch を把握 → 全データで同じ epoch 数だけ再学習
model_final = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME, num_labels=2)
for epoch in range(1, EPOCHS + 1):
    loss = train_one_epoch(model_final, full_loader, ...)
```

なぜ全データで再学習するか：  
検証データ（20%）も学習に使うことで、最終モデルをより強化できるため。

### 結果

```
=== 学習曲線サマリ ===
Epoch  train_loss  val_loss  val_F1
    1    0.5215      0.4102   0.7890
    2    0.3621      0.3987   0.8101 ← best
    3    0.2741      0.4561   0.7988   ← val_loss が上昇（過学習の兆候）
```

**Best Val F1: 0.8101 / Kaggle スコア: 0.82745**

### 分析：診断出力から読み取れること

```
=== 混同行列 ===
              予測: 非災害  予測: 災害
  実際: 非災害      771       98   ← FP
  実際: 災害        142      512   ← FN

FN（142件）> FP（98件）
→ 「災害ツイートを見逃している」ケースが多い
→ 閾値を下げれば Recall は上がるかも？
```

```
=== 改善の手がかり ===
・Epoch 2 がベスト → Epoch 3 で過学習が始まる
  → Early Stopping が有効かもしれない
・FN > FP → 閾値を 0.5 より低くすると Recall が上がるかも
・keyword カラムが未使用 → "wildfire" などの明示的な単語を活用できていない
```

---

## ステップ3：改善の試み（v2）とその失敗

### 何を試したか

distilbert v1 の分析から3つの改善を実装した：

1. **keyword 付加**：keyword を text の先頭に付加して文脈情報を追加
2. **閾値最適化**：検証データで F1 が最大になる確率閾値を探索
3. **Early Stopping**：val_F1 が改善しなければ停止（PATIENCE=1）

### keyword 付加

```python
def build_input(row) -> str:
    keyword = clean_text(str(row["keyword"])) if pd.notna(row["keyword"]) else ""
    text    = clean_text(str(row["text"]))
    if keyword:
        return f"{keyword} {text}"   # "wildfire forest fire near canada"
    return text
```

keyword は "wildfire"、"earthquake" など災害の種類を示す明示的な単語。  
テキストの先頭に置くことで BERT に「この災害カテゴリ」を直接伝えられる。

### 閾値最適化

```python
def find_best_threshold(labels, probs):
    for thresh in np.arange(0.30, 0.71, 0.01):
        preds = (probs >= thresh).astype(int)
        score = f1_score(labels, preds)
        if score > best_f1:
            best_thresh = thresh
    return best_thresh, best_f1
```

通常は確率 ≥ 0.5 なら「災害」と判定するが、  
FN > FP の場合は閾値を下げると Recall が上がって F1 が改善するかもしれない。

### 結果と失敗の分析

```
=== 学習曲線サマリ ===
Epoch  train_loss  val_loss  val_F1
    1    0.4823      0.3934   0.8030 ← best
    2    0.3499      0.4098   0.8016
  Early Stopping: 1 epoch 改善なし → 停止

=== 閾値最適化の結果 ===
  デフォルト閾値 0.50: F1=0.8030
  最適閾値     0.32: F1=0.8156  ← この閾値をテストに使用

Kaggle スコア: 0.80324  ← v1（0.82745）より悪化！
```

#### 失敗の原因①：PATIENCE=1 が早すぎた

```
v1: Epoch 2 がベスト（val_F1=0.8101）
v2: Epoch 1 がベスト → PATIENCE=1 で即停止 → best_epoch=1

→ 全データ再学習も 1 epoch だけ
→ v1 より少ない学習で提出 → 精度が下がった
```

#### 失敗の原因②：閾値最適化が検証セットに過学習

```
val で閾値 0.32 が最適でも、Kaggle の未知データには合わなかった

検証セット（1,523件）に最適化した閾値
  → その 1,523件に特有の偏りに合わせすぎた
  → 本番データ（3,263件）では過度に「災害」と判定しすぎた

target 予測:
  v1（閾値=0.50）: 0=1823件, 1=1440件
  v2（閾値=0.32）: 0=1699件, 1=1564件 ← 「災害」が増えすぎた
```

> **教訓**  
> 閾値最適化は、検証セットが小さい場合に「その検証セットへの過学習」を引き起こす。  
> 改善が小さい場合（+0.01 程度）は特に注意が必要。  
> Early Stopping の PATIENCE は、過去の実験結果を参考に設定する。

---

## ステップ4：BERTweet の導入

### なぜ BERTweet に移行したか

DistilBERT の事前学習データ：Wikipedia、BookCorpus（正式な文章）  
ツイートの特徴：略語・口語・絵文字・ハッシュタグ・ノイズだらけ

```
ツイートの例:
  "omg the wildfire is INSANE rn 😱 #PrayForCalifornia HTTPURL"

通常の BERT には「omg」「rn」「😱」「#PrayForCalifornia」は
学習データにほとんど存在しない → 理解が弱い
```

**BERTweet**（`vinai/bertweet-base`）：  
850万件のツイートで事前学習した BERT。  
ツイート特有の表現、略語、絵文字に強い。

### DistilBERT との前処理の違い

```
DistilBERT の前処理:
  "wildfire! https://t.co/xxx @CNN #fire"
  → "wildfire fire"  ← URL・@・# を全部消す

BERTweet の前処理（BERTweet 専用の規約に合わせる）:
  "wildfire! https://t.co/xxx @CNN #fire"
  → "wildfire! HTTPURL @USER #fire"  ← 構造を保持

なぜ保持するか:
  BERTweet は "HTTPURL" や "@USER" を語彙として持っている
  → 「URL が含まれている」「誰かに言及している」という情報を活かせる
```

```python
URL_RE     = re.compile(r"https?://\S+|www\.\S+")
MENTION_RE = re.compile(r"@\w+")

def clean_text(text: str) -> str:
    text = URL_RE.sub("HTTPURL", text)   # BERTweet の規約
    text = MENTION_RE.sub("@USER", text) # BERTweet の規約
    text = SPACE_RE.sub(" ", text).strip()
    return text  # 大文字・小文字はそのまま（lowercase しない）
```

| 前処理 | DistilBERT | BERTweet |
|--------|-----------|---------|
| URL | 削除 | HTTPURL に置換 |
| @メンション | 削除 | @USER に置換 |
| ハッシュタグ | # を除去して単語のみ | # ごと保持 |
| 大文字・小文字 | 小文字化 | そのまま（区別する） |
| 絵文字 | 削除（記号として消える） | そのまま（語彙に含む） |

### Early Stopping の実装（PATIENCE=2 に変更）

```python
PATIENCE = 2  # v2 の反省から 1 → 2 に変更

for epoch in range(1, EPOCHS + 1):
    train_loss = train_one_epoch(...)
    val_f1, ... = evaluate(...)

    if val_f1 > best_f1:
        best_f1 = val_f1
        best_epoch = epoch
        patience_count = 0
        torch.save(model.state_dict(), "best_model.pt")  # ベストモデルを保存
    else:
        patience_count += 1
        if patience_count >= PATIENCE:
            print("Early Stopping: 停止")
            break
```

```
Early Stopping の動き（PATIENCE=2）:
  Epoch 1: val_F1=0.8259  ★ best（patience=0）
  Epoch 2: val_F1=0.8211       （patience=1）
  Epoch 3: val_F1=0.8188       （patience=2）→ 停止
  → best_epoch=1 のモデルで予測
```

### 結果

```
=== 学習曲線サマリ ===
Epoch  train_loss  val_loss  val_F1
    1    0.4962      0.3850   0.8259 ← best
    2    0.3685      0.3914   0.8211
    3    0.2992      0.4220   0.8188
  Early Stopping: 2 epoch 改善なし → 停止

=== クラス別 Precision / Recall / F1（閾値=0.50）===
              precision  recall  f1-score
  非災害(0)    0.8519   0.9068   0.8785
  災害(1)      0.8645   0.7905   0.8259

=== 混同行列 ===
              予測: 非災害  予測: 災害
  実際: 非災害      788       81   ← FP（81件 ← v1の98件から減少）
  実際: 災害        137      517   ← FN（137件 ← v1の142件から改善）
```

**Best Val F1: 0.8259 / Kaggle スコア: 0.83665**

| モデル | Val F1 | Kaggle スコア | 改善幅 |
|--------|--------|--------------|--------|
| TF-IDF ベースライン | 0.7470 | 0.80171 | ― |
| DistilBERT | 0.8101 | 0.82745 | +0.02574 |
| BERTweet | 0.8259 | 0.83665 | +0.00920 |

---

## ステップ5：K-Fold CV + アンサンブル

### なぜ K-Fold + アンサンブルが有効か

単一モデルの問題点：

```
単一モデル（80/20 分割）:
  ・検証データは全体の 20%（1,523件）だけ
  ・その 1,523件の「偶然の偏り」に左右される
  ・学習データも 80%（6,090件）だけ
```

```
K-Fold アンサンブルの構造:

  全データ ── Fold1: 80%学習 / 20%検証 ── モデル1 ── テスト確率①
          ├── Fold2: 80%学習 / 20%検証 ── モデル2 ── テスト確率②
          ├── Fold3: 80%学習 / 20%検証 ── モデル3 ── テスト確率③
          ├── Fold4: 80%学習 / 20%検証 ── モデル4 ── テスト確率④
          └── Fold5: 80%学習 / 20%検証 ── モデル5 ── テスト確率⑤
                                              ↓
                                         ①〜⑤の平均 → 0/1 変換
```

**利点**：
- 全学習データが検証に使われる（データを無駄にしない）
- 5モデルの予測を平均 → ばらつきが減る
- OOF（後述）で信頼性の高い精度評価ができる

### OOF（Out-of-Fold）予測とは

```
OOF: 各サンプルが「自分が含まれていない fold のモデル」で予測された確率

Fold1 のモデル: Fold2〜5 で学習 → Fold1 の検証データを予測
Fold2 のモデル: Fold1,3〜5 で学習 → Fold2 の検証データを予測
...

→ 全 7,613件の予測がそろう
→ データリークなし・全学習データをカバーした公正な評価
```

```python
oof_probs = np.zeros(len(train_df))   # 全件分の OOF 確率を格納

for fold, (train_idx, val_idx) in enumerate(skf.split(X, y), 1):
    # 学習 → ベストモデル保存 → ベストモデルで val を予測
    oof_probs[val_idx] = val_probs   # OOF に記録

oof_preds = (oof_probs >= 0.5).astype(int)
oof_f1    = f1_score(y, oof_preds)   # 全データをカバーした F1
```

### テスト予測の平均化

```python
test_probs_sum = np.zeros(len(test_df))

for fold, ...:
    # 各 fold のベストモデルでテストデータを予測
    fold_test_probs  = get_probs(model, test_loader)
    test_probs_sum  += fold_test_probs

test_probs_avg = test_probs_sum / N_FOLDS  # 5 fold の平均
test_preds     = (test_probs_avg >= 0.5).astype(int)
```

**なぜ確率の平均が有効か**：

```
Fold1 が難しい「曖昧なツイート」で prob=0.48 と予測 → 0（非災害）
Fold2 が同じツイートで prob=0.53 と予測 → 1（災害）
Fold3 が同じツイートで prob=0.55 と予測 → 1（災害）

Fold1 のみ → 0（非災害）と予測
平均: (0.48 + 0.53 + 0.55) / 3 = 0.52 → 1（災害）と予測
→ 多数決的に正しい答えに近づく
```

### 結果

```
=== Fold ごとの結果 ===
 Fold    Val F1  Best Epoch  時間(分)
    1     0.8102           2      99.9
    2     0.8102           3      98.3
    3     0.7991           3      99.2
    4     0.8003           2     100.4
    5     0.7971           1      68.5
  平均    0.8034    ±0.0057

=== OOF F1（全学習データへの予測から算出） ===
  OOF F1      : 0.8033
  Fold 平均   : 0.8034
  BERTweet 単体: 0.8259

Kaggle スコア: 0.83971
```

**注目ポイント：OOF F1（0.8033）が単体 val F1（0.8259）より低い**

```
単体モデルの val F1=0.8259 は「偶然その分割が簡単だった」可能性がある。
K-Fold の OOF は全データで評価するため、より信頼できる指標。
→ Kaggle スコアと OOF F1 の比較で、過学習の有無を判断できる。
```

---

## 精度向上プロセス全体の振り返り

### スコア推移

```
  TF-IDF ベースライン : 0.80171
  DistilBERT          : 0.82745  (+0.02574)
  BERTweet v2 ※失敗   : 0.80324  (-0.02421)  ← 閾値過学習 + 学習不足
  BERTweet 単体        : 0.83665  (+0.00920)
  BERTweet K-Fold      : 0.83971  (+0.00306)
```

### 時系列まとめ

```
ステップ1: TF-IDF + ロジスティック回帰でベースライン作成
  → テキストを数値に変換する基本を学んだ
  → CV F1=0.7470、Kaggle=0.80171
     ↓
ステップ2: DistilBERT ファインチューニング
  → 文脈を理解するモデルに移行
  → 診断出力で「FN > FP」「Epoch3 で過学習」を発見
  → Kaggle=0.82745
     ↓
ステップ3: 改善の試み（v2）
  → keyword 付加・閾値最適化・Early Stopping を同時に実装
  → PATIENCE=1 で学習不足・閾値は検証セットに過学習 → 失敗
  → Kaggle=0.80324（悪化）
     ↓
ステップ4: BERTweet 単体モデル
  → ツイート専用の事前学習モデルに変更
  → PATIENCE=2 に変更（失敗の反省）・閾値最適化は使わない
  → Kaggle=0.83665
     ↓
ステップ5: K-Fold CV + アンサンブル
  → 全データを活用し、5モデルの予測を平均
  → Kaggle=0.83971
```

### 失敗から学んだこと

| 失敗 | 原因 | 教訓 |
|------|------|------|
| v2 で精度が悪化 | Early Stopping が早すぎた | 過去の実験結果から PATIENCE を設定する |
| 閾値最適化が逆効果 | 検証セット（1,523件）への過学習 | 改善幅が小さいときは使わない |
| OOF F1 < 単体 Val F1 | 単体の検証セットが「偶然易しかった」 | OOF の方が信頼できる指標 |
| v2 で複数の改善を同時に実装 | 何が効いた/効かなかったか不明 | 変更は1つずつ行い、効果を測定する |

---

## 各ステップで使った技術の整理

| ステップ | 主な技術 | 目的 |
|---------|---------|------|
| 1 | TF-IDF、N-gram、Pipeline | テキストを数値に変換、データリーク防止 |
| 2 | BERT、Tokenizer、DataLoader、AdamW | 文脈を理解する深層学習モデル |
| 2 | Warmup スケジューラー、勾配クリッピング | 安定した学習の実現 |
| 2 | 混同行列、FP/FN 分析 | 次の改善方針の特定 |
| 4 | BERTweet、専用前処理規約 | ツイート特有の表現への対応 |
| 4 | Early Stopping | 過学習の自動検知と停止 |
| 5 | K-Fold CV、OOF 予測、確率平均 | 安定した精度と信頼できる評価 |

---

## 機械学習改善の一般的な進め方（まとめ）

精度改善は以下のサイクルを繰り返すことで行う。

```
①  問題を理解する（EDA）
    ↓ テキストの特徴、クラス分布、欠損値を確認
②  シンプルなベースラインを作る
    ↓ 比較の基準（ベースライン）を確立する
③  診断出力で問題を特定する
    ↓ 過学習？未学習？FN > FP？
④  1つの改善を実装して測定する
    ↓ 改善した → 採用、改善しなかった → 廃棄
⑤  Kaggle に提出して実際のスコアを確認する
    ↓ OOF スコアと大きく乖離 → 過学習・データリークを疑う
⑥  ① に戻る
```

> **最も大切なこと**  
> 「どの手法を使うか」ではなく、「何の問題を解決しようとしているのか」。  
> 常に意識しながら改善を進めること。  
> 手法を目的にするのではなく、**「精度を上げるための手段」として使うことが重要**。

---

## さらに精度を上げるために（次のステップ）

本ガイドで到達したスコア（0.83971）からさらに伸ばすには：

| 手法 | 概要 | 期待効果 |
|------|------|---------|
| 疑似ラベリング | 高確信度のテスト予測を学習データに追加 | +0.005〜0.010 程度 |
| マルチモデルアンサンブル | BERTweet + RoBERTa など異なるモデルを平均 | +0.003〜0.008 程度 |
| より大きなモデル | `roberta-large` など | モデルによる |

> **疑似ラベリングの考え方**  
> テスト予測で確率が 0.9 以上（ほぼ確実に災害）または 0.1 以下（ほぼ確実に非災害）の  
> サンプルは信頼できる予測。これらを「正解ラベルとして扱い」、  
> 学習データに追加してもう一度学習すると精度が上がることがある。
