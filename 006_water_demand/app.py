import sys
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sklearn.linear_model import Ridge
from sklearn.model_selection import LeaveOneOut, cross_val_score

## 定数
# ベースディレクトリ(exe実行時はexe本体のディレクトリ、通常実行時はスクリプトのディレクトリ)
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent
# 水の注文量実績CSVパス
DATA_PATH = BASE_DIR/"train_data"/"water_demand.csv"
# AIC出社カレンダーCSVパス
WORK_DAY_PATH = BASE_DIR/"train_data"/"work_day.csv"
# JBD営業日カレンダーCSVパス
JBD_CALENDAR_PATH = BASE_DIR/"train_data"/"jbd_calendar.csv"
# 気候情報CSVパス
WEATHER_DATA_PATH = BASE_DIR/"train_data"/"weather_data.csv"

## アプリケーション初期化
# FastAPIインスタンス生成
app = FastAPI()
# テンプレートディレクトリ設定
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ── メニュー ──────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def menu(request: Request):
    # メニュー画面を返却
    return templates.TemplateResponse("menu.html", {"request": request})


# ── 水の注文量登録 ─────────────────────────────────────────

@app.get("/water_demand", response_class=HTMLResponse)
async def water_demand_page(request: Request):
    # 注文量実績CSVを読み込み
    df = pd.read_csv(DATA_PATH)
    # テンプレートに渡す行データを構築
    rows = []
    for _, row in df.iterrows():
        rem = row["remaining_quantity"]
        rows.append({
            "date_ym": row["date_ym"],
            "order_quantity": float(row["order_quantity"]),
            # 残量が欠損の場合は空文字で渡す
            "remaining_quantity": "" if pd.isna(rem) else float(rem),
        })
    # 年月の新しい順に並び替え
    rows.sort(key=lambda r: r["date_ym"], reverse=True)
    return templates.TemplateResponse("water_demand.html", {"request": request, "rows": rows})


@app.post("/water_demand/save")
async def water_demand_save(request: Request):
    # リクエストボディを取得
    data = await request.json()
    # 各行のデータを整形
    records = []
    for r in data.get("rows", []):
        records.append({
            "date_ym": r["date_ym"],
            "order_quantity": r["order_quantity"],
            # 残量が空文字の場合はNoneとして保存
            "remaining_quantity": r["remaining_quantity"] if r["remaining_quantity"] != "" else None,
        })
    # DataFrameに変換してCSV保存
    df = pd.DataFrame(records, columns=["date_ym", "order_quantity", "remaining_quantity"])
    df.to_csv(DATA_PATH, index=False)
    return JSONResponse({"status": "ok"})


# ── 出社状況登録 ───────────────────────────────────────────

@app.get("/work_day", response_class=HTMLResponse)
async def work_day_page(request: Request):
    # 出社カレンダーCSVを読み込み
    df = pd.read_csv(WORK_DAY_PATH)
    df["date"] = pd.to_datetime(df["date"])
    # カレンダーの期間（表示用）を取得
    min_date = df["date"].min().strftime("%Y年%m月%d日")
    max_date = df["date"].max().strftime("%Y年%m月%d日")
    # 社員列を抽出
    emp_cols = [c for c in df.columns if c.startswith("emp_")]
    return templates.TemplateResponse("work_day.html", {
        "request": request,
        "min_date": min_date,
        "max_date": max_date,
        "employees": emp_cols,
    })


@app.get("/work_day/data")
async def work_day_data(emp: str):
    # 出社カレンダーCSVを読み込み
    df = pd.read_csv(WORK_DAY_PATH)
    df["date"] = pd.to_datetime(df["date"])
    # 指定された社員列が存在しない場合はエラーを返す
    if emp not in df.columns:
        return JSONResponse({"error": "invalid employee"}, status_code=400)
    # 日付をキー, 出社フラグを値とした辞書を返却
    data = {
        row["date"].strftime("%Y-%m-%d"): int(row[emp])
        for _, row in df.iterrows()
    }
    return JSONResponse(data)


