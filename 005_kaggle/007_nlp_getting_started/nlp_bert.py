"""
BERT ファインチューニングによる災害ツイート分類
使用モデル: distilbert-base-uncased（BERT の軽量版）
"""
import re
import time
import numpy as np
import pandas as pd
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from transformers import get_linear_schedule_with_warmup
from torch.optim import AdamW
from sklearn.model_selection import train_test_split
from sklearn.metrics import f1_score, classification_report, confusion_matrix

# ── 設定 ──────────────────────────────────────────────────
MODEL_NAME  = "distilbert-base-uncased"   # BERT 軽量版（速度優先）
MAX_LEN     = 128    # ツイートは短い（最大157文字）ので128で十分
BATCH_SIZE  = 16     # CPU 環境では小さめに設定
EPOCHS      = 3      # BERT は 2〜4 epoch が過学習しにくい
LR          = 2e-5   # BERT ファインチューニングの標準的な学習率
WARMUP_RATE = 0.1    # 全ステップの 10% をウォームアップに使う
SEED        = 42

# ── パス設定 ──────────────────────────────────────────────
DATA_DIR   = Path(__file__).parent.parent / "competitions" / "nlp-getting-started"
OUTPUT_DIR = Path(__file__).parent
OUTPUT_DIR.mkdir(exist_ok=True)

# ── 再現性の確保 ───────────────────────────────────────────
torch.manual_seed(SEED)
np.random.seed(SEED)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"使用デバイス: {device}")

# ── データ読み込み・前処理 ─────────────────────────────────
train_df = pd.read_csv(DATA_DIR / "train.csv")
test_df  = pd.read_csv(DATA_DIR / "test.csv")

URL_RE      = re.compile(r"https?://\S+")
MENTION_RE  = re.compile(r"@\w+")
HASHTAG_RE  = re.compile(r"#(\w+)")
NONALPHA_RE = re.compile(r"[^a-zA-Z\s]")

def clean_text(text: str) -> str:
    text = URL_RE.sub("", text)
    text = MENTION_RE.sub("", text)
    text = HASHTAG_RE.sub(r"\1", text)
    text = NONALPHA_RE.sub(" ", text)
    return text.lower().strip()

train_df["clean_text"] = train_df["text"].apply(clean_text)
test_df["clean_text"]  = test_df["text"].apply(clean_text)

# ── Dataset クラス ─────────────────────────────────────────
class TweetDataset(Dataset):
    """
    BERT の入力形式に変換する Dataset クラス。
    tokenizer がテキストを token_ids・attention_mask に変換する。
    """
    def __init__(self, texts, labels, tokenizer, max_len):
        self.texts     = texts
        self.labels    = labels
        self.tokenizer = tokenizer
        self.max_len   = max_len

    def __len__(self):
        return len(self.texts)

    def __getitem__(self, idx):
        encoding = self.tokenizer(
            self.texts[idx],
            max_length=self.max_len,
            padding="max_length",   # MAX_LEN に満たない場合は [PAD] で埋める
            truncation=True,        # MAX_LEN を超える場合は切り捨て
            return_tensors="pt",
        )
        return {
            "input_ids":      encoding["input_ids"].squeeze(0),
            "attention_mask": encoding["attention_mask"].squeeze(0),
            "labels":         torch.tensor(self.labels[idx], dtype=torch.long),
        }


# ── 学習・評価関数 ─────────────────────────────────────────
LOG_INTERVAL = 50   # 何バッチごとに進捗を表示するか

def train_one_epoch(model, loader, optimizer, scheduler, epoch, total_epochs):
    model.train()
    total_loss  = 0.0
    start_time  = time.time()

    for step, batch in enumerate(loader, 1):
        input_ids      = batch["input_ids"].to(device)
        attention_mask = batch["attention_mask"].to(device)
        labels         = batch["labels"].to(device)

        optimizer.zero_grad()
        outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
        loss    = outputs.loss
        loss.backward()

        # 勾配クリッピング：勾配が大きくなりすぎて学習が不安定になるのを防ぐ
        nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)

        optimizer.step()
        scheduler.step()
        total_loss += loss.item()

        # 進捗表示（print のコストはニューラルネットの計算に比べて無視できる）
        if step % LOG_INTERVAL == 0 or step == len(loader):
            elapsed   = time.time() - start_time
            eta       = elapsed / step * (len(loader) - step)
            avg_loss  = total_loss / step
            print(f"  Epoch {epoch}/{total_epochs}"
                  f"  [{step:>4}/{len(loader)}]"
                  f"  loss={avg_loss:.4f}"
                  f"  elapsed={elapsed/60:.1f}m"
                  f"  ETA={eta/60:.1f}m")

    return total_loss / len(loader)


