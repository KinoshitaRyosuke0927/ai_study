"""
BERTweet ファインチューニングによる災害ツイート分類
使用モデル: vinai/bertweet-base（ツイート専用 BERT）

distilbert との主な違い:
  1. 850万件のツイートで事前学習 → ツイート特有の略語・口語・絵文字に強い
  2. 前処理の規約: URL → HTTPURL, @mention → @USER（大文字のまま保持）
  3. 大文字・小文字を区別する（lowercase しない）
  4. keyword 特徴量をテキスト先頭に付加（変更点①）
  5. Early Stopping: PATIENCE=2（v2 の 1 より緩やかに設定）
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
MODEL_NAME  = "vinai/bertweet-base"
MAX_LEN     = 128
BATCH_SIZE  = 16
EPOCHS      = 4       # Early Stopping があるので多めに設定
LR          = 2e-5
WARMUP_RATE = 0.1
PATIENCE    = 2       # 2 epoch 改善なしで停止（1 は早すぎた反省から）
SEED        = 42

# ── パス設定 ──────────────────────────────────────────────
DATA_DIR   = Path(__file__).parent.parent / "competitions" / "nlp-getting-started"
OUTPUT_DIR = Path(__file__).parent
OUTPUT_DIR.mkdir(exist_ok=True)

torch.manual_seed(SEED)
np.random.seed(SEED)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"使用デバイス: {device}")

# ── データ読み込み ─────────────────────────────────────────
train_df = pd.read_csv(DATA_DIR / "train.csv")
test_df  = pd.read_csv(DATA_DIR / "test.csv")

# ── BERTweet 専用の前処理 ──────────────────────────────────
# BERTweet の事前学習データと同じ正規化を行う。
# ・URL      → HTTPURL  （BERTweet の語彙に含まれる特殊トークン）
# ・@mention → @USER    （同上）
# ・大文字小文字は区別する（lowercase しない）
# ・ハッシュタグは # ごと残す（BERTweet は # 付きで学習済み）
# ・絵文字も残す（BERTweet は絵文字込みで学習済み）
URL_RE     = re.compile(r"https?://\S+|www\.\S+")
MENTION_RE = re.compile(r"@\w+")
SPACE_RE   = re.compile(r"\s+")

def clean_text(text: str) -> str:
    text = URL_RE.sub("HTTPURL", text)
    text = MENTION_RE.sub("@USER", text)
    text = SPACE_RE.sub(" ", text).strip()
    return text

# keyword を text の先頭に付加（BERTweet にも適用）
# keyword は "wildfire" "earthquake" など災害の種類を直接示す単語。
# 先頭に置くことで BERT の [CLS] トークンが disaster カテゴリの情報を拾いやすくなる。
def build_input(row) -> str:
    keyword = clean_text(str(row["keyword"])) if pd.notna(row["keyword"]) else ""
    text    = clean_text(str(row["text"]))
    if keyword:
        return f"{keyword} {text}"
    return text

train_df["input"] = train_df.apply(build_input, axis=1)
test_df["input"]  = test_df.apply(build_input, axis=1)

# ── トークナイザー読み込み ─────────────────────────────────
print(f"\nモデル読み込み中: {MODEL_NAME}")
# BERTweet は SentencePiece ではなく BPE トークナイザー。
# use_fast=False は安定性のため（fast 版でも動作するが念のため）
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, use_fast=False)

X = train_df["input"].tolist()
y = train_df["target"].tolist()

token_lengths = [len(tokenizer.encode(t, truncation=False)) for t in X]
truncated = sum(1 for l in token_lengths if l > MAX_LEN)
print(f"\n=== トークン長の分布（keyword 付加後 / MAX_LEN={MAX_LEN}） ===")
print(f"  平均: {np.mean(token_lengths):.1f}  中央値: {np.median(token_lengths):.0f}"
      f"  最大: {max(token_lengths)}")
print(f"  切り捨てられるツイート: {truncated}件 ({truncated/len(X)*100:.1f}%)")

# ── Dataset クラス ─────────────────────────────────────────
class TweetDataset(Dataset):
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
            padding="max_length",
            truncation=True,
            return_tensors="pt",
        )
        return {
            "input_ids":      encoding["input_ids"].squeeze(0),
            "attention_mask": encoding["attention_mask"].squeeze(0),
            "labels":         torch.tensor(self.labels[idx], dtype=torch.long),
        }


# ── 学習・評価関数 ─────────────────────────────────────────
LOG_INTERVAL = 50

def train_one_epoch(model, loader, optimizer, scheduler, epoch, total_epochs):
    model.train()
    total_loss = 0.0
    start_time = time.time()

    for step, batch in enumerate(loader, 1):
        input_ids      = batch["input_ids"].to(device)
        attention_mask = batch["attention_mask"].to(device)
        labels         = batch["labels"].to(device)

        optimizer.zero_grad()
        outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
        loss    = outputs.loss
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        scheduler.step()
        total_loss += loss.item()

        if step % LOG_INTERVAL == 0 or step == len(loader):
            elapsed  = time.time() - start_time
            eta      = elapsed / step * (len(loader) - step)
            avg_loss = total_loss / step
            print(f"  Epoch {epoch}/{total_epochs}"
                  f"  [{step:>4}/{len(loader)}]"
                  f"  loss={avg_loss:.4f}"
                  f"  elapsed={elapsed/60:.1f}m"
                  f"  ETA={eta/60:.1f}m")

    return total_loss / len(loader)


def evaluate(model, loader):
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

            probs = torch.softmax(outputs.logits, dim=1)[:, 1]
            preds = torch.argmax(outputs.logits, dim=1)
            all_preds.extend(preds.cpu().numpy())
            all_labels.extend(labels.cpu().numpy())
            all_probs.extend(probs.cpu().numpy())

    f1   = f1_score(all_labels, all_preds)
    loss = total_loss / len(loader)
    return f1, loss, np.array(all_preds), np.array(all_labels), np.array(all_probs)


# ── Train / Validation 分割 ────────────────────────────────
X_train, X_val, y_train, y_val = train_test_split(
    X, y, test_size=0.2, stratify=y, random_state=SEED
)
print(f"\n学習: {len(X_train)}件  検証: {len(X_val)}件")

train_dataset = TweetDataset(X_train, y_train, tokenizer, MAX_LEN)
val_dataset   = TweetDataset(X_val,   y_val,   tokenizer, MAX_LEN)
train_loader  = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True)
val_loader    = DataLoader(val_dataset,   batch_size=BATCH_SIZE, shuffle=False)

# ── モデル・オプティマイザー ───────────────────────────────
model = AutoModelForSequenceClassification.from_pretrained(
    MODEL_NAME, num_labels=2
).to(device)

optimizer    = AdamW(model.parameters(), lr=LR, weight_decay=0.01)
total_steps  = len(train_loader) * EPOCHS
warmup_steps = int(total_steps * WARMUP_RATE)
scheduler    = get_linear_schedule_with_warmup(
    optimizer, num_warmup_steps=warmup_steps, num_training_steps=total_steps
)

# ── 学習ループ（Early Stopping 付き） ─────────────────────
print(f"\n学習開始（最大 {EPOCHS} epochs / Early Stopping patience={PATIENCE}）")
print("=" * 60)

best_f1         = 0.0
best_val_preds  = None
best_val_labels = None
best_val_probs  = None
best_epoch      = 1
patience_count  = 0
epoch_log       = []

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
        best_epoch      = epoch
        patience_count  = 0
        torch.save(model.state_dict(), OUTPUT_DIR / "best_model_bertweet.pt")
    else:
        patience_count += 1
        if patience_count >= PATIENCE:
            print(f"\n  Early Stopping: {PATIENCE} epoch 改善なし → 停止")
            break

# ── 学習曲線サマリ ─────────────────────────────────────────
print(f"\n{'='*60}")
print("=== 学習曲線サマリ ===")
print(f"{'Epoch':>6}  {'train_loss':>10}  {'val_loss':>8}  {'val_F1':>7}")
for row in epoch_log:
    stop = " ← best" if row["epoch"] == best_epoch else ""
    print(f"  {row['epoch']:>4}     {row['train_loss']:>9.4f}  "
          f"{row['val_loss']:>8.4f}  {row['val_f1']:>7.4f}{stop}")

# ── クラス別レポート ──────────────────────────────────────
print(f"\n=== クラス別 Precision / Recall / F1（閾値=0.50）===")
print(classification_report(
    best_val_labels, best_val_preds,
    target_names=["非災害(0)", "災害(1)"],
    digits=4,
))

# ── 混同行列 ──────────────────────────────────────────────
cm = confusion_matrix(best_val_labels, best_val_preds)
tn, fp, fn, tp = cm.ravel()
print(f"=== 混同行列 ===")
print(f"              予測: 非災害  予測: 災害")
print(f"  実際: 非災害    {tn:5d}       {fp:5d}   ← FP")
print(f"  実際: 災害      {fn:5d}       {tp:5d}   ← FN")

# ── 予測確率の分布 ─────────────────────────────────────────
bins = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
print(f"\n=== 予測確率（disaster クラス）の分布 ===")
hist, _ = np.histogram(best_val_probs, bins=bins)
for i, count in enumerate(hist):
    bar = "█" * (count // 5)
    print(f"  {bins[i]:.1f}~{bins[i+1]:.1f}: {count:4d}件  {bar}")

# ── 誤分類サンプル ─────────────────────────────────────────
errors = [
    {"text": X_val[i], "label": best_val_labels[i],
     "pred": best_val_preds[i], "prob": best_val_probs[i]}
    for i in range(len(X_val))
    if best_val_preds[i] != best_val_labels[i]
]
fp_samples = sorted([e for e in errors if e["label"] == 0],
                    key=lambda x: x["prob"], reverse=True)
fn_samples = sorted([e for e in errors if e["label"] == 1],
                    key=lambda x: x["prob"])

print(f"\n=== 誤分類サンプル（FP / 上位5件）===")
for e in fp_samples[:5]:
    print(f"  確率={e['prob']:.3f}  「{e['text'][:80]}」")
print(f"\n=== 誤分類サンプル（FN / 上位5件）===")
for e in fn_samples[:5]:
    print(f"  確率={e['prob']:.3f}  「{e['text'][:80]}」")

print(f"\n{'='*60}")
print(f"Best Val F1（BERTweet）: {best_f1:.4f}")
print(f"distilbert v1          : 0.8101")
print(f"改善幅                 : {best_f1 - 0.8101:+.4f}")

# ── 全データで再学習（best_epoch 分） ────────────────────
print(f"\n全データで再学習（{best_epoch} epochs）...")

full_dataset    = TweetDataset(X, y, tokenizer, MAX_LEN)
full_loader     = DataLoader(full_dataset, batch_size=BATCH_SIZE, shuffle=True)
model_final     = AutoModelForSequenceClassification.from_pretrained(
    MODEL_NAME, num_labels=2
).to(device)
optimizer_final = AdamW(model_final.parameters(), lr=LR, weight_decay=0.01)
total_steps_f   = len(full_loader) * best_epoch
scheduler_final = get_linear_schedule_with_warmup(
    optimizer_final,
    num_warmup_steps=int(total_steps_f * WARMUP_RATE),
    num_training_steps=total_steps_f,
)

for epoch in range(1, best_epoch + 1):
    loss = train_one_epoch(
        model_final, full_loader, optimizer_final, scheduler_final, epoch, best_epoch
    )
    print(f"  Full Epoch {epoch}/{best_epoch}  loss={loss:.4f}")

# ── テストデータ予測 ───────────────────────────────────────
X_test       = test_df["input"].tolist()
y_test_dummy = [0] * len(X_test)
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

submission = pd.DataFrame({"id": test_df["id"], "target": test_preds})
out_path   = OUTPUT_DIR / "submission_bertweet.csv"
submission.to_csv(out_path, index=False)
print(f"\nSubmission saved → {out_path}")
print(submission["target"].value_counts().to_string())