@app.post("/work_day/save")
async def work_day_save(request: Request):
    # リクエストボディを取得
    body = await request.json()
    emp = body.get("emp")
    data = body.get("data", {})
    # 出社カレンダーCSVを読み込み
    df = pd.read_csv(WORK_DAY_PATH)
    # 指定された社員列が存在しない場合はエラーを返す
    if emp not in df.columns:
        return JSONResponse({"error": "invalid employee"}, status_code=400)
    # 日付列を一時的にdatetime型に変換してマスク処理を行う
    df["_parsed"] = pd.to_datetime(df["date"])
    # 変更対象の日付・フラグを上書き
    for date_str, val in data.items():
        mask = df["_parsed"] == pd.to_datetime(date_str)
        if mask.any():
            df.loc[mask, emp] = int(val)
    # 一時列を削除してCSV保存
    df = df.drop(columns=["_parsed"])
    df.to_csv(WORK_DAY_PATH, index=False)
    return JSONResponse({"status": "ok"})


# ── 注文量予測 ────────────────────────────────────────────

def _data_source_info() -> dict:
    """
    使用データの参照期間・更新日時を返す
    """
    ## 日付フォーマット定数
    fmt_dt  = "%Y/%m/%d %H:%M:%S"
    fmt_day = "%Y/%m/%d"
    fmt_ym  = "%Y/%m"

    def mtime(path):
        # ファイルの最終更新日時を取得
        return datetime.fromtimestamp(path.stat().st_mtime).strftime(fmt_dt)

    ## 水の注文量実績
    df_wd = pd.read_csv(DATA_PATH)
    df_wd["date_ym"] = pd.to_datetime(df_wd["date_ym"])
    # 最小・最大年月を結合して参照期間文字列を生成
    water_period = (
        df_wd["date_ym"].min().strftime(fmt_ym)
        + " 〜 "
        + df_wd["date_ym"].max().strftime(fmt_ym)
    )

    ## JBD営業日カレンダー
    df_jbd = pd.read_csv(JBD_CALENDAR_PATH)
    df_jbd["date"] = pd.to_datetime(df_jbd["date"])
    # 最小・最大日付を結合して参照期間文字列を生成
    jbd_period = (
        df_jbd["date"].min().strftime(fmt_day)
        + " 〜 "
        + df_jbd["date"].max().strftime(fmt_day)
    )

    ## AIC出社カレンダー
    df_wd2 = pd.read_csv(WORK_DAY_PATH)
    df_wd2["date"] = pd.to_datetime(df_wd2["date"])
    # 最小・最大日付を結合して参照期間文字列を生成
    work_period = (
        df_wd2["date"].min().strftime(fmt_day)
        + " 〜 "
        + df_wd2["date"].max().strftime(fmt_day)
    )

    ## 気候情報（欠損行除外）
    df_w = pd.read_csv(WEATHER_DATA_PATH)
    df_w["date"] = pd.to_datetime(df_w["date"])
    # 欠損行を除外して実データの期間のみを対象とする
    df_w_clean = df_w.dropna()
    weather_period = (
        df_w_clean["date"].min().strftime(fmt_day)
        + " 〜 "
        + df_w_clean["date"].max().strftime(fmt_day)
    )

    # 各データソースの情報を返却
    return [
        {"name": "水の注文量実績", "period": water_period, "mtime": mtime(DATA_PATH)},
        {"name": "JBD営業日カレンダー", "period": jbd_period, "mtime": mtime(JBD_CALENDAR_PATH)},
        {"name": "AIC出社カレンダー", "period": work_period, "mtime": mtime(WORK_DAY_PATH)},
        {"name": "気候情報", "period": weather_period, "mtime": mtime(WEATHER_DATA_PATH)},
    ]


