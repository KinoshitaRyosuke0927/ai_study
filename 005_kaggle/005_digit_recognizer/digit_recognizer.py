"""
https://www.kaggle.com/competitions/digit-recognizer/overview
手書き数字画像（0〜9）の多クラス分類問題。
評価指標: Accuracy（正解率）

EDA からの主な発見:
  - ピクセル値の 80.8% がゼロ（白背景）→ 正規化で 0〜1 に変換
  - クラス分布はほぼ均等（3,795〜4,684枚）→ クラス不均衡の対策不要
  - 欠損値なし → 補完処理不要

ベースラインモデルの方針:
  - 784ピクセルをそのまま特徴量として使用（特徴量エンジニアリングなし）
  - ピクセル値を 0〜255 → 0〜1 に正規化（モデルの学習安定化）
  - LightGBM で多クラス分類
  - 5-fold 交差検証で精度を評価
"""

from lightgbm import LGBMClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score, ParameterSampler
from sklearn.metrics import accuracy_score
from scipy.stats import randint, uniform
from tqdm import tqdm

import numpy as np
import pandas as pd
from pathlib import Path

DATA_DIR = Path(r"C:\azure_ai\education\005_kaggle\competitions\digit-recognizer")

train = pd.read_csv(DATA_DIR / "train.csv")
test  = pd.read_csv(DATA_DIR / "test.csv")

print(f"train: {train.shape},  test: {test.shape}")

## 特徴量・目的変数の準備
X      = train.drop("label", axis=1).values / 255.0  # 0〜1 に正規化
y      = train["label"].values
X_test = test.values / 255.0

print(f"X: {X.shape},  クラス数: {len(np.unique(y))}")

## LightGBM のパラメータ設定
# TUNE = True : ParameterSampler でハイパーパラメータを探索する（時間がかかる）
# TUNE = False: 探索済みパラメータをそのまま使用して即座に学習する
TUNE = False

# 探索済み最良パラメータ
BEST_PARAMS = {
    "colsample_bytree":  0.8,
    "learning_rate":     0.1,
    "max_depth":         7,
    "min_child_samples": 20,
    "n_estimators":      500,
    "num_leaves":        63,
    "reg_alpha":         0.1,
    "reg_lambda":        1.0,
    "subsample":         0.8,
}

# StratifiedKFold: クラス比率を保ったまま k 分割する
# 画像分類など多クラス問題に適切（時系列ではないため TimeSeriesSplit は不要）
skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=1)

print("\n学習開始")

if TUNE:
    param_dist = {
        "n_estimators":      randint(300, 1000),
        "max_depth":         randint(5, 10),
        "learning_rate":     uniform(0.05, 0.15),
        "num_leaves":        randint(31, 127),
        "subsample":         uniform(0.6, 0.4),
        "colsample_bytree":  uniform(0.6, 0.4),
        "reg_alpha":         uniform(0, 0.5),
        "reg_lambda":        uniform(0.5, 2.0),
        "min_child_samples": randint(10, 50),
    }
    N_ITER = 30
    param_list        = list(ParameterSampler(param_dist, n_iter=N_ITER, random_state=1))
    best_score        = 0.0
    best_params_found = None

    for i, params in enumerate(tqdm(param_list, desc="チューニング中"), 1):
        model  = LGBMClassifier(**params, random_state=1, verbosity=-1, n_jobs=-1)
        scores = cross_val_score(model, X, y, cv=skf, scoring="accuracy", n_jobs=-1)
        acc    = scores.mean()
        if acc > best_score:
            best_score        = acc
            best_params_found = params
        tqdm.write(f"  [{i:2d}/{N_ITER}] Accuracy={acc:.4f}  best={best_score:.4f}")

    print(f"\nチューニング完了  CV Accuracy={best_score:.4f}")
    print(f"best_params={best_params_found}")
    best_model = LGBMClassifier(**best_params_found, random_state=1, verbosity=-1, n_jobs=-1)
    best_model.fit(X, y)

else:
    best_model = LGBMClassifier(
        **BEST_PARAMS, random_state=1, verbosity=-1, n_jobs=-1
    )
    # CV スコアを確認してから全データで学習
    scores = cross_val_score(best_model, X, y, cv=skf, scoring="accuracy", n_jobs=-1)
    print(f"CV Accuracy: {scores.mean():.4f} (±{scores.std():.4f})")
    print(f"  各fold: {[f'{s:.4f}' for s in scores]}")
    best_model.fit(X, y)
    print("探索済みパラメータで学習完了")

## 予測・提出ファイルの出力
predictions = best_model.predict(X_test)

output = pd.DataFrame({
    "ImageId": range(1, len(predictions) + 1),
    "Label":   predictions,
})
output.to_csv(
    Path(__file__).parent / "submission.csv",
    index=False
)
print(f"\n予測結果（先頭5件）:")
print(output.head())
print("submission.csv を出力しました")
