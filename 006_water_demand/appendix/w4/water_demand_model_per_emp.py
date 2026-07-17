from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def make_daily_model(alpha):
    """
    特徴量のスケール差（0/1のダミー系 と 気温由来の交互作用）を揃えるため標準化を挟んだRidge回帰
    fit_intercept=Falseとし、非出社日は全特徴量が0になる＝予測消費量も0となる関係を切片に崩されないようにする
    同じ理由でStandardScalerもwith_mean=Falseとし、0が0のまま保たれるようにする
    """
    return make_pipeline(StandardScaler(with_mean=False), Ridge(alpha=alpha, fit_intercept=False))


def predict_daily(model, X):
    """日次消費量予測（負値は0にクリップ）"""
    return np.clip(model.predict(X), 0, None)


## データ読み込み
# 学習用データのパス
BASE_DIR = Path(__file__).parent
# 水の注文量（月次実績、評価の正解データとして利用）
water_demand = pd.read_csv(f"{BASE_DIR}/input_data/water_demand.csv")
# 矢野さんの過去消費量を補正
# ※今まで消費を抑えていたため
water_demand["order_quantity"] *= 1.2
# JBDカレンダー
jbd_calendar = pd.read_csv(f"{BASE_DIR}/input_data/jbd_calendar.csv")
# 社員ごとのAIC出社カレンダー
work_day = pd.read_csv(f"{BASE_DIR}/input_data/work_day.csv")
# 気象データ
weather_data = pd.read_csv(f"{BASE_DIR}/input_data/weather_data.csv")
# 社員ごと日ごとの水消費量実績
water_demand_per_emp = pd.read_csv(f"{BASE_DIR}/input_data/v_water_demand_per_emp.csv")

## 前処理
# 年月列の作成
water_demand["date_ym"] = pd.to_datetime(water_demand["date_ym"])
water_demand["year_month"] = water_demand["date_ym"].dt.to_period("M")
# 年月列の作成
jbd_calendar["date"] = pd.to_datetime(jbd_calendar["date"])
jbd_calendar["year_month"] = jbd_calendar["date"].dt.to_period("M")
# 年月列の作成
work_day["date"] = pd.to_datetime(work_day["date"])
work_day["year_month"] = work_day["date"].dt.to_period("M")
# 年月列の作成
weather_data["date"] = pd.to_datetime(weather_data["date"])
weather_data["year_month"] = weather_data["date"].dt.to_period("M")
# 日付型変換（列名をdateに統一）
water_demand_per_emp["date"] = pd.to_datetime(water_demand_per_emp["date_ym"])

# 月次実績を年月引きできるように変換
water_demand_months = water_demand.set_index("year_month")["order_quantity"]
# 社員情報取得
emp_cols = [c for c in work_day.columns if c.startswith("emp_")]

########################################################################
## 人ごと日ごとモデル（社員×日単位で消費量を予測し、月次に積み上げ集計）
########################################################################

## 縦持ちデータへの変換（社員×日を1行1レコードに展開）
# 消費量実績の縦持ち化
consumption_long = water_demand_per_emp.melt(
    id_vars="date", value_vars=emp_cols, var_name="emp_id", value_name="consumption"
)
# 出社実績の縦持ち化
attendance_long = work_day.melt(id_vars="date", value_vars=emp_cols, var_name="emp_id", value_name="attendance")

