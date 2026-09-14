"""
アンサンブルモデル：指数飽和カーブ(ドメイン知識モデル) + LightGBM

## 背景
実際の投稿スコア(year=6, tournamentのみ)は以下の通りだった。

    線形回帰(1/year, log(year)) : 4.3624
    GAM                         : 4.3666
    LightGBM                    : 3.3619
    指数飽和カーブ(ドメイン知識)  : 4.0603

ホールドアウト検証(year<=4で学習→year==5を予測)では指数飽和カーブが
LightGBMを上回っていたにもかかわらず、実際のyear=6では逆転している。
これは「滑らかな関数で外挿する」系のモデル(線形/GAM/指数飽和カーブ)が
軒並み実測で悪化している一方、LightGBM(直近の値に近い予測をする傾向)は
ホールドアウト推定とほぼ一致していたことから、
**year=6の実際の伸びは、滑らかな外挿が想定するほど大きくなかった
可能性が高い**と考えられる。

## アンサンブルの狙い
- 指数飽和カーブ：滑らかなトレンドを捉えられるが、year=6では外挿が効きすぎるバイアスがある
- LightGBM：外挿は原理的に苦手だが、実測ではむしろ手堅かった
この「異なるバイアスを持つ2つのモデル」を混ぜることで、
どちらか一方の外し方に振り切られるリスクを下げる。

## 重みの決め方
year=6の正解ラベルは無いため、擬似ホールドアウト
(year<=4で学習 → year==5のtournamentのみを検証に使う。本番と同じ
「tournamentだけを予測する」状況に揃えるため)でブレンド比率wを
grid searchし、
    pred = w * 指数飽和カーブ + (1-w) * LightGBM
のRMSEが最小になるwを採用する。
"""

import sys

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_squared_error

from domain_learning_curve_model import (
    add_time_feature,
    apply_offsets,
    fit_pair_models,
    predict_pair_models,
    session_offsets,
)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

DOMAIN_K = 0.45  # domain_learning_curve_model.py で選定された値
CATEGORICAL_COLS = ["session_type", "player_id", "course_id"]


def lgbm_predict(fit_df: pd.DataFrame, target_df: pd.DataFrame) -> np.ndarray:
    """lightgbm_model.py と同じ特徴量・設定でLightGBMを学習し予測する"""
    fit_df = fit_df.copy()
    target_df = target_df.copy()
    fit_df["quarter"] = fit_df["quarter"].fillna(0)
    target_df["quarter"] = target_df["quarter"].fillna(0)

    feature_cols = ["year", "quarter"]
    combined = pd.concat(
        [fit_df[feature_cols + CATEGORICAL_COLS], target_df[feature_cols + CATEGORICAL_COLS]],
        keys=["fit", "target"],
    )
    dummies = pd.get_dummies(combined, columns=CATEGORICAL_COLS)
    X_fit, X_target = dummies.loc["fit"], dummies.loc["target"]

    model = LGBMRegressor(random_state=42, verbose=-1)
    model.fit(X_fit, fit_df["time_seconds"])
    return model.predict(X_target)


def domain_predict(fit_df: pd.DataFrame, target_df: pd.DataFrame, k: float = DOMAIN_K) -> np.ndarray:
    models = fit_pair_models(fit_df, k)
    offsets = session_offsets(fit_df, models, k)
    return apply_offsets(predict_pair_models(models, target_df, k), target_df, offsets)


def select_best_weight(train_df: pd.DataFrame) -> tuple[float, float]:
    """
    擬似ホールドアウト(year<=4学習 -> year==5のtournamentのみ検証)で
    ブレンド比率wをgrid searchする。
    """
    fit_part = train_df[train_df["year"] <= 4]
    valid_part = train_df[(train_df["year"] == 5) & (train_df["session_type"] == "tournament")]

    pred_domain = domain_predict(fit_part, valid_part)
    pred_lgbm = lgbm_predict(fit_part, valid_part)
    y_true = valid_part["time_seconds"].to_numpy()

    best_w, best_rmse = None, np.inf
    for w in np.arange(0.0, 1.01, 0.05):
        pred = w * pred_domain + (1 - w) * pred_lgbm
        rmse = np.sqrt(mean_squared_error(y_true, pred))
        if rmse < best_rmse:
            best_w, best_rmse = w, rmse

    print("--- ブレンド比率ごとのRMSE(参考) ---")
    for w in [0.0, 0.25, 0.5, 0.75, 1.0]:
        pred = w * pred_domain + (1 - w) * pred_lgbm
        rmse = np.sqrt(mean_squared_error(y_true, pred))
        print(f"  w(domain)={w:.2f} -> RMSE={rmse:.3f}")

    return best_w, best_rmse


def main():
    train_df = add_time_feature(pd.read_csv("train_data.csv"))
    test_df = add_time_feature(pd.read_csv("test_data.csv"))

    best_w, best_rmse = select_best_weight(train_df)
    print(f"\n選択したブレンド比率: w(domain)={best_w:.2f}, w(lgbm)={1 - best_w:.2f}")
    print(f"pseudo-holdout RMSE(tournamentのみ) = {best_rmse:.3f}")

    pred_domain_test = domain_predict(train_df, test_df)
    pred_lgbm_test = lgbm_predict(train_df, test_df)
    pred_ensemble = best_w * pred_domain_test + (1 - best_w) * pred_lgbm_test

    submission = pd.DataFrame({"record_id": test_df["record_id"], "time_seconds": pred_ensemble})
    submission.to_csv("submission_ensemble.csv", index=False)
    print(submission.head())
    print("saved -> submission_ensemble.csv")


if __name__ == "__main__":
    main()
