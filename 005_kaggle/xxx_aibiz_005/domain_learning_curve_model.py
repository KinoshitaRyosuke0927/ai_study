"""
ドメイン知識(レースゲームの習熟曲線)を活用した最終モデル

## 発想
レースゲームのタイムアタックには物理的な下限(理論上のベストタイム)が存在する。
そのため「経験を積むほど速くなるが、上達幅は逓減し、ある値に漸近していく」という
飽和型(asymptotic)の学習曲線で表現するのが自然である。

これは心理学・スポーツ科学で使われる指数学習曲線(exponential learning curve)そのもの:

    time(t) = c + b * exp(-k * t)

- c: 選手×コースごとの「到達しうる下限タイム」
- b: 選手×コースごとの「初期タイムと下限タイムの差(伸びしろ)」
- k: 上達スピード(全選手・全コース共通と仮定するグローバルパラメータ)
- t: 経過時間(年、連続値。日付から計算するのでtournamentの時期も正確に扱える)

model_comparison_guide.md で採用した「1/year」「log(year)」による変換は、
year→∞ で発散する(タイムが際限なく短くなる、あるいはlogは発散が緩やかだが
下限を明示的に持たない)ため、理論上は物理的にありえない値へ外挿されうる。
指数飽和カーブは c という明示的な下限を持つため、より長期の外挿でも
破綻しにくいという利点がある(今回は1年先の外挿なので影響は小さいが、
「なぜこの関数形を選ぶか」という理由づけとして重要)。

## 選手×コースごとに別々の(c, b)を推定する理由
EDAの結果、上達幅(year1→year5の差)は
  - コースによって 6.6秒(C5)〜13.7秒(C7) とばらつく
  - 選手によっても 6.6秒〜16.5秒とばらつく
ことがわかっている。つまり「上達しやすいコース×上達しやすい選手」の
組み合わせ効果があるため、選手×コースの160通りごとに個別の(c, b)を
最小二乗法で推定する。1組につき25件(practice20件+tournament5件)の
データがあるため、2パラメータの推定には十分なサンプル数がある。

一方で上達"スピード"(k)は選手×コースごとに推定すると過学習しやすいため、
全体で共有するグローバルパラメータとし、グリッドサーチで選択する。
"""

import sys

import numpy as np
import pandas as pd

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error

REFERENCE_DATE = pd.Timestamp("2021-01-01")


def add_time_feature(df: pd.DataFrame) -> pd.DataFrame:
    """日付を「2021年始からの経過年数(連続値)」に変換する"""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["t"] = (df["date"] - REFERENCE_DATE).dt.days / 365.25
    return df


def fit_pair_models(fit_df: pd.DataFrame, k: float) -> dict:
    """player_id x course_id ごとに y = c + b * exp(-k*t) の (c, b) を最小二乗で推定する"""
    models = {}
    decay = np.exp(-k * fit_df["t"].to_numpy())
    fit_df = fit_df.assign(decay=decay)
    for (player, course), g in fit_df.groupby(["player_id", "course_id"]):
        X = g[["decay"]].to_numpy()
        y = g["time_seconds"].to_numpy()
        reg = LinearRegression().fit(X, y)
        models[(player, course)] = (reg.intercept_, reg.coef_[0])
    return models


def predict_pair_models(models: dict, target_df: pd.DataFrame, k: float) -> np.ndarray:
    decay = np.exp(-k * target_df["t"].to_numpy())
    preds = np.empty(len(target_df))
    for i, (player, course, d) in enumerate(
        zip(target_df["player_id"], target_df["course_id"], decay)
    ):
        c, b = models[(player, course)]
        preds[i] = c + b * d
    return preds


def session_offsets(fit_df: pd.DataFrame, models: dict, k: float) -> dict:
    """
    tournament(本番)は practice(練習) より僅かに遅い/速い傾向が残差として出るため、
    session_type の効果をタイプごとのグローバルな加算オフセットとして推定する
    (選手xコースごとに推定するには tournament のサンプル数が少なすぎるため、
    全選手xコース共通の1オフセットとして残差平均から求める)。
    """
    pred = predict_pair_models(models, fit_df, k)
    resid = fit_df["time_seconds"].to_numpy() - pred
    out = {}
    for s in ("practice", "tournament"):
        mask = (fit_df["session_type"] == s).to_numpy()
        out[s] = float(resid[mask].mean())
    return out


def apply_offsets(pred: np.ndarray, target_df: pd.DataFrame, offsets: dict) -> np.ndarray:
    add = target_df["session_type"].map(offsets).to_numpy()
    return pred + add


def select_best_k(train_df: pd.DataFrame, k_grid) -> tuple[float, float]:
    """2章の手法と同じ「year<=4で学習→year==5を未知年に見立てて検証」でkを選ぶ"""
    fit_part = train_df[train_df["year"] <= 4]
    valid_part = train_df[train_df["year"] == 5]

    best_k, best_rmse = None, np.inf
    for k in k_grid:
        models = fit_pair_models(fit_part, k)
        offsets = session_offsets(fit_part, models, k)
        pred = apply_offsets(predict_pair_models(models, valid_part, k), valid_part, offsets)
        rmse = np.sqrt(mean_squared_error(valid_part["time_seconds"], pred))
        if rmse < best_rmse:
            best_k, best_rmse = k, rmse
    return best_k, best_rmse


def tournament_only_rmse(train_df: pd.DataFrame, k: float) -> float:
    """本番同様「tournamentだけを予測する」状況に絞った参考RMSE"""
    fit_part = train_df[train_df["year"] <= 4]
    valid_part = train_df[(train_df["year"] == 5) & (train_df["session_type"] == "tournament")]
    models = fit_pair_models(fit_part, k)
    offsets = session_offsets(fit_part, models, k)
    pred = apply_offsets(predict_pair_models(models, valid_part, k), valid_part, offsets)
    return float(np.sqrt(mean_squared_error(valid_part["time_seconds"], pred)))


def main():
    train_df = add_time_feature(pd.read_csv("train_data.csv"))
    test_df = add_time_feature(pd.read_csv("test_data.csv"))

    k_grid = np.arange(0.05, 3.01, 0.05)
    best_k, holdout_rmse = select_best_k(train_df, k_grid)
    print(f"selected k = {best_k:.2f}  (pseudo-holdout RMSE [year5全体] = {holdout_rmse:.3f})")
    print(f"  参考: tournamentのみに絞った場合のRMSE = {tournament_only_rmse(train_df, best_k):.3f}")

    # 全学習データ(year1-5)で選手xコースごとの(c, b)を再学習
    models = fit_pair_models(train_df, best_k)
    offsets = session_offsets(train_df, models, best_k)
    print(f"session offsets = {offsets}")

    # test は全て tournament なのでtournamentオフセットが加算される
    pred = apply_offsets(predict_pair_models(models, test_df, best_k), test_df, offsets)

    submission = pd.DataFrame(
        {"record_id": test_df["record_id"], "time_seconds": pred}
    )
    submission.to_csv("submission_domain_learning_curve.csv", index=False)
    print(submission.head())
    print("saved -> submission_domain_learning_curve.csv")


if __name__ == "__main__":
    main()
