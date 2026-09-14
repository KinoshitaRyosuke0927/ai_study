"""
LightGBMのハイパーパラメータチューニング版

## 経緯
③(LightGBM + ドメイン知識由来の特徴量によるハイブリッド)を検証したが、
以下のいずれの追加特徴量も、本番に最も近い擬似ホールドアウト
(year<=4で学習 -> year==5のtournamentのみ検証)では改善しなかった。

    +t (連続時間特徴量)                  : 3.522 -> 3.474 (わずかに改善だが誤差の範囲)
    +decay = exp(-k*t)                   : tと完全に同じ結果(木は単調変換から新情報を得られない)
    +domain_pred (指数飽和カーブの予測値) : 3.522 -> 3.577 (悪化)
    +prev_year_avg (前年の平均タイム)     : 3.522 -> 3.936 (悪化)

いずれも「データの少ない古いfold(fit<=2年)」では改善する一方、
「本番と同じ5年分学習に近いfold(fit<=4年)」では悪化するという
一貫したパターンが見られた。これは、LightGBM自身が既に
year・player_id・course_idの分岐だけで十分にパターンを学習できており、
外部から追加した「滑らかな外挿」の情報はむしろノイズになっている
ことを示唆している。

## 方針転換：特徴量ではなくモデル自体のチューニング
上記の結果を踏まえ、「LightGBMに新しい情報を追加する」のではなく、
「LightGBM自体のハイパーパラメータ（学習率・木の深さ・葉の最小サンプル数等）を
このデータサイズ(3200件学習)に合わせて最適化する」方向に切り替えた。
デフォルトパラメータ(n_estimators=100, learning_rate=0.1, max_depth=-1)は
やや過学習気味/学習不足気味である可能性があり、grid searchで調整した。

## 検証方法
本番に近い2つのfold（fit<=3年→valid4年目、fit<=4年→valid5年目、
いずれもtournamentのみで検証）の平均RMSEでgrid searchした。
（fit<=2年→valid3年目は学習データが少なすぎて本番の状況とかけ離れるため
参考値としてのみ確認し、grid searchの目的関数には含めていない）

    baseline (デフォルト)                         : fold(3→4)=3.183, fold(4→5)=3.522
    tuned (n_estimators=150, lr=0.25, max_depth=5,
           min_child_samples=25)                  : fold(3→4)=2.926, fold(4→5)=3.259

参考: fold(2→3) は baseline=4.748 -> tuned=4.808 とわずかに悪化するが、
これは学習データが2年分しかない極端に厳しい条件でのみ起きており、
本番(5年分の学習データがある)の状況とは乖離が大きいため許容する。
"""

import sys

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_squared_error

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

CATEGORICAL_COLS = ["session_type", "player_id", "course_id"]
FEATURE_COLS = ["year", "quarter"]
BEST_PARAMS = dict(n_estimators=150, learning_rate=0.25, max_depth=5, min_child_samples=25)


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
        m = LGBMRegressor(random_state=42, verbose=-1, **params).fit(X_fit, fit_part["time_seconds"])
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

    ## 本番学習: year 1-5 の全データで学習し、test (year=6) を予測
    X_train, X_test = make_xy(FEATURE_COLS, train_data, test_data)
    model = LGBMRegressor(random_state=42, verbose=-1, **BEST_PARAMS)
    model.fit(X_train, train_data["time_seconds"])

    pred = model.predict(X_test)
    submission = pd.DataFrame({"record_id": test_data["record_id"], "time_seconds": pred})
    submission.to_csv("submission_lgbm_tuned.csv", index=False)
    print()
    print(submission.head())
    print("saved -> submission_lgbm_tuned.csv")


if __name__ == "__main__":
    main()
