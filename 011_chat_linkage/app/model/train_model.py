"""ラベル付けした投稿データ(pickup_flag,user,text 形式のCSV)を用いて、
日本語BERTをファインチューニングし、投稿ごとに「リマインドが必要か」を
0~1のスコアで判定するモデルを学習するスクリプト。

実行方法: 011_chat_linkage ディレクトリで
    python -m app.model.train_model
学習済みモデルは app/model/reminder_classifier/ に保存される。
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import precision_recall_fscore_support
from sklearn.model_selection import train_test_split
from torch.nn import CrossEntropyLoss
from torch.utils.data import Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)

MODEL_NAME = "cl-tohoku/bert-base-japanese-v3"
DATA_DIR = Path(__file__).resolve().parent / "train_data"
# ラベル付け済みCSV(同じ pickup_flag,user,text 形式であれば複数まとめて学習に使う)
TRAIN_DATA_FILES = [DATA_DIR / "train_data.csv", DATA_DIR / "collected_posts.csv"]
OUTPUT_DIR = Path(__file__).resolve().parent / "reminder_classifier"
MAX_LENGTH = 256
VAL_RATIO = 0.15
RANDOM_SEED = 42


def load_labeled_posts() -> tuple[list[str], list[int]]:
    """
    TRAIN_DATA_FILES に列挙したラベル付けCSVを読み込み、テキストとラベルのリストを返す

    Returns
    -----------------
    - texts: list[str],    投稿本文のリスト
    - labels: list[int],   各投稿に対応するラベル(0または1)のリスト

    """
    # 入れ物用意
    texts: list[str] = []
    labels: list[int] = []
    # 指定された全CSVファイルについて処理
    for path in TRAIN_DATA_FILES:
        # ファイルが存在しない場合はスキップ
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as f:
            # 1行(1投稿)ずつ処理
            for row in csv.DictReader(f):
                flag = row["pickup_flag"].strip()
                text = row["text"].strip()
                # ラベルが0/1以外、またはテキストが空の行は学習対象外として除外
                if flag not in ("0", "1") or not text:
                    continue
                # テキストとラベルをそれぞれ追加
                texts.append(text)
                labels.append(int(flag))
    return texts, labels


class ReminderDataset(Dataset):
    """トークナイズ済みの投稿本文とラベルを、Trainerに渡せる形式でまとめるDataset。"""

    def __init__(self, encodings, labels: list[int]):
        self.encodings = encodings
        self.labels = labels

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, idx: int) -> dict:
        # idx番目のトークナイズ結果(input_ids, attention_maskなど)を取り出す
        item = {key: value[idx] for key, value in self.encodings.items()}
        # 対応するラベルを追加
        item["labels"] = torch.tensor(self.labels[idx])
        return item


class WeightedTrainer(Trainer):
    """0/1のクラス不均衡を補正するため、クラス重み付きCrossEntropyLossを使うTrainer。"""

    def __init__(self, *args, class_weights: torch.Tensor, **kwargs):
        super().__init__(*args, **kwargs)
        self.class_weights = class_weights

    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        # 入力からラベルを取り出す
        labels = inputs.pop("labels")
        # モデルにテキストを入力し、ロジット(分類スコア)を取得
        outputs = model(**inputs)
        logits = outputs.logits
        # クラス重み付きの損失関数で誤差を計算
        loss_fct = CrossEntropyLoss(weight=self.class_weights.to(logits.device))
        loss = loss_fct(logits, labels)
        return (loss, outputs) if return_outputs else loss


def compute_metrics(eval_pred) -> dict:
    """
    Trainerの評価時に呼び出され、検証データでのprecision/recall/f1を算出する

    Args
    -----------------
    - eval_pred: EvalPrediction,  モデルの出力ロジットと正解ラベルの組

    Returns
    -----------------
    - metrics: dict,   precision・recall・f1 を含む評価指標の辞書

    """
    logits, labels = eval_pred
    # ロジットが大きい方のクラス(0または1)を予測ラベルとする
    preds = np.argmax(logits, axis=1)
    # 正解ラベルと予測ラベルからprecision/recall/f1を算出
    precision, recall, f1, _ = precision_recall_fscore_support(
        labels, preds, average="binary", zero_division=0
    )
    return {"precision": precision, "recall": recall, "f1": f1}


def main() -> None:
    """
    ラベル付けCSVを読み込み、日本語BERT(MODEL_NAME)をファインチューニングして、
    学習済みモデルを OUTPUT_DIR に保存する
    """
    # ラベル付けCSVから学習データを読み込む
    texts, labels = load_labeled_posts()
    num_pos_all = sum(labels)
    print(f"学習データ: {len(texts)}件 (1(要リマインド)={num_pos_all}件, 0={len(labels) - num_pos_all}件)")

    # 学習用・検証用データに分割(ラベルの比率を保ったまま分割する)
    train_texts, val_texts, train_labels, val_labels = train_test_split(
        texts, labels, test_size=VAL_RATIO, random_state=RANDOM_SEED, stratify=labels
    )

    # 日本語BERTのトークナイザーでテキストをトークナイズ
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    train_encodings = tokenizer(
        train_texts, truncation=True, padding=True, max_length=MAX_LENGTH, return_tensors="pt"
    )
    val_encodings = tokenizer(
        val_texts, truncation=True, padding=True, max_length=MAX_LENGTH, return_tensors="pt"
    )

    # Trainerに渡すDatasetを作成
    train_dataset = ReminderDataset(train_encodings, train_labels)
    val_dataset = ReminderDataset(val_encodings, val_labels)

    # 事前学習済みの日本語BERTに、2クラス分類用のヘッドを追加してロード
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME, num_labels=2)

    # 0/1のクラス不均衡を補正するため、少数派クラス(1)側の重みを大きくする
    num_pos = sum(train_labels)
    num_neg = len(train_labels) - num_pos
    class_weights = torch.tensor([1.0, num_neg / num_pos], dtype=torch.float)

    # 学習条件(エポック数・バッチサイズ・学習率など)を設定
    training_args = TrainingArguments(
        output_dir=str(OUTPUT_DIR / "checkpoints"),
        num_train_epochs=5,
        per_device_train_batch_size=8,
        per_device_eval_batch_size=8,
        learning_rate=2e-5,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=1,
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        logging_steps=20,
        seed=RANDOM_SEED,
    )

    # クラス重み付きの損失関数を使うTrainerを用意
    trainer = WeightedTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        compute_metrics=compute_metrics,
        class_weights=class_weights,
    )

    # ファインチューニングを実行
    trainer.train()
    # 検証データで最終的な精度を評価
    eval_result = trainer.evaluate()
    print("検証データでの評価結果:", eval_result)

    # 学習済みモデル・トークナイザーを保存
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(OUTPUT_DIR))
    tokenizer.save_pretrained(str(OUTPUT_DIR))
    print(f"学習済みモデルを {OUTPUT_DIR} に保存しました。")


if __name__ == "__main__":
    main()