def evaluate(model, loader):
    """評価に加えて、精度分析用の確率・ラベル・予測を返す"""
    model.eval()
    all_preds, all_labels, all_probs = [], [], []
    total_loss = 0.0

    with torch.no_grad():
        for batch in loader:
            input_ids      = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels         = batch["labels"].to(device)

            outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
            total_loss += outputs.loss.item()

            probs = torch.softmax(outputs.logits, dim=1)[:, 1]   # 災害クラスの確率
            preds = torch.argmax(outputs.logits, dim=1)
            all_preds.extend(preds.cpu().numpy())
            all_labels.extend(labels.cpu().numpy())
            all_probs.extend(probs.cpu().numpy())

    f1   = f1_score(all_labels, all_preds)
    loss = total_loss / len(loader)
    return f1, loss, np.array(all_preds), np.array(all_labels), np.array(all_probs)


# ── トークナイザー読み込み ─────────────────────────────────
print(f"\nモデル読み込み中: {MODEL_NAME}")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

# ── トークン長の分布確認（次回改善の参考情報） ────────────
X = train_df["clean_text"].tolist()
y = train_df["target"].tolist()

token_lengths = [
    len(tokenizer.encode(text, truncation=False)) for text in X
]
truncated = sum(1 for l in token_lengths if l > MAX_LEN)
print(f"\n=== トークン長の分布（MAX_LEN={MAX_LEN}） ===")
print(f"  平均: {np.mean(token_lengths):.1f}  中央値: {np.median(token_lengths):.0f}"
      f"  最大: {max(token_lengths)}")
print(f"  MAX_LEN を超えて切り捨てられるツイート: {truncated}件"
      f" ({truncated/len(X)*100:.1f}%)")
print(f"  → 切り捨て率が高い場合は MAX_LEN を増やすことで改善できる可能性あり")

# ── Train / Validation 分割 ────────────────────────────────
# BERT は学習に時間がかかるため、まず 80/20 の 1分割で性能を確認する
X_train, X_val, y_train, y_val = train_test_split(
    X, y, test_size=0.2, stratify=y, random_state=SEED
)
print(f"\n学習: {len(X_train)}件  検証: {len(X_val)}件")

# ── DataLoader の作成 ──────────────────────────────────────
train_dataset = TweetDataset(X_train, y_train, tokenizer, MAX_LEN)
val_dataset   = TweetDataset(X_val,   y_val,   tokenizer, MAX_LEN)

train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True)
val_loader   = DataLoader(val_dataset,   batch_size=BATCH_SIZE, shuffle=False)

# ── モデル・オプティマイザーの定義 ────────────────────────
model = AutoModelForSequenceClassification.from_pretrained(
    MODEL_NAME,
    num_labels=2,   # 0: 非災害, 1: 災害
)
model = model.to(device)

optimizer = AdamW(model.parameters(), lr=LR, weight_decay=0.01)

total_steps   = len(train_loader) * EPOCHS
warmup_steps  = int(total_steps * WARMUP_RATE)

# 学習率スケジューラー：最初はゆっくり上げて（ウォームアップ）、その後線形に下げる
scheduler = get_linear_schedule_with_warmup(
    optimizer,
    num_warmup_steps=warmup_steps,
    num_training_steps=total_steps,
)

# ── 学習ループ ─────────────────────────────────────────────
print(f"\n学習開始（{EPOCHS} epochs / デバイス: {device}）")
print(f"総ステップ数: {total_steps}  ウォームアップ: {warmup_steps}ステップ")
print("=" * 60)

best_f1          = 0.0
best_val_preds   = None
best_val_labels  = None
best_val_probs   = None
epoch_log        = []   # 学習曲線の記録

for epoch in range(1, EPOCHS + 1):
    print(f"\n--- Epoch {epoch}/{EPOCHS} 学習中 ---")
    train_loss = train_one_epoch(
        model, train_loader, optimizer, scheduler, epoch, EPOCHS
    )
    val_f1, val_loss, val_preds, val_labels, val_probs = evaluate(model, val_loader)

    epoch_log.append({
        "epoch": epoch, "train_loss": train_loss,
        "val_loss": val_loss, "val_f1": val_f1,
    })

    mark = " ★ best" if val_f1 > best_f1 else ""
    print(f"  → train_loss={train_loss:.4f}  "
          f"val_loss={val_loss:.4f}  "
          f"val_F1={val_f1:.4f}{mark}")

    if val_f1 > best_f1:
        best_f1         = val_f1
        best_val_preds  = val_preds
        best_val_labels = val_labels
        best_val_probs  = val_probs
        torch.save(model.state_dict(), OUTPUT_DIR / "best_model.pt")

# ── 学習曲線サマリ（過学習・未学習の確認） ────────────────
print(f"\n{'='*60}")
print("=== 学習曲線サマリ ===")
print(f"{'Epoch':>6}  {'train_loss':>10}  {'val_loss':>8}  {'val_F1':>7}")
for row in epoch_log:
    print(f"  {row['epoch']:>4}     {row['train_loss']:>9.4f}  "
          f"{row['val_loss']:>8.4f}  {row['val_f1']:>7.4f}")

