"""「暗黙知共有」の★評価値を学習し、未評価アイテムに評価値を予測するモデル。

- train_model(): rating(★評価)済みアイテムを教師データに回帰モデルを学習し、
  ローカルファイル(storage/tacit_models/)へ保存する。
- predict_ratings(): 学習済みモデルで、未評価アイテムの評価値を予測する。

特徴量は暗黙知の本文(content)を埋め込みベクトル化したもの(pipeline.ai.AiAnalyzer。
Azure OpenAI 未設定時は決定的なハッシュ埋め込みにフォールバック)。評価値(0〜5)を
連続値として回帰する(Ridge回帰)。学習件数が少ない前提のため、次元数に対して
サンプル数が少なくても過学習しにくい線形回帰 + 正則化を採用している。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from config.settings import Settings

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).resolve().parents[1] / "storage" / "tacit_models"
MIN_TRAINING_ITEMS = 5     # これ未満の評価済み件数では学習しない
MIN_ITEMS_FOR_VALIDATION = 10  # これ以上なら学習/検証を分けて精度を確認する


class TacitTrainingError(Exception):
    """学習データ不足、または学習・予測に失敗した場合。"""


def _embed(settings: Settings, texts: list[str]) -> tuple[list[list[float]], str]:
    from pipeline.ai import AiAnalyzer

    analyzer = AiAnalyzer(settings)
    return analyzer.embed_texts(texts)


def train_model(settings: Settings, run_id: int, items: list[dict[str, Any]]) -> dict[str, Any]:
    """rating 済みアイテムから回帰モデルを学習し、保存する。

    Args
    -----------------
    - items: [{"id", "content", "rating"}, ...](rating は 0〜5 の数値)

    Returns
    -----------------
    - {"model_path", "feature_dim", "training_item_count", "metrics"}
    """
    if len(items) < MIN_TRAINING_ITEMS:
        raise TacitTrainingError(
            f"評価済みの暗黙知が {MIN_TRAINING_ITEMS} 件未満です(現在 {len(items)} 件)。"
            "「暗黙知共有」画面で★評価を増やしてから実行してください。"
        )

    vectors, embedding_model = _embed(settings, [it["content"] for it in items])
    x_all = np.array(vectors, dtype=float)
    y_all = np.array([it["rating"] for it in items], dtype=float)

    pipeline = Pipeline([("scale", StandardScaler()), ("ridge", Ridge(alpha=5.0))])
    metrics: dict[str, Any] = {"embedding_model": embedding_model}

    if len(items) >= MIN_ITEMS_FOR_VALIDATION:
        x_train, x_val, y_train, y_val = train_test_split(x_all, y_all, test_size=0.2, random_state=42)
        pipeline.fit(x_train, y_train)
        val_pred = pipeline.predict(x_val)
        metrics["val_mae"] = float(mean_absolute_error(y_val, val_pred))
        metrics["val_count"] = int(len(y_val))
        # 精度を確認したあと、実運用モデルは全データで学習し直す
        pipeline.fit(x_all, y_all)
    else:
        pipeline.fit(x_all, y_all)
        train_pred = pipeline.predict(x_all)
        metrics["train_mae"] = float(mean_absolute_error(y_all, train_pred))
        metrics["note"] = "評価済み件数が少ないため検証データを分けていません(学習データ自体でのMAE)"

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / f"model_{run_id}.joblib"
    joblib.dump({"pipeline": pipeline, "embedding_model": embedding_model}, model_path)

    return {
        "model_path": str(model_path),
        "feature_dim": int(x_all.shape[1]),
        "training_item_count": len(items),
        "metrics": metrics,
    }


def _load(model_path: str) -> dict[str, Any] | None:
    try:
        return joblib.load(model_path)
    except Exception as exc:
        logger.error("学習済みモデルの読み込みに失敗 path=%s: %s", model_path, exc)
        return None


def predict_ratings(settings: Settings, model_path: str, contents: list[str]) -> list[float] | None:
    """学習済みモデルで評価値(0〜5 にクリップ)を予測する。読み込み失敗時は None。"""
    if not contents:
        return []
    bundle = _load(model_path)
    if not bundle:
        return None
    vectors, _ = _embed(settings, contents)
    x = np.array(vectors, dtype=float)
    pred = bundle["pipeline"].predict(x)
    return [float(max(0.0, min(5.0, p))) for p in pred]
