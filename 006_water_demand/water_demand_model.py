import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error
from sklearn.linear_model import Ridge
from sklearn.model_selection import LeaveOneOut, cross_val_score


## データ読み込み
# 学習用データのパス
BASE_DIR = "C:/azure_ai/education/006_water_demand/train_data"
# 水の注文量
water_demand = pd.read_csv(f"{BASE_DIR}/water_demand.csv")
# JBDカレンダー
jbd_calendar = pd.read_csv(f"{BASE_DIR}/jbd_calendar.csv")
# 社員ごとのAIC出社カレンダー
work_day = pd.read_csv(f"{BASE_DIR}/work_day.csv")
# 気象データ
weather_data = pd.read_csv(f"{BASE_DIR}/weather_data.csv")
# 社員ごとの日次消費量
water_demand_per_emp = pd.read_csv(f"{BASE_DIR}/water_demand_per_emp.csv")

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
# 年月列の作成
water_demand_per_emp["date_ym"] = pd.to_datetime(water_demand_per_emp["date_ym"])
water_demand_per_emp["year_month"] = water_demand_per_emp["date_ym"].dt.to_period("M")

## 月次特徴量作成
# 月ごとの営業日数を集計
monthly_biz_days = (
    jbd_calendar.groupby("year_month")["business_day_flag"]
    .sum()
    .reset_index()
    .rename(columns={"business_day_flag": "business_days"})
)
# 社員情報取得
emp_cols = [c for c in work_day.columns if c.startswith("emp_")]
# 日ごとの出社人数集計
work_day["daily_attendance"] = work_day[emp_cols].sum(axis=1)
# JBDカレンダーの営業日フラグを付与して営業日のみ出社にカウント
work_day = work_day.merge(jbd_calendar[["date", "business_day_flag"]], on="date", how="left")
# カレンダーにない日付は休日とする
work_day["daily_attendance"] = work_day["daily_attendance"] * work_day["business_day_flag"].fillna(0)
# 月ごとの延べ出社人数を合計
monthly_attendance = (
    work_day.groupby("year_month")["daily_attendance"]
    .sum()
    .reset_index()
    .rename(columns={"daily_attendance": "total_attendance"})
)
# 月ごとの平均気温を計算
monthly_weather = (
    weather_data.groupby("year_month")["tavg"]
    .mean()
    .reset_index()
    .rename(columns={"tavg": "tavg_mean"})
)
# 社員ごとの出社1日あたり平均消費量を算出（0Lの日は欠勤とみなして除外）
emp_cols_consumption = [c for c in water_demand_per_emp.columns if c.startswith("emp_")]
per_emp_rate = {
    col: (lambda s: s[s > 0].mean() if (s > 0).any() else 0.0)(water_demand_per_emp[col])
    for col in emp_cols_consumption
}

## 学習データ構築
# 水の注文量に月ごとの営業日を連結
df = water_demand.merge(monthly_biz_days, on="year_month", how="left")
# 月ごとの延べ出社人数を連結
df = df.merge(monthly_attendance, on="year_month", how="left")
# 月ごとの平均気温を連結
df = df.merge(monthly_weather, on="year_month", how="left")
# 月ごとの平均出社人数を計算
df["attendance_rate"] = df["total_attendance"] / df["business_days"]
# 特徴量として[月ごとの営業日, 月ごとの平均出社人数, 月ごとの平均気温]を採用
feature_cols = ["business_days", "attendance_rate", "tavg_mean"]
# 必要な列のみ抽出
df_train = df.dropna(subset=feature_cols + ["order_quantity"])
# 学習用データ分割
X = df_train[feature_cols]
y = df_train["order_quantity"]

## alpha設定
# Ridge回帰 + 正則化強度alphaをLOO-CVで比較
print("=" * 40)
print("【alpha別 LOO-CV MAE】")
# 定数用意
best_alpha = None
best_mae = float("inf")
# 最適alpha候補を順番に試す
for alpha in [0.01, 0.1, 1.0, 10.0, 50.0, 100.0]:
    # Ridge回帰
    ridge = Ridge(alpha=alpha)
    # LOO
    loo = LeaveOneOut()
    # CVでscore測定
    scores = cross_val_score(ridge, X, y, cv=loo, scoring="neg_mean_absolute_error")
    # MAE(Mean Absolute Error)計算
    mae = -scores.mean()
    # 最良か判定
    marker = " ← 最良" if mae < best_mae else ""
    # 結果出力
    print(f"  alpha={alpha:>6}: LOO-CV MAE = {mae:.2f} L{marker}")
    # 最良の場合は定数更新
    if mae < best_mae:
        best_mae = mae
        best_alpha = alpha
# 最良alpha決定
print(f"\n  採用alpha: {best_alpha}")
print("=" * 40)