def _run_prediction() -> dict:
    """
    翌月の注文量をRidge回帰で予測して結果を返す
    """
    ## データ読み込み
    # 水の注文量実績
    water_demand = pd.read_csv(DATA_PATH)
    # JBD営業日カレンダー
    jbd_calendar = pd.read_csv(JBD_CALENDAR_PATH)
    # AIC出社カレンダー
    work_day_df = pd.read_csv(WORK_DAY_PATH)
    # 気候情報
    weather_data = pd.read_csv(WEATHER_DATA_PATH)

    ## 前処理
    # 年月列の作成
    water_demand["date_ym"] = pd.to_datetime(water_demand["date_ym"])
    water_demand["year_month"] = water_demand["date_ym"].dt.to_period("M")
    # 年月列の作成
    jbd_calendar["date"] = pd.to_datetime(jbd_calendar["date"])
    jbd_calendar["year_month"] = jbd_calendar["date"].dt.to_period("M")
    # 年月列の作成
    work_day_df["date"] = pd.to_datetime(work_day_df["date"])
    work_day_df["year_month"] = work_day_df["date"].dt.to_period("M")
    # 年月列の作成
    weather_data["date"] = pd.to_datetime(weather_data["date"])
    weather_data["year_month"] = weather_data["date"].dt.to_period("M")

    ## 月次特徴量作成
    # 月ごとの営業日数を集計
    monthly_biz_days = (
        jbd_calendar.groupby("year_month")["business_day_flag"]
        .sum().reset_index()
        .rename(columns={"business_day_flag": "business_days"})
    )

    # 社員列を抽出
    emp_cols = [c for c in work_day_df.columns if c.startswith("emp_")]
    # 日ごとの出社人数を集計
    work_day_df["daily_attendance"] = work_day_df[emp_cols].sum(axis=1)
    # JBDカレンダーの営業日フラグを付与して営業日のみ出社にカウント
    work_day_df = work_day_df.merge(jbd_calendar[["date", "business_day_flag"]], on="date", how="left")
    # カレンダーにない日付は休日とする
    work_day_df["daily_attendance"] *= work_day_df["business_day_flag"].fillna(0)
    # 月ごとの延べ出社人数を合計
    monthly_attendance = (
        work_day_df.groupby("year_month")["daily_attendance"]
        .sum().reset_index()
        .rename(columns={"daily_attendance": "total_attendance"})
    )

    # 月ごとの平均気温を計算
    monthly_weather = (
        weather_data.groupby("year_month")["tavg"]
        .mean().reset_index()
        .rename(columns={"tavg": "tavg_mean"})
    )

    ## 学習データ構築
    # 水の注文量に月ごとの営業日数を連結
    df = water_demand.merge(monthly_biz_days, on="year_month", how="left")
    # 月ごとの延べ出社人数を連結
    df = df.merge(monthly_attendance, on="year_month", how="left")
    # 月ごとの平均気温を連結
    df = df.merge(monthly_weather, on="year_month", how="left")
    # 月ごとの平均出社人数を計算
    df["attendance_rate"] = df["total_attendance"] / df["business_days"]

    # 特徴量として[月ごとの営業日数, 月ごとの平均出社人数, 月ごとの平均気温]を採用
    feature_cols = ["business_days", "attendance_rate", "tavg_mean"]
    # 必要な列が欠損している行を除外
    df_train = df.dropna(subset=feature_cols + ["order_quantity"])
    # 学習データ分割
    X = df_train[feature_cols]
    y = df_train["order_quantity"]

    ## alpha設定
    # Ridge回帰 + 正則化強度alphaをLOO-CVで比較して最適値を選択
    best_alpha, best_mae = None, float("inf")
    for alpha in [0.01, 0.1, 1.0, 10.0, 50.0, 100.0]:
        # 負の平均絶対誤差により評価
        scores = cross_val_score(
            Ridge(alpha=alpha), X, y, cv=LeaveOneOut(),
            scoring="neg_mean_absolute_error"
        )
        mae = -scores.mean()
        # MAEが改善した場合は最良alphaを更新
        if mae < best_mae:
            best_mae, best_alpha = mae, alpha

    ## 最良alphaで改めて学習
    model = Ridge(alpha=best_alpha)
    model.fit(X, y)

    ## 予測月の決定
    # 最新の実績月を取得
    latest_month = water_demand["date_ym"].max()
    # 翌月を予測対象月とする
    next_month_dt = latest_month + pd.DateOffset(months=1)
    # Period型に変換
    next_period = pd.Period(next_month_dt, "M")

    # 予測月の営業日数を抽出
    next_biz = monthly_biz_days.loc[monthly_biz_days["year_month"] == next_period, "business_days"]
    # 予測月の出社状況を抽出
    next_att = monthly_attendance.loc[monthly_attendance["year_month"] == next_period, "total_attendance"]

    # 予測月のカレンダーデータが不足している場合はエラーを返す
    if next_biz.empty or next_att.empty:
        return {"error": f"予測月 {next_period} のカレンダーデータが不足しています"}

    # Seriesから営業日数・出社比率を抽出
    next_biz_val = float(next_biz.values[0])
    next_att_rate = float(next_att.values[0]) / next_biz_val
    # 気温は前年同月実績値を使用
    prev_year_period = pd.Period(next_month_dt - pd.DateOffset(years=1), "M")
    tavg_row = monthly_weather.loc[monthly_weather["year_month"] == prev_year_period, "tavg_mean"]

    # 前年同月の気温データが存在しない場合はエラーを返す
    if tavg_row.empty:
        return {"error": f"前年同月（{prev_year_period}）の気温データがありません"}

    # Seriesから平均気温を抽出
    tavg_val = float(tavg_row.values[0])
    # 予測に必要な特徴量を用意
    X_pred = pd.DataFrame([{
        "business_days": next_biz_val,
        "attendance_rate": next_att_rate,
        "tavg_mean": tavg_val,
    }])
    # 予測実行
    prediction = float(model.predict(X_pred)[0])
    # 20L単位に切り上げて推奨注文量を計算
    prediction_rounded = int(np.ceil(prediction / 20) * 20)

    # 予測結果を返却
    return {
        "target_month": next_month_dt.strftime("%Y年%m月"),
        "date_ym_csv": next_month_dt.strftime("%Y/%m/%d"),
        "business_days": int(next_biz_val),
        "attendance_rate": round(next_att_rate, 1),
        "tavg_prev_year": round(tavg_val, 1),
        "prediction": round(prediction, 1),
        "prediction_rounded": prediction_rounded,
    }


