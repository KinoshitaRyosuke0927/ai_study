"""
BERTweet K-Fold CV + アンサンブル
  5 つの fold で BERTweet をそれぞれ学習し、
  テスト予測確率の平均でアンサンブル（多数決より精度が安定する）。

  所要時間目安（CPU）:
    1 epoch ≈ 30分 / PATIENCE=1 の場合 最大 2 epoch/fold
    → 5 fold × 2 epoch × 30分 ≈ 5 時間（前回 epoch1 が最良だったため目安）

  単一モデルと比べた利点:
    ・全学習データを検証に使える（val データを無駄にしない）
    ・5 モデルの確率平均 → 予測のばらつきが減り汎化性能が向上
    ・OOF F1 がより信頼できる性能指標になる
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
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import f1_score, classification_report, confusion_matrix

# ── 設定 ──────────────────────────────────────────────────
MODEL_NAME  = "vinai/bertweet-base"
MAX_LEN     = 128
BATCH_SIZE  = 16
N_FOLDS     = 5
EPOCHS      = 3       # Early Stopping があるので最大値として設定
LR          = 2e-5
WARMUP_RATE = 0.1
PATIENCE    = 1       # 前回実験で epoch1 が最良 → 1 epoch 改善なしで早期停止
SEED        = 42

# ── パス設定 ──────────────────────────────────────────────
DATA_DIR   = Path(__file__).parent.parent / "competitions" / "nlp-getting-started"
OUTPUT_DIR = Path(__file__).parent
OUTPUT_DIR.mkdir(exist_ok=True)

torch.manual_seed(SEED)
np.random.seed(SEED)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"使用デバイス: {device}")
print(f"設定: {N_FOLDS}-Fold / 最大 {EPOCHS} epochs / PATIENCE={PATIENCE}")

# ── データ読み込み ─────────────────────────────────────────
train_df = pd.read_csv(DATA_DIR / "train.csv")
test_df  = pd.read_csv(DATA_DIR / "test.csv")

# ── BERTweet 専用の前処理 ──────────────────────────────────
URL_RE     = re.compile(r"https?://\S+|www\.\S+")
MENTION_RE = re.compile(r"@\w+")
SPACE_RE   = re.compile(r"\s+")

def clean_text(text: str) -> str:
    text = URL_RE.sub("HTTPURL", text)
    text = MENTION_RE.sub("@USER", text)
    return SPACE_RE.sub(" ", text).strip()

def build_input(row) -> str:
    keyword = clean_text(str(row["keyword"])) if pd.notna(row["keyword"]) else ""
    text    = clean_text(str(row["text"]))
    if keyword:
        return f"{keyword} {text}"
    return text

train_df["input"] = train_df.apply(build_input, axis=1)
test_df["input"]  = test_df.apply(build_input, axis=1)

X = train_df["input"].tolist()
y = train_df["target"].tolist()
X_test = test_df["input"].tolist()

# ── トークナイザー読み込み ─────────────────────────────────
print(f"\nモデル読み込み中: {MODEL_NAME}")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, use_fast=False)

token_lengths = [len(tokenizer.encode(t, truncation=False)) for t in X]
truncated = sum(1 for l in token_lengths if l > MAX_LEN)
print(f"\n=== トークン長の分布（MAX_LEN={MAX_LEN}） ===")
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


# ── 学習・評価・予測関数 ───────────────────────────────────
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
            print(f"  Epoch {epoch}/{total_epochs}"
                  f"  [{step:>4}/{len(loader)}]"
                  f"  loss={total_loss/step:.4f}"
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


def get_probs(model, loader):
    """ラベルなし（テストデータ用）の確率取得"""
    model.eval()
    all_probs = []

    with torch.no_grad():
        for batch in loader:
            input_ids      = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            outputs        = model(input_ids=input_ids, attention_mask=attention_mask)
            probs          = torch.softmax(outputs.logits, dim=1)[:, 1]
            all_probs.extend(probs.cpu().numpy())

    return np.array(all_probs)


# ── テストデータ用 DataLoader（全 fold 共通） ─────────────
test_dataset = TweetDataset(X_test, [0] * len(X_test), tokenizer, MAX_LEN)
test_loader  = DataLoader(test_dataset, batch_size=BATCH_SIZE, shuffle=False)

# ── K-Fold ループ ──────────────────────────────────────────
# OOF: 各 fold の val 予測を集約 → 全学習データをカバーする確率配列
# test_probs_sum: 各 fold のテスト予測確率を積算 → 最後に N_FOLDS で割って平均
oof_probs     = np.zeros(len(train_df))
test_probs_sum = np.zeros(len(test_df))
fold_results   = []

skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED)
total_start = time.time()

for fold, (train_idx, val_idx) in enumerate(skf.split(X, y), 1):
    fold_start = time.time()
    print(f"\n{'='*60}")
    print(f"Fold {fold}/{N_FOLDS}  "
          f"(学習: {len(train_idx)}件  検証: {len(val_idx)}件)")
    print("=" * 60)

    X_train_f = [X[i] for i in train_idx]
    y_train_f = [y[i] for i in train_idx]
    X_val_f   = [X[i] for i in val_idx]
    y_val_f   = [y[i] for i in val_idx]

    train_dataset = TweetDataset(X_train_f, y_train_f, tokenizer, MAX_LEN)
    val_dataset   = TweetDataset(X_val_f,   y_val_f,   tokenizer, MAX_LEN)
    train_loader  = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True)
    val_loader    = DataLoader(val_dataset,   batch_size=BATCH_SIZE, shuffle=False)

    # モデル・オプティマイザー（fold ごとに初期化）
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME, num_labels=2
    ).to(device)
    optimizer    = AdamW(model.parameters(), lr=LR, weight_decay=0.01)
    total_steps  = len(train_loader) * EPOCHS
    warmup_steps = int(total_steps * WARMUP_RATE)
    scheduler    = get_linear_schedule_with_warmup(
        optimizer, num_warmup_steps=warmup_steps, num_training_steps=total_steps
    )

    # 学習ループ（Early Stopping 付き）
    best_f1        = 0.0
    best_epoch     = 1
    patience_count = 0
    epoch_log      = []
    model_path     = OUTPUT_DIR / f"model_fold{fold}.pt"

    for epoch in range(1, EPOCHS + 1):
        print(f"\n--- Fold {fold} / Epoch {epoch}/{EPOCHS} ---")
        train_loss = train_one_epoch(
            model, train_loader, optimizer, scheduler, epoch, EPOCHS
        )
        val_f1, val_loss, _, _, _ = evaluate(model, val_loader)
        epoch_log.append({"epoch": epoch, "train_loss": train_loss,
                          "val_loss": val_loss, "val_f1": val_f1})

        mark = " ★ best" if val_f1 > best_f1 else ""
        print(f"  → train_loss={train_loss:.4f}  "
              f"val_loss={val_loss:.4f}  val_F1={val_f1:.4f}{mark}")

        if val_f1 > best_f1:
            best_f1        = val_f1
            best_epoch     = epoch
            patience_count = 0
            torch.save(model.state_dict(), model_path)
        else:
            patience_count += 1
            if patience_count >= PATIENCE:
                print(f"  Early Stopping: {PATIENCE} epoch 改善なし → 停止")
                break

    # best モデルを読み込んで OOF とテスト予測を取得
    model.load_state_dict(torch.load(model_path, weights_only=True))

    _, _, _, val_labels, val_probs = evaluate(model, val_loader)
    oof_probs[val_idx] = val_probs                            # OOF に記録

    fold_test_probs  = get_probs(model, test_loader)
    test_probs_sum  += fold_test_probs                        # fold ごとに積算

    fold_elapsed = (time.time() - fold_start) / 60
    fold_results.append({
        "fold": fold, "val_f1": best_f1,
        "best_epoch": best_epoch, "elapsed_min": fold_elapsed,
    })
    print(f"\n  Fold {fold} 完了: best_epoch={best_epoch}  "
          f"val_F1={best_f1:.4f}  所要時間={fold_elapsed:.1f}分")

    # モデルファイルを削除（ディスク節約）
    model_path.unlink()

# ── アンサンブル結果の集計 ─────────────────────────────────
total_elapsed = (time.time() - total_start) / 60
test_probs_avg = test_probs_sum / N_FOLDS        # 5 fold の確率平均

print(f"\n\n{'='*60}")
print(f"=== K-Fold 完了（合計 {total_elapsed:.1f}分） ===")
print(f"{'='*60}")

# ── per-fold サマリ ────────────────────────────────────────
print(f"\n=== Fold ごとの結果 ===")
print(f"{'Fold':>5}  {'Val F1':>8}  {'Best Epoch':>10}  {'時間(分)':>8}")
for r in fold_results:
    print(f"  {r['fold']:>3}    {r['val_f1']:>7.4f}    {r['best_epoch']:>9}    {r['elapsed_min']:>7.1f}")
fold_f1s = [r["val_f1"] for r in fold_results]
print(f"  平均   {np.mean(fold_f1s):>7.4f}    ±{np.std(fold_f1s):.4f}")

# ── OOF 全体の F1（最も信頼できる性能指標） ─────────────────
# OOF: 各サンプルが「自分が含まれていない fold のモデル」で予測された確率
# → データリークなし・学習データ全体をカバーした公正な評価
oof_preds = (oof_probs >= 0.5).astype(int)
oof_f1    = f1_score(y, oof_preds)

print(f"\n=== OOF F1（全学習データへの予測から算出） ===")
print(f"  OOF F1         : {oof_f1:.4f}")
print(f"  Fold 平均 F1   : {np.mean(fold_f1s):.4f}")
print(f"  distilbert v1  : 0.8101")
print(f"  BERTweet 単体  : 0.8259")
print(f"  改善幅（vs 単体）: {oof_f1 - 0.8259:+.4f}")

# ── OOF のクラス別レポート ─────────────────────────────────
print(f"\n=== クラス別 Precision / Recall / F1（OOF / 閾値=0.50）===")
print(classification_report(
    y, oof_preds,
    target_names=["非災害(0)", "災害(1)"],
    digits=4,
))

# ── OOF 混同行列 ──────────────────────────────────────────
cm = confusion_matrix(y, oof_preds)
tn, fp, fn, tp = cm.ravel()
print(f"=== 混同行列（OOF） ===")
print(f"              予測: 非災害  予測: 災害")
print(f"  実際: 非災害    {tn:5d}       {fp:5d}   ← FP")
print(f"  実際: 災害      {fn:5d}       {tp:5d}   ← FN")

# ── 予測確率の分布（アンサンブル後） ─────────────────────
bins = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
print(f"\n=== テスト予測確率（5 fold 平均）の分布 ===")
hist, _ = np.histogram(test_probs_avg, bins=bins)
for i, count in enumerate(hist):
    bar = "█" * (count // 5)
    print(f"  {bins[i]:.1f}~{bins[i+1]:.1f}: {count:4d}件  {bar}")

# ── 提出ファイル生成 ───────────────────────────────────────
test_preds = (test_probs_avg >= 0.5).astype(int)
submission = pd.DataFrame({"id": test_df["id"], "target": test_preds})
out_path   = OUTPUT_DIR / "submission_bertweet_kfold.csv"
submission.to_csv(out_path, index=False)
print(f"\nSubmission saved → {out_path}")
print(submission["target"].value_counts().to_string())