## 最良alphaで改めて学習
# モデル用意
model = Ridge(alpha=best_alpha)
# 学習
model.fit(X, y)
# 学習用データでモデル評価
y_pred_train = model.predict(X)
# 誤差計算
train_mae = mean_absolute_error(y, y_pred_train)
# LOO
loo = LeaveOneOut()
# CVでLOOのscore測定
loo_scores = cross_val_score(model, X, y, cv=loo, scoring="neg_mean_absolute_error")
# 符号を戻す
loo_errors = -loo_scores
# 結果の表示
print()
print("=" * 40)
print("【LOO-CV 評価結果】")
# 月ごとに実績値と予測誤差を出力
for i, (err, actual) in enumerate(zip(loo_errors, y)):
    # 年月抽出
    ym = df_train["date_ym"].iloc[i].strftime("%Y-%m")
    # 結果表示
    print(f"  {ym}: 実績={actual:.0f}L, 絶対誤差={err:.1f}L")
print()
print(f"  学習データMAE（自己採点） : {train_mae:.2f} L")
print(f"  LOO-CV MAE（実力値）     : {loo_errors.mean():.2f} L")
print("=" * 40)

## 翌月の予測
# 最新の実績値を取得
latest_month = water_demand["date_ym"].max()
# 予測する月を決定
next_month_dt = latest_month + pd.DateOffset(months=1)
# 年月に変換
next_period = pd.Period(next_month_dt, "M")
# 予測月の営業日数を抽出
next_biz = monthly_biz_days.loc[monthly_biz_days["year_month"] == next_period, "business_days"]
# 予測月の出社状況を抽出
next_att = monthly_attendance.loc[monthly_attendance["year_month"] == next_period, "total_attendance"]
# 予測月の営業日と出社状況のデータが不足している場合
if next_biz.empty or next_att.empty:
    # 予測できない旨を報告
    print(f"\n予測月 {next_period} のカレンダーデータが不足しています。")
else:
    ## Seriesから要素を抽出
    # 営業日
    next_biz_val = next_biz.values[0]
    # 出社比率
    next_att_rate = next_att.values[0] / next_biz_val
    # 予測月の前年を計算
    prev_year_period = pd.Period(next_month_dt - pd.DateOffset(years=1), "M")
    # 前年度の平均気温データを抽出
    tavg_prev_year = monthly_weather.loc[monthly_weather["year_month"] == prev_year_period, "tavg_mean"]
    # 平均気温データが抽出できなかった場合
    if tavg_prev_year.empty:
        # 予測できない旨を報告
        print(f"\n前年同月（{prev_year_period}）の気温データがありません。")
    else:
        # Seriesから平均気温を抽出
        tavg_val = tavg_prev_year.values[0]
        # 予測に必要なデータ用意
        X_pred = pd.DataFrame([{
            "business_days": next_biz_val,
            "attendance_rate": next_att_rate,
            "tavg_mean": tavg_val,
        }])
        # 予測実行
        prediction = model.predict(X_pred)[0]
        # 注文数を計算
        prediction_rounded = np.ceil(prediction / 20) * 20
        # 結果出力
        print()
        print("=" * 40)
        print("【翌月の注文量予測】")
        print(f"  予測対象月        : {next_month_dt.strftime('%Y年%m月')}")
        print(f"  営業日数          : {next_biz_val:.0f} 日")
        print(f"  1日あたり出勤人数 : {next_att_rate:.1f} 人/日")
        print(f"  月平均気温（代替） : {tavg_val:.1f} 前年同月実績値")
        print(f"  予測注文量        : {prediction:.1f} L")
        print(f"  推奨注文量        : {prediction_rounded:.0f} L  (20L単位に切り上げ)")
        print("=" * 40)

## ボトムアップ予測（社員別消費量ベース）
# 予測月の社員別出社予定日数を抽出
next_work = work_day[work_day["year_month"] == next_period]
# 予測月の出社予定データが不足している場合
if next_work.empty:
    print(f"\n予測月 {next_period} の出社予定データが不足しています。")
else:
    # 社員ごとに「出社1日あたり平均消費量 × 予測月の出社予定日数」を積み上げ
    bottom_up_detail = {
        col: per_emp_rate[col] * next_work[col].sum()
        for col in emp_cols_consumption
        if col in next_work.columns
    }
    # 合計消費量を算出
    bottom_up_total = sum(bottom_up_detail.values())
    # 注文数を計算
    bottom_up_rounded = np.ceil(bottom_up_total / 20) * 20
    # 結果出力
    print()
    print("=" * 40)
    print("【翌月の注文量予測（ボトムアップ：社員別消費量ベース）】")
    for col, val in bottom_up_detail.items():
        print(f"  {col}: 出社1日あたり{per_emp_rate[col]:.2f}L × 出社予定{next_work[col].sum():.0f}日 = {val:.1f}L")
    print(f"  予測注文量        : {bottom_up_total:.1f} L")
    print(f"  推奨注文量        : {bottom_up_rounded:.0f} L  (20L単位に切り上げ)")
    print("  ※社員別消費量データは1か月分の実績のため、参考値・トップダウン予測との比較用です。")
    print("=" * 40)
