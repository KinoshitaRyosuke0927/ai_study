import os
from typing import Optional

import pandas as pd

from common.constants import ACTIVE_RESERVATION_STATUS_CODES
from database.db_local_service import db_local, DB_DATA_DIR


############################################################
## m_userテーブル
############################################################
def select_user(mail_address: str) -> pd.DataFrame:
    """
    m_userテーブルから該当するメールアドレスを持つユーザの情報を取得する

    Args
    -----------------
    - mail_address: str,            ユーザのメールアドレス

    Returns
    -----------------
    - df: pd.DataFrame,             取得したユーザ情報

    """
    # テーブルデータ取得
    df_user = db_local.m_user
    # 必要な列のみ絞り込み
    df = df_user.loc[df_user["mail_address"] == mail_address].copy()
    # パスワードについては照合のためByte文字に変換
    df.loc[:, "password"] = df["password"].astype(bytes)

    return df


############################################################
## m_accommodation_planテーブル
############################################################
def select_plan(key_word: str) -> pd.DataFrame:
    """
    m_accommodation_planテーブルから検索ワードにヒットする情報を取得する

    Args
    -----------------
    - key_word: str,                検索ワード

    Returns
    -----------------
    - df: pd.DataFrame,             取得した宿泊プラン情報

    """
    # テーブルデータ取得
    df_hotel = db_local.m_hotel.copy()
    df_plan = db_local.m_accommodation_plan.copy()
    # key_wordが空文字の場合は空のDataFrameを返す
    if not key_word:
        return pd.DataFrame(columns=["hotel_id", "hotel_name", "plan_id", "plan_name", "price"])

    # ホテル名で絞り込み(英字の大文字・小文字は区別しない)
    df_hotel = df_hotel[df_hotel["hotel_name"].str.contains(key_word, case=False, na=False)]
    # 宿泊プランと結合して必要な列のみ抽出
    df = pd.merge(df_hotel, df_plan, on="hotel_id", how="left")[
        ["hotel_id", "hotel_name", "plan_id", "plan_name", "price"]
    ]

    return df


def select_plan_detail(plan_id: int) -> pd.DataFrame:
    """
    m_accommodation_planテーブルとm_hotelテーブルからplan_idに一致する宿泊プランの詳細情報を取得する

    Args
    -----------------
    - plan_id: int,                 宿泊プランID

    Returns
    -----------------
    - df: pd.DataFrame,             取得した宿泊プラン詳細情報(該当なしの場合は空)

    """
    # テーブルデータ取得
    df_hotel = db_local.m_hotel.copy()
    df_plan = db_local.m_accommodation_plan.copy()
    # plan_idで絞り込み
    df_plan = df_plan[df_plan["plan_id"] == plan_id]
    # ホテル情報と結合し、必要な列のみ抽出
    df = pd.merge(df_plan, df_hotel, on="hotel_id", how="left", suffixes=("", "_hotel")).rename(
        columns={"address": "hotel_address", "introduction_hotel": "hotel_introduction"}
    )[
        [
            "hotel_id", "hotel_name", "hotel_address", "hotel_introduction",
            "plan_id", "plan_name", "price", "area", "room_size",
            "has_breakfast", "has_lunch", "has_dinner", "introduction",
        ]
    ]

    return df


############################################################
## t_reservationテーブル
############################################################
def select_reservations(user_id: int) -> pd.DataFrame:
    """
    t_reservationテーブルから該当ユーザの予約情報を、宿泊プラン・ホテル情報と結合して取得する

    Args
    -----------------
    - user_id: int,                 ユーザID

    Returns
    -----------------
    - df: pd.DataFrame,             予約日昇順に並んだ予約情報(該当なしの場合は空)

    """
    # テーブルデータ取得
    df_reservation = db_local.t_reservation.copy()
    df_plan = db_local.m_accommodation_plan.copy()
    df_hotel = db_local.m_hotel.copy()
    # user_idで絞り込み
    df_reservation = df_reservation[df_reservation["user_id"] == user_id].copy()
    # plan_idの型をm_accommodation_planに合わせて結合できるようにする
    df_reservation.loc[:, "plan_id"] = df_reservation["plan_id"].astype(int)
    # 宿泊プラン・ホテル情報と結合し、予約日昇順に並び替えて必要な列のみ抽出
    df = pd.merge(df_reservation, df_plan, on="plan_id", how="left")
    df = pd.merge(df, df_hotel, on="hotel_id", how="left")
    df = df.sort_values("date_of_stay")[
        ["hotel_id", "hotel_name", "plan_id", "plan_name", "price", "date_of_stay", "status"]
    ]

    return df


def select_plan_capacity(plan_id: int) -> Optional[int]:
    """
    m_accommodation_planテーブルからplan_idに一致する宿泊プランの1日あたりの最大部屋数を取得する

    Args
    -----------------
    - plan_id: int,                 宿泊プランID

    Returns
    -----------------
    - capacity: Optional[int],      1日あたりの最大部屋数(該当プランが存在しない場合はNone)

    """
    df_plan = db_local.m_accommodation_plan
    df_plan = df_plan[df_plan["plan_id"] == plan_id]
    if df_plan.empty:
        return None

    return int(df_plan["capacity"].values[0])


def select_reservation_counts(plan_id: int) -> pd.Series:
    """
    t_reservationテーブルから、指定プランについて日付ごとの有効な予約件数(キャンセルを除く)を取得する

    Args
    -----------------
    - plan_id: int,                 宿泊プランID

    Returns
    -----------------
    - counts: pd.Series,            日付(Timestamp)をインデックスとした予約件数

    """
    df = db_local.t_reservation.copy()
    # plan_idの型をm_accommodation_planに合わせて比較できるようにする
    df.loc[:, "plan_id"] = df["plan_id"].astype(int)
    # 対象プラン、かつキャンセルされていない予約のみに絞り込む
    df = df[(df["plan_id"] == plan_id) & (df["status"].isin(ACTIVE_RESERVATION_STATUS_CODES))]

    return df.groupby("date_of_stay").size()


def insert_reservation(user_id: int, plan_id: int, date_of_stay: pd.Timestamp) -> None:
    """
    t_reservationテーブルに新しい予約を1件追加する(メモリ上のデータ・csvファイルの両方を更新する)

    Args
    -----------------
    - user_id: int,                     予約するユーザのID
    - plan_id: int,                     予約する宿泊プランID
    - date_of_stay: pd.Timestamp,       宿泊日

    """
    # 予約中ステータスで1件分のデータを作成し、メモリ上のt_reservationに追加する
    new_row = pd.DataFrame([{
        "user_id": user_id,
        "plan_id": str(plan_id),
        "date_of_stay": date_of_stay,
        "status": "1",
    }])
    db_local.t_reservation = pd.concat([db_local.t_reservation, new_row], ignore_index=True)

    # DBの代わりとなるcsvファイルにも同じ内容を追記して永続化する(既存データと同じ日付表記に合わせる)
    date_label = f"{date_of_stay.year}/{date_of_stay.month}/{date_of_stay.day}"
    csv_path = os.path.join(DB_DATA_DIR, "t_reservation.csv")
    with open(csv_path, "a", encoding="utf-8", newline="") as f:
        f.write(f"{user_id},{plan_id},{date_label},1\n")