## 学習データ構築（社員×日単位）
# 消費量実績と出社実績を結合
daily_df = consumption_long.merge(attendance_long, on=["date", "emp_id"], how="left")
# 営業日フラグを結合
daily_df = daily_df.merge(jbd_calendar[["date", "business_day_flag"]], on="date", how="left")
# 気温を結合
daily_df = daily_df.merge(weather_data[["date", "tavg"]], on="date", how="left")
# 出社実績には非営業日にもフラグが立っている行が一部あるため、営業日フラグでマスクする
daily_df["attend_masked"] = daily_df["attendance"] * daily_df["business_day_flag"]
# 月次集計用の年月列を作成
daily_df["year_month"] = daily_df["date"].dt.to_period("M")
# 社員ごとの消費水準・気温感度の差を捉えるため、社員ダミー×出社フラグ／社員ダミー×出社フラグ×気温を特徴量化
# （単純な社員ダミーの加算だと非出社日にもその社員の基準消費量が乗ってしまうため、出社日にのみ効くようにする。
# 　気温への反応度も社員ごとに異なる＝相関の強さがバラバラなため、感度自体も社員ごとに学習させる）
emp_dummies = pd.get_dummies(daily_df["emp_id"], prefix="emp").astype(int)
emp_attend = emp_dummies.multiply(daily_df["attend_masked"], axis=0)
emp_attend.columns = [f"{c}_attend" for c in emp_dummies.columns]
emp_attend_tavg = emp_attend.multiply(daily_df["tavg"], axis=0)
emp_attend_tavg.columns = [f"{c}_tavg" for c in emp_attend.columns]
# 交互作用列を結合
daily_df = pd.concat([daily_df, emp_attend, emp_attend_tavg], axis=1)

## 特徴量定義
# 社員ごとの出社効果（社員ダミー×出社フラグ）＋ 社員ごとの気温感度（社員ダミー×出社フラグ×気温）
feature_cols = list(emp_attend.columns) + list(emp_attend_tavg.columns)
# 学習に使える行（消費量・特徴量が揃っている行）のみ抽出
daily_train = daily_df.dropna(subset=feature_cols + ["consumption"])
# 学習用データ分割
X_daily = daily_train[feature_cols]
y_daily = daily_train["consumption"]

## 評価対象月の決定
# 気温データが取得できている最終日（これ以降の月は日ごとの気温が揃わないため評価対象外）
weather_max_date = weather_data["date"].max()
# 「月内の全日で特徴量が揃っている」かつ「注文実績がある」月のみを評価対象とする
eval_months = [
    ym
    for ym in water_demand_months.index
    if ym.end_time <= weather_max_date and ym in daily_train["year_month"].unique()
]


def month_out_cv_mae(alpha):
    """月単位でのLeave-One-Month-Out CV（対象月のデータを除いて学習→対象月を日次予測して月次集計→実績と比較）"""
    # 誤差格納用
    errors = []
    # 評価対象月を順番に処理
    for ym in eval_months:
        # 対象月を除いた学習データ
        train_mask = daily_train["year_month"] != ym
        # モデル用意
        model_cv = make_daily_model(alpha)
        # 対象月を除いて学習
        model_cv.fit(X_daily[train_mask], y_daily[train_mask])
        # 対象月の日次特徴量を抽出
        month_rows = daily_train[daily_train["year_month"] == ym]
        # 対象月の日次消費量を予測して月次集計
        pred_total = predict_daily(model_cv, month_rows[feature_cols]).sum()
        # 実績値取得
        actual_total = water_demand_months.loc[ym]
        # 絶対誤差を記録
        errors.append(abs(pred_total - actual_total))
    return np.mean(errors), errors


## alpha設定
# Ridge回帰 + 正則化強度alphaを月次LOO-CVで比較
print("=" * 40)
print("【alpha別 月次LOO-CV MAE】")
# 定数用意
best_alpha = None
best_mae = float("inf")
# 社員×気温の交互作用まで含め特徴量数が多いため、強めの正則化域まで探索する
for alpha in [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0, 10000.0, 30000.0, 100000.0]:
    # 月次LOO-CVでMAE計算
    mae, _ = month_out_cv_mae(alpha)
    # 最良か判定
    marker = " ← 最良" if mae < best_mae else ""
    # 結果出力
    print(f"  alpha={alpha:>8}: 月次LOO-CV MAE = {mae:.2f} L{marker}")
    # 最良の場合は定数更新
    if mae < best_mae:
        best_mae = mae
        best_alpha = alpha
# 最良alpha決定
print(f"\n  採用alpha: {best_alpha}")
print("=" * 40)

## 最良alphaで改めて学習（全日次データで学習した最終モデル）
# モデル用意
model = make_daily_model(best_alpha)
# 学習
model.fit(X_daily, y_daily)

## 最良alphaでの月次LOO-CV結果（実力値）
loo_mae, loo_errors = month_out_cv_mae(best_alpha)

