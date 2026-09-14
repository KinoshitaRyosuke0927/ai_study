"""
CatBoostによる比較・チューニング

lightgbm_tuned_model.py と同じ特徴量（year, quarter, session_type/player_id/course_idの
one-hotダミー）・同じ検証方法（fit<=3->valid4年目, fit<=4->valid5年目のtournamentのみ、
本番に近い2foldの平均RMSEでgrid search）でCatBoostを比較する。

なお、CatBoost本来の強みである「カテゴリ変数をone-hot化せずネイティブに扱う」
`cat_features` 機能も試したが、このデータではone-hotよりも大幅に悪化した
（RMSEが7〜9台まで悪化）。CatBoostのカテゴリ特徴量の扱い（ターゲット統計量ベースの
エンコーディング）は本来、高カーディナリティなカテゴリ変数で効果を発揮するが、
今回はplayer_id(20種類)・course_id(8種類)と少なく、むしろone-hotの方が
相性が良かったと考えられる。
"""

import sys

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from sklearn.metrics import mean_squared_error

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

CATEGORICAL_COLS = ["session_type", "player_id", "course_id"]
FEATURE_COLS = ["year", "quarter"]
BEST_PARAMS = dict(depth=4, learning_rate=0.2, iterations=200, l2_leaf_reg=3)


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
        m = CatBoostRegressor(random_state=42, verbose=False, **params)
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
    model = CatBoostRegressor(random_state=42, verbose=False, **BEST_PARAMS)
    model.fit(X_train, train_data["time_seconds"])

    pred = model.predict(X_test)
    submission = pd.DataFrame({"record_id": test_data["record_id"], "time_seconds": pred})
    submission.to_csv("submission_catboost_tuned.csv", index=False)
    print()
    print(submission.head())
    print("saved -> submission_catboost_tuned.csv")


if __name__ == "__main__":
    main()