# ── クラス別詳細レポート（次回改善の判断材料） ────────────
print(f"\n=== クラス別 Precision / Recall / F1 ===")
print(classification_report(
    best_val_labels, best_val_preds,
    target_names=["非災害(0)", "災害(1)"],
    digits=4,
))
print("  → Recall が低いクラスは「見逃し」が多い（閾値調整や重み付けで改善できる可能性あり）")

# ── 混同行列 ──────────────────────────────────────────────
cm = confusion_matrix(best_val_labels, best_val_preds)
tn, fp, fn, tp = cm.ravel()
print(f"\n=== 混同行列 ===")
print(f"              予測: 非災害  予測: 災害")
print(f"  実際: 非災害    {tn:5d}       {fp:5d}   ← FP（非災害を誤って災害と判定）")
print(f"  実際: 災害      {fn:5d}       {tp:5d}   ← FN（災害を見逃した）")

# ── 予測確率の分布（モデルの自信度の確認） ────────────────
bins = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
print(f"\n=== 予測確率（disaster クラス）の分布 ===")
hist, _ = np.histogram(best_val_probs, bins=bins)
for i, count in enumerate(hist):
    bar = "█" * (count // 5)
    print(f"  {bins[i]:.1f}~{bins[i+1]:.1f}: {count:4d}件  {bar}")
print("  → 0.4〜0.6 に集中している場合、モデルが判断に迷っているサンプルが多い")

# ── 誤分類サンプルの分析（改善の手がかり） ────────────────
val_texts = X_val
errors = [
    {"text": val_texts[i], "label": best_val_labels[i],
     "pred": best_val_preds[i], "prob": best_val_probs[i]}
    for i in range(len(val_texts))
    if best_val_preds[i] != best_val_labels[i]
]

# FP: 非災害なのに災害と予測（確率が高い順）
fp_samples = sorted(
    [e for e in errors if e["label"] == 0],
    key=lambda x: x["prob"], reverse=True
)
# FN: 災害なのに非災害と予測（確率が低い順）
fn_samples = sorted(
    [e for e in errors if e["label"] == 1],
    key=lambda x: x["prob"]
)

print(f"\n=== 誤分類サンプル（FP: 非災害を災害と誤判定 / 上位5件）===")
for e in fp_samples[:5]:
    print(f"  確率={e['prob']:.3f}  「{e['text'][:80]}」")

print(f"\n=== 誤分類サンプル（FN: 災害を見逃し / 上位5件）===")
for e in fn_samples[:5]:
    print(f"  確率={e['prob']:.3f}  「{e['text'][:80]}」")

print(f"\n{'='*60}")
print(f"Best Val F1 : {best_f1:.4f}")
print(f"baseline F1 : 0.7470  (TF-IDF + LogReg)")
print(f"改善幅      : {best_f1 - 0.7470:+.4f}")

# ── 全データで再学習 → テスト予測 ─────────────────────────
print("\n全データで再学習してテスト予測を生成...")

full_dataset = TweetDataset(X, y, tokenizer, MAX_LEN)
full_loader  = DataLoader(full_dataset, batch_size=BATCH_SIZE, shuffle=True)

# モデルを初期化して全データで再学習
model_final = AutoModelForSequenceClassification.from_pretrained(
    MODEL_NAME, num_labels=2
).to(device)

optimizer_final = AdamW(model_final.parameters(), lr=LR, weight_decay=0.01)
total_steps_f   = len(full_loader) * EPOCHS
scheduler_final = get_linear_schedule_with_warmup(
    optimizer_final,
    num_warmup_steps=int(total_steps_f * WARMUP_RATE),
    num_training_steps=total_steps_f,
)

for epoch in range(1, EPOCHS + 1):
    loss = train_one_epoch(
        model_final, full_loader, optimizer_final, scheduler_final, epoch, EPOCHS
    )
    print(f"  Full Epoch {epoch}/{EPOCHS}  loss={loss:.4f}")

# テストデータ予測
X_test       = test_df["clean_text"].tolist()
y_test_dummy = [0] * len(X_test)   # ラベルなし（ダミー）
test_dataset = TweetDataset(X_test, y_test_dummy, tokenizer, MAX_LEN)
test_loader  = DataLoader(test_dataset, batch_size=BATCH_SIZE, shuffle=False)

model_final.eval()
test_preds = []
with torch.no_grad():
    for batch in test_loader:
        input_ids      = batch["input_ids"].to(device)
        attention_mask = batch["attention_mask"].to(device)
        outputs        = model_final(input_ids=input_ids, attention_mask=attention_mask)
        preds          = torch.argmax(outputs.logits, dim=1)
        test_preds.extend(preds.cpu().numpy())

# ── 提出ファイル生成 ───────────────────────────────────────
submission = pd.DataFrame({"id": test_df["id"], "target": test_preds})
out_path   = OUTPUT_DIR / "submission_bert.csv"
submission.to_csv(out_path, index=False)
print(f"\nSubmission saved → {out_path}")
print(submission["target"].value_counts().to_string())