## 結果の表示
print()
print("=" * 40)
print("【月次LOO-CV 評価結果】")
# 月ごとに実績値と予測誤差を出力
for ym, err in zip(eval_months, loo_errors):
    # 実績値取得
    actual = water_demand_months.loc[ym]
    # 結果表示
    print(f"  {ym}: 実績={actual:.0f}L, 絶対誤差={err:.1f}L")
print()
print(f"  LOO-CV MAE（実力値） : {loo_mae:.2f} L")
print("=" * 40)

########################################################################
## 翌月の予測（社員ごと・日ごとの消費量を予測し、月次集計値も算出）
########################################################################


def lookup_temperature(dates):
    """
    指定した日付列（Series）に対応する気温を返す。
    実測値があればそれを使い、無ければ前年同日、それも無ければ前年同月平均で代替する。
    """
    weather_lookup = weather_data.set_index("date")["tavg"]
    # まずは実測値を引き当て
    tavg = dates.map(weather_lookup)
    # 実測値が無い日は前年同日で代替
    missing = tavg.isna()
    if missing.any():
        prev_year_dates = dates[missing] - pd.DateOffset(years=1)
        tavg.loc[missing] = prev_year_dates.map(weather_lookup).values
    # 前年同日でも代替できない日は前年同月の平均気温で代替
    missing = tavg.isna()
    if missing.any():
        for ym in dates[missing].dt.to_period("M").unique():
            prev_year_period = ym - 12
            prev_month_mean = weather_data.loc[weather_data["year_month"] == prev_year_period, "tavg"].mean()
            target_idx = missing & (dates.dt.to_period("M") == ym)
            tavg.loc[target_idx] = prev_month_mean
    return tavg


def build_feature_frame(dates):
    """
    指定した日付集合について、出社予定・営業日フラグ・気温（実測 or 代替）から
    社員×日ごとの特徴量（feature_cols）を構築して返す（date, emp_id列を含む）。
    """
    # 対象日の出社予定
    work_day_target = work_day[work_day["date"].isin(dates)]
    # 対象日の営業日フラグ
    jbd_target = jbd_calendar[jbd_calendar["date"].isin(dates)]
    # 出社予定の縦持ち化
    frame = work_day_target.melt(id_vars="date", value_vars=emp_cols, var_name="emp_id", value_name="attendance")
    # 営業日フラグを結合
    frame = frame.merge(jbd_target[["date", "business_day_flag"]], on="date", how="left")
    # 気温（実測 or 代替）を付与
    frame["tavg"] = lookup_temperature(frame["date"])
    # 出社実績を営業日フラグでマスク
    frame["attend_masked"] = frame["attendance"] * frame["business_day_flag"]
    # 社員ごとの出社効果・気温感度（学習時と同じ列構成に揃える）
    emp_dummies_f = pd.get_dummies(frame["emp_id"], prefix="emp").astype(int)
    emp_attend_f = emp_dummies_f.multiply(frame["attend_masked"], axis=0)
    emp_attend_f.columns = [f"{c}_attend" for c in emp_dummies_f.columns]
    emp_attend_f = emp_attend_f.reindex(columns=emp_attend.columns, fill_value=0)
    emp_attend_tavg_f = emp_attend_f.multiply(frame["tavg"], axis=0)
    emp_attend_tavg_f.columns = [f"{c}_tavg" for c in emp_attend_f.columns]
    # 交互作用列を結合
    return pd.concat([frame, emp_attend_f, emp_attend_tavg_f], axis=1)


def wide_from_long(long_df, value_col):
    """縦持ちの(date, emp_id, value_col)をv_water_demand_per_emp.csvと同じ横持ち形式に変換する"""
    wide_df = long_df.pivot(index="date", columns="emp_id", values=value_col)[emp_cols]
    # v_water_demand_per_emp.csvと同じ日付表記（ゼロ埋めなしのYYYY/M/D）に変換
    wide_df.insert(0, "date_ym", [f"{d.year}/{d.month}/{d.day}" for d in wide_df.index])
    return wide_df.reset_index(drop=True)