@app.get("/predict/data-info")
async def predict_data_info():
    # 使用データの参照期間・更新日時を返却
    return JSONResponse(_data_source_info())


@app.get("/predict", response_class=HTMLResponse)
async def predict_page(request: Request):
    # 使用データ情報を取得してテンプレートに渡す
    info = _data_source_info()
    return templates.TemplateResponse("predict.html", {"request": request, "info": info})


@app.post("/predict/run")
def predict_run():
    # 予測を実行して結果を返却
    return JSONResponse(_run_prediction())


@app.post("/predict/update-weather")
def update_weather():
    # 気候情報を最新化してCSVに上書き保存する
    try:
        from dotenv import load_dotenv
        # .envファイルからAPIキーを読み込む
        load_dotenv()
        from weather_data_service import get_daily_weather
        # 取得開始日を固定、終了日は今日とする
        start = datetime(2024, 10, 1)
        end   = datetime.now()
        df = get_daily_weather(start, end)
        df.to_csv(WEATHER_DATA_PATH, index=False)
        return JSONResponse({"status": "ok"})
    except EnvironmentError as e:
        # APIキー未設定などの環境エラー
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        # APIリクエスト失敗などの予期せぬエラー
        return JSONResponse({"error": f"データ取得に失敗しました: {e}"}, status_code=500)


@app.post("/predict/register")
async def predict_register(request: Request):
    # リクエストボディから年月と注文量を取得
    body = await request.json()
    date_ym = body.get("date_ym")
    order_quantity = body.get("order_quantity")
    # 既存CSVを読み込んで新行を追加
    df = pd.read_csv(DATA_PATH)
    new_row = pd.DataFrame([{
        "date_ym": date_ym,
        "order_quantity": order_quantity,
        # 残量は空欄で登録
        "remaining_quantity": None,
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(DATA_PATH, index=False)
    return JSONResponse({"status": "ok"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
