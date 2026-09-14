"""
XGBoostによる比較・チューニング

lightgbm_tuned_model.py / catboost_tuned_model.py と同じ特徴量・同じ検証方法
（fit<=3->valid4年目, fit<=4->valid5年目のtournamentのみ、本番に近い2foldの
平均RMSEでgrid search）でXGBoostを比較する。
"""

import sys

import numpy as np
import pandas as pd
from sklearn.metrics import mean_squared_error
from xgboost import XGBRegressor

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

CATEGORICAL_COLS = ["session_type", "player_id", "course_id"]
FEATURE_COLS = ["year", "quarter"]
BEST_PARAMS = dict(max_depth=3, learning_rate=0.2, n_estimators=300, min_child_weight=1)


def make_xy(feature_cols, fit_df, valid_df):
    combined = pd.concat(
        [fit_df[feature_cols + CATEGORICAL_COLS], valid_df[feature_cols + CATEGORICAL_COLS]],
        keys=["fit", "valid"],
    )
    dummies = pd.get_dummies(combined, columns=CATEGORICAL_COLS)
    return dummies.loc["fit"], dummies.loc["valid"]


def evaluate(train_data: pd.DataFrame, params: dict) -> None:
    print(f"=== 擬似ホールドアウトRMSE比較 (tournamentのみ, params={params}) ===")
    for fit_max, valid_year in [(2, 3), (3, 4), (4, 5)]:
        fit_part = train_data[train_data["year"] <= fit_max].copy()
        valid_part = train_data[
            (train_data["year"] == valid_year) & (train_data["session_type"] == "tournament")
        ].copy()
        fit_part["quarter"] = fit_part["quarter"].fillna(0)
        valid_part["quarter"] = valid_part["quarter"].fillna(0)

        X_fit, X_valid = make_xy(FEATURE_COLS, fit_part, valid_part)
        m = XGBRegressor(random_state=42, verbosity=0, **params)
        m.fit(X_fit, fit_part["time_seconds"])
        rmse = np.sqrt(mean_squared_error(valid_part["time_seconds"], m.predict(X_valid)))
        print(f"  fit<={fit_max} -> valid={valid_year}: RMSE={rmse:.3f}")


def main():
    train_data = pd.read_csv("train_data.csv")
    test_data = pd.read_csv("test_data.csv")
    train_data["quarter"] = train_data["quarter"].fillna(0)
    test_data["quarter"] = test_data["quarter"].fillna(0)

    print(">>> デフォルトパラメータ")
    evaluate(train_data, {})
    print()
    print(">>> チューニング後パラメータ")
    evaluate(train_data, BEST_PARAMS)

    X_train, X_test = make_xy(FEATURE_COLS, train_data, test_data)
    model = XGBRegressor(random_state=42, verbosity=0, **BEST_PARAMS)
    model.fit(X_train, train_data["time_seconds"])

    pred = model.predict(X_test)
    submission = pd.DataFrame({"record_id": test_data["record_id"], "time_seconds": pred})
    submission.to_csv("submission_xgb_tuned.csv", index=False)
    print()
    print(submission.head())
    print("saved -> submission_xgb_tuned.csv")


if __name__ == "__main__":
    main()