def predict_next_month_per_emp(model, target_month_dt):
    """
    指定した月の社員×日ごとの消費量を予測し、v_water_demand_per_emp.csvと同じ形式
    （date_ym, emp_01, ..., emp_12）のDataFrameを返す。
    このDataFrameをそのままv_water_demand_per_emp.csvの実績に積み上げていくことを想定している。
    出社・営業日カレンダーが不足していて予測できない場合はNoneを返す。
    """
    # 年月に変換
    target_period = pd.Period(target_month_dt, "M")
    # 予測対象月に含まれる日付一覧
    days_in_month = pd.date_range(target_period.start_time.normalize(), target_period.end_time.normalize(), freq="D")
    # 予測対象月の出社・営業日データが不足している場合
    if work_day[work_day["date"].isin(days_in_month)].empty or jbd_calendar[jbd_calendar["date"].isin(days_in_month)].empty:
        return None

    # 予測対象月の日次×社員データを構築し、消費量を予測
    pred_df = build_feature_frame(days_in_month)
    pred_df["predicted_consumption"] = predict_daily(model, pred_df[feature_cols])
    return wide_from_long(pred_df, "predicted_consumption")


def predict_month_with_partial_actuals(target_month_dt, performance_df):
    """
    予測対象月の実績が一部取得できている場合に、その実績を学習データへ追加して再学習し、
    残りの日数分を予測し直す。
    - 実績がある日  : 実績値をそのまま採用
    - 実績が無い日  : 実績を反映して再学習したモデルによる予測値を採用
    月内全日分をv_water_demand_per_emp.csvと同じ形式のDataFrameとして返す。
    performance_dfがNone/空、または対象月の実績が無い場合は、
    元のモデル（実績未反映）による通常の翌月予測と同じ結果になる。
    """
    # 年月に変換
    target_period = pd.Period(target_month_dt, "M")
    # 予測対象月に含まれる日付一覧
    all_days = pd.date_range(target_period.start_time.normalize(), target_period.end_time.normalize(), freq="D")

    # 対象月の実績データを抽出
    if performance_df is not None and len(performance_df) > 0:
        actual_month = performance_df.copy()
        actual_month["date"] = pd.to_datetime(actual_month["date_ym"])
        actual_month = actual_month[actual_month["date"].dt.to_period("M") == target_period].sort_values("date")
    else:
        actual_month = pd.DataFrame(columns=["date"] + emp_cols)

    # 実績が無い場合は元のモデルで通常通り月内全日を予測
    if actual_month.empty:
        return predict_next_month_per_emp(model, target_month_dt)

    # 実績が得られている日付・まだ実績が無い残り日数を分ける
    elapsed_dates = actual_month["date"]
    remaining_days = all_days[~all_days.isin(elapsed_dates)]

    ## 実績データを学習データに追加して再学習
    # 実績を縦持ち化
    actual_long = actual_month.melt(id_vars="date", value_vars=emp_cols, var_name="emp_id", value_name="consumption")
    # 実績日の特徴量を構築（気温の実測が無い場合は前年同日等で代替）
    actual_features = build_feature_frame(elapsed_dates)
    actual_train = actual_features.merge(actual_long[["date", "emp_id", "consumption"]], on=["date", "emp_id"], how="left")
    actual_train = actual_train.dropna(subset=feature_cols + ["consumption"])
    # 既存の学習データに実績を追加
    X_updated = pd.concat([X_daily, actual_train[feature_cols]], ignore_index=True)
    y_updated = pd.concat([y_daily, actual_train["consumption"]], ignore_index=True)
    # 実績を加えて再学習（alphaは元のモデル選定時のものを流用）
    updated_model = make_daily_model(best_alpha)
    updated_model.fit(X_updated, y_updated)

    # 実績を横持ちに変換
    actual_wide = actual_month.set_index("date")[emp_cols]

    # 残り日数が無い（月内すべて実績が揃っている）場合はそのまま返す
    if len(remaining_days) == 0:
        combined = actual_wide.reset_index()
        combined.insert(0, "date_ym", [f"{d.year}/{d.month}/{d.day}" for d in combined["date"]])
        return combined.drop(columns="date")

    # 残り日数分を、実績を反映したモデルで予測
    remaining_features = build_feature_frame(remaining_days)
    remaining_features["predicted_consumption"] = predict_daily(updated_model, remaining_features[feature_cols])
    remaining_wide = remaining_features.pivot(index="date", columns="emp_id", values="predicted_consumption")[emp_cols]

    # 実績（経過日）＋予測（残り日数）を日付順に結合
    combined = pd.concat([actual_wide, remaining_wide]).sort_index().reset_index()
    combined.insert(0, "date_ym", [f"{d.year}/{d.month}/{d.day}" for d in combined["date"]])
    return combined.drop(columns="date")


