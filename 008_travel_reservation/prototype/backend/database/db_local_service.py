import os

import pandas as pd

# このファイルの場所を基準にdb_dataディレクトリの絶対パスを組み立てる
DB_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db_data")


# クラス変数定義
class TR_DB():
    def __init__(self):
        self.m_accommodation_plan: pd.DataFrame = pd.DataFrame()
        self.m_hotel: pd.DataFrame = pd.DataFrame()
        self.m_room_capacity: pd.DataFrame = pd.DataFrame()
        self.m_user: pd.DataFrame = pd.DataFrame()
        self.t_reservation: pd.DataFrame = pd.DataFrame()

# クラス変数用意
db_local = TR_DB()


def read_db_data():
    """
    DBのデータに相当するcsvファイルを読み込む
    """
    ## m_accommodation_plan
    # csvファイル読み込み
    try:
        df = pd.read_csv(
            os.path.join(DB_DATA_DIR, "m_accommodation_plan.csv"),
            dtype={
                "hotel_id": int,
                "plan_id": int,
                "area": str,
                "plan_name": str,
                "price": int,
                "room_size": int,
                "has_breakfast": bool,
                "has_lunch": bool,
                "has_dinner": bool,
                "introduction": str,
            }
        )
    except:
        # csv読み込みに失敗した場合
        print("m_accommodation_planのcsvファイルが読み込めませんでした")
        return

    # データが1件も取得できなかった場合はエラー
    if df.empty:
        print("m_accommodation_planのデータが1件も登録されていません")
    else:
        db_local.m_accommodation_plan = df

    ## m_hotel
    # csvファイル読み込み
    try:
        df = pd.read_csv(
            os.path.join(DB_DATA_DIR, "m_hotel.csv"),
            dtype={
                "hotel_id": int,
                "hotel_name": str,
                "address": str,
                "introduction": str,
            }
        )
    except:
        # csv読み込みに失敗した場合
        print("m_hotelのcsvファイルが読み込めませんでした")
        return

    # データが1件も取得できなかった場合はエラー
    if df.empty:
        print("m_hotelのデータが1件も登録されていません")
    else:
        db_local.m_hotel = df

    ## m_room_capacity
    # csvファイル読み込み
    try:
        df = pd.read_csv(
            os.path.join(DB_DATA_DIR, "m_room_capacity.csv"),
            dtype={
                "plan_id": int,
                "capacity": int,
                "date_of_stay": str,
            }
        )
        # 日付型に変換
        df["date_of_stay"] = pd.to_datetime(df["date_of_stay"])
    except:
        # csv読み込みに失敗した場合
        print("m_room_capacityのcsvファイルが読み込めませんでした")
        return

    # データが1件も取得できなかった場合はエラー
    if df.empty:
        print("m_room_capacityのデータが1件も登録されていません")
    else:
        db_local.m_room_capacity = df

    ## m_user
    # csvファイル読み込み
    try:
        df = pd.read_csv(
            os.path.join(DB_DATA_DIR, "m_user.csv"),
            dtype={
                "user_id": int,
                "user_name": str,
                "mail_address": str,
                "password": str,
                "owner_flag": bool,
            }
        )
    except:
        # csv読み込みに失敗した場合
        print("m_userのcsvファイルが読み込めませんでした")
        return

    # データが1件も取得できなかった場合はエラー
    if df.empty:
        print("m_userのデータが1件も登録されていません")
    else:
        db_local.m_user = df

    ## t_reservation
    # csvファイル読み込み
    try:
        df = pd.read_csv(
            os.path.join(DB_DATA_DIR, "t_reservation.csv"),
            dtype={
                "user_id": int,
                "plan_id": str,
                "date_of_stay": str,
                "status": str,
            }
        )
        # 日付型に変換
        df["date_of_stay"] = pd.to_datetime(df["date_of_stay"])
    except:
        # csv読み込みに失敗した場合
        print("t_reservationのcsvファイルが読み込めませんでした")
        return

    # データが1件も取得できなかった場合はエラー
    if df.empty:
        print("t_reservationのデータが1件も登録されていません")
    else:
        db_local.t_reservation = df

    ## 読み込んだデータを表示
    print("===========================================================")
    print("★ 以下のデータが読み込まれました★")
    print("m_accommodation_plan :" + str(len(db_local.m_accommodation_plan)) + "件")
    print("m_hotel              :" + str(len(db_local.m_hotel)) + "件")
    print("m_room_capacity      :" + str(len(db_local.m_room_capacity)) + "件")
    print("m_user               :" + str(len(db_local.m_user)) + "件")
    print("t_reservation        :" + str(len(db_local.t_reservation)) + "件")
    print("===========================================================")
