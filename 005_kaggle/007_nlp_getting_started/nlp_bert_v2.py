"""
BERT v2: キーワード特徴量の追加 + 閾値最適化
  変更点①: keyword を text の先頭に付加して文脈情報を追加
  変更点②: 検証データで F1 が最大になる確率閾値を探索して適用
  変更点③: Early Stopping で過学習エポックの無駄をカット
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
MODEL_NAME  = "distilbert-base-uncased"
MAX_LEN     = 128
BATCH_SIZE  = 16
EPOCHS      = 4      # Early Stopping があるので多めに設定
LR          = 2e-5
WARMUP_RATE = 0.1
PATIENCE    = 1      # 検証 F1 が PATIENCE epoch 改善しなければ停止
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

# ── テキスト前処理 ─────────────────────────────────────────
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

# ── 変更点①：keyword を text の先頭に付加 ────────────────
# keyword は「wildfire」「earthquake」など災害の種類を示す明示的な単語。
# BERT への入力を "wildfire forest fire near canada" のように変換することで、
# 「この tweet がどんな disaster に関するものか」をモデルに直接伝えられる。
def build_input(row) -> str:
    keyword = str(row["keyword"]) if pd.notna(row["keyword"]) else ""
    text    = clean_text(str(row["text"]))
    keyword = clean_text(keyword)
    if keyword:
        return f"{keyword} {text}"   # "wildfire forest fire near canada"
    return text

train_df["input"] = train_df.apply(build_input, axis=1)
test_df["input"]  = test_df.apply(build_input, axis=1)

# keyword 付加によるトークン長の変化を確認
print(f"\nモデル読み込み中: {MODEL_NAME}")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

X = train_df["input"].tolist()
y = train_df["target"].tolist()

token_lengths = [len(tokenizer.encode(t, truncation=False)) for t in X]
truncated = sum(1 for l in token_lengths if l > MAX_LEN)
print(f"\n=== トークン長の分布（keyword 追加後 / MAX_LEN={MAX_LEN}） ===")
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


# ── 変更点②：閾値を探索する関数 ──────────────────────────
# 確率 prob >= threshold なら「災害」と判定する。
# threshold=0.5 が標準だが、FN>FP の場合は低くした方が F1 が上がる。
def find_best_threshold(labels, probs):
    best_thresh = 0.5
    best_f1     = 0.0
    for thresh in np.arange(0.30, 0.71, 0.01):
        preds = (probs >= thresh).astype(int)
        score = f1_score(labels, preds)
        if score > best_f1:
            best_f1     = score
            best_thresh = thresh
    return best_thresh, best_f1


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
best_val_probs  = None
best_val_labels = None
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
        best_val_probs  = val_probs
        best_val_labels = val_labels
        best_epoch      = epoch
        patience_count  = 0
        torch.save(model.state_dict(), OUTPUT_DIR / "best_model_v2.pt")
    else:
        patience_count += 1
        if patience_count >= PATIENCE:
            print(f"\n  Early Stopping: {PATIENCE} epoch 改善なし → 停止")
            break

# ── 変更点②：閾値最適化 ───────────────────────────────────
best_thresh, thresh_f1 = find_best_threshold(best_val_labels, best_val_probs)

print(f"\n{'='*60}")
print(f"=== 閾値最適化の結果 ===")
print(f"  デフォルト閾値 0.50 : F1={f1_score(best_val_labels, (best_val_probs >= 0.50).astype(int)):.4f}")
print(f"  最適閾値     {best_thresh:.2f} : F1={thresh_f1:.4f}  ← この閾値を予測に使用")

# 学習曲線サマリ
print(f"\n=== 学習曲線サマリ ===")
print(f"{'Epoch':>6}  {'train_loss':>10}  {'val_loss':>8}  {'val_F1':>7}")
for row in epoch_log:
    stop = " ← best" if row["epoch"] == best_epoch else ""
    print(f"  {row['epoch']:>4}     {row['train_loss']:>9.4f}  "
          f"{row['val_loss']:>8.4f}  {row['val_f1']:>7.4f}{stop}")

# クラス別レポート（最適閾値適用後）
opt_preds = (best_val_probs >= best_thresh).astype(int)
print(f"\n=== クラス別 Precision / Recall / F1（閾値={best_thresh:.2f}）===")
print(classification_report(
    best_val_labels, opt_preds,
    target_names=["非災害(0)", "災害(1)"],
    digits=4,
))

# 混同行列（最適閾値適用後）
cm = confusion_matrix(best_val_labels, opt_preds)
tn, fp, fn, tp = cm.ravel()
print(f"=== 混同行列（閾値={best_thresh:.2f}）===")
print(f"              予測: 非災害  予測: 災害")
print(f"  実際: 非災害    {tn:5d}       {fp:5d}   ← FP")
print(f"  実際: 災害      {fn:5d}       {tp:5d}   ← FN")

# 誤分類サンプル
errors = [
    {"text": X_val[i], "label": best_val_labels[i],
     "pred": opt_preds[i], "prob": best_val_probs[i]}
    for i in range(len(X_val))
    if opt_preds[i] != best_val_labels[i]
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
print(f"Best Val F1（閾値=0.50）: {best_f1:.4f}")
print(f"Best Val F1（閾値最適化）: {thresh_f1:.4f}  ({thresh_f1 - best_f1:+.4f})")
print(f"v1 BERT    : 0.8101")
print(f"改善幅     : {thresh_f1 - 0.8101:+.4f}")

# ── 全データで再学習（best_epoch 分だけ） ────────────────
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

# テストデータ予測（最適閾値を適用）
X_test       = test_df["input"].tolist()
y_test_dummy = [0] * len(X_test)
test_dataset = TweetDataset(X_test, y_test_dummy, tokenizer, MAX_LEN)
test_loader  = DataLoader(test_dataset, batch_size=BATCH_SIZE, shuffle=False)

model_final.eval()
test_probs = []
with torch.no_grad():
    for batch in test_loader:
        input_ids      = batch["input_ids"].to(device)
        attention_mask = batch["attention_mask"].to(device)
        outputs        = model_final(input_ids=input_ids, attention_mask=attention_mask)
        probs          = torch.softmax(outputs.logits, dim=1)[:, 1]
        test_probs.extend(probs.cpu().numpy())

# 最適閾値で 0/1 に変換
test_preds = (np.array(test_probs) >= best_thresh).astype(int)

submission = pd.DataFrame({"id": test_df["id"], "target": test_preds})
out_path   = OUTPUT_DIR / "submission_bert_v2.csv"
submission.to_csv(out_path, index=False)
print(f"\nSubmission saved → {out_path}")
print(f"使用した閾値: {best_thresh:.2f}")
print(submission["target"].value_counts().to_string())