# 最新の実績値を取得
latest_month = water_demand["date_ym"].max()
# 予測する月を決定
next_month_dt = latest_month + pd.DateOffset(months=1)
# 社員ごと日ごとの消費量予測（v_water_demand_per_emp.csvと同じ形式のDataFrame）
prediction_df = predict_next_month_per_emp(model, next_month_dt)

if prediction_df is None:
    # 予測できない旨を報告
    print(f"\n予測月 {pd.Period(next_month_dt, 'M')} の出社・営業日カレンダーが不足しています。")
else:
    print()
    print("=" * 40)
    print("【翌月：社員ごと・日ごとの消費量予測（v_water_demand_per_emp.csv形式）】")
    print(prediction_df.round(2).to_string(index=False))
    print("=" * 40)

    ## 月次集計（=翌月の注文量予測）
    prediction = prediction_df[emp_cols].to_numpy().sum()
    # 注文数を計算
    prediction_rounded = np.ceil(prediction / 20) * 20
    # 結果出力
    print()
    print("=" * 40)
    print("【翌月の注文量予測（人ごと日ごとの積み上げ）】")
    print(f"  予測対象月        : {next_month_dt.strftime('%Y年%m月')}")
    print(f"  対象日数          : {len(prediction_df)} 日")
    print(f"  予測注文量        : {prediction:.1f} L")
    print(f"  推奨注文量        : {prediction_rounded:.0f} L  (20L単位に切り上げ)")
    print("=" * 40)

    # v_water_demand_per_emp.csvへの積み上げ例（既存の実績データに予測結果を連結する場合）
    # accumulated = pd.concat([water_demand_per_emp.drop(columns="date"), prediction_df], ignore_index=True)
    # accumulated.to_csv(f"{BASE_DIR}/input_data/v_water_demand_per_emp.csv", index=False)

########################################################################
## 予測対象月の実績が一部得られた場合の再予測（実績を反映して残り日数を予測し直す）
########################################################################

# 予測対象月の実績データ（無ければ空のDataFrームとして扱う）
performance_path = BASE_DIR / "input_data" / "water_demand_performance.csv"
if performance_path.exists():
    water_demand_performance = pd.read_csv(performance_path)
else:
    water_demand_performance = pd.DataFrame(columns=["date_ym"] + emp_cols)

# 実績を反映して残り日数を予測し直した結果
updated_prediction_df = predict_month_with_partial_actuals(next_month_dt, water_demand_performance)

if prediction_df is not None and updated_prediction_df is not None:
    # 当初予測（実績未反映）と、実績反映後の予測を月次合計で比較
    original_total = prediction_df[emp_cols].to_numpy().sum()
    updated_total = updated_prediction_df[emp_cols].to_numpy().sum()
    elapsed_days = len(
        water_demand_performance[
            pd.to_datetime(water_demand_performance["date_ym"]).dt.to_period("M") == pd.Period(next_month_dt, "M")
        ]
    ) if len(water_demand_performance) else 0

    print()
    print("=" * 40)
    print("【実績反映：当初予測 と 実績反映後予測 の比較】")
    print(f"  予測対象月              : {next_month_dt.strftime('%Y年%m月')}")
    print(f"  実績反映済み日数        : {elapsed_days} 日")
    print(f"  当初予測（月合計）      : {original_total:.1f} L")
    print(f"  実績反映後予測（月合計）: {updated_total:.1f} L")
    print(f"  差分                    : {updated_total - original_total:+.1f} L")
    print("=" * 40)
