import os
import datetime
import requests

import pandas as pd

## 定数
# AICの緯度
AIC_LAT = 35.698568
# AICの経度
AIC_LON = 139.779358
# APIホスト
RAPIDAPI_HOST = "meteostat.p.rapidapi.com"
# APIエンドポイント
ENDPOINT = f"https://{RAPIDAPI_HOST}/point/daily"


def get_daily_weather(start_date: datetime.datetime, end_date: datetime.datetime) -> pd.DataFrame:
    """
    https://dev.meteostat.net/api/point/daily
    指定した期間の日次気象データを Meteostat API から取得する
    ※1回のリクエストで取得できるのは10年分まで
    ※リクエスト回数は500回/月

    API Responseデータ
    ----------------------
    - date  : 日付 (YYYY-MM-DD)
    - tavg  : 平均気温 [℃]
    - tmin  : 最低気温 [℃]
    - tmax  : 最高気温 [℃]
    - prcp  : 降水量 [mm]
    - snow  : 積雪深 [mm]
    - wdir  : 平均風向 [°]
    - wspd  : 平均風速 [km/h]
    - wpgt  : 最大瞬間風速 [km/h]
    - pres  : 海面気圧 [hPa]
    - tsun  : 日照時間 [分]

    Args
    ----------------------
    - start_date: datetime.datetime,        取得開始日
    - end_date: datetime.datetime,          取得終了日

    Returns
    ----------------------
    - result_df: pd.DataFrame,              気象データ
        - date: datetime64[ns],             日付 (YYYY-MM-DD)
        - tavg: float,                      平均気温 [℃]
        - tmin: float,                      最低気温 [℃]
        - tmax: float,                      最高気温 [℃]
    """
    ## 接続準備
    # 環境変数からAPIキー取得
    api_key = os.environ.get("RAPIDAPI_KEY")
    # キーが取得できなかった場合
    if not api_key:
        # エラーを報告
        raise EnvironmentError("環境変数 RAPIDAPI_KEY が設定されていません。")

    ## データの取得
    # 日付の型変換
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")
    # パラメータ作成
    params = {
        "lat": AIC_LAT,
        "lon": AIC_LON,
        "start": start_date_str,
        "end": end_date_str,
    }
    # ヘッダ作成
    headers = {
        "x-rapidapi-host": RAPIDAPI_HOST,
        "x-rapidapi-key": api_key,
    }
    # リクエスト送信
    print("=========================== 気候データ取得開始 ===========================")
    response = requests.get(ENDPOINT, params=params, headers=headers, timeout=10)
    # 通信に失敗した場合はエラーを報告
    response.raise_for_status()
    # 取得したデータをJSON形式に変換
    json_list = response.json().get("data", [])
    print("取得開始日 :", start_date)
    print("取得終了日 :", end_date)
    print("取得したデータ数 :" + str(len(json_list)) + "件")
    # データが取得できなかった場合
    if not json_list:
        # 空のDataFrameを返却
        empty_df = pd.DataFrame(columns=["date", "tavg", "tmin", "tmax"]).astype({"tavg": float, "tmin": float, "tmax": float})
        empty_df["date"] = pd.to_datetime(empty_df["date"])
        return empty_df

    ## レスポンス整形
    # 必要な列のみ抽出
    df = pd.DataFrame(json_list)[["date", "tavg", "tmin", "tmax"]]
    # 型変換
    df["date"] = pd.to_datetime(df["date"])
    # 整形したデータを返却
    return df


if __name__ == "__main__":
    from dotenv import load_dotenv

    # 環境変数読み込み
    load_dotenv()
    # データ取得
    result_df = get_daily_weather(datetime.datetime(2024, 10, 1), datetime.datetime(2026, 5, 31))
    # csv出力
    print("=========================== 気候データcsv出力 ===========================")
    result_df.to_csv(r"C:\azure_ai\education\006_water_demand\raw_data\weather_data.csv", index=False)
