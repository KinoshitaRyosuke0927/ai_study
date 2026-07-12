from typing import Optional

import pandas as pd
from sqlalchemy import bindparam, text

from common.constants import ACTIVE_RESERVATION_STATUS_CODES
from database.db_connection import get_engine


############################################################
## ログイン
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
    sql = text(
        "SELECT user_id, user_name, mail_address, password, owner_flag "
        "FROM m_user WHERE mail_address = :mail_address"
    )
    df = pd.read_sql(sql, get_engine(), params={"mail_address": mail_address})
    # パスワードについては照合のためByte文字に変換
    df.loc[:, "password"] = df["password"].astype(bytes)

    return df


############################################################
## 旅行者向け:宿泊プラン検索
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
    # key_wordが空文字の場合は空のDataFrameを返す
    if not key_word:
        return pd.DataFrame(columns=["hotel_id", "hotel_name", "plan_id", "plan_name", "price"])

    # ホテル名で絞り込み(DBのcollationがci=大文字小文字を区別しないため、そのままLIKEで絞り込める)
    sql = text(
        "SELECT h.hotel_id, h.hotel_name, p.plan_id, p.plan_name, p.price "
        "FROM m_hotel h "
        "LEFT JOIN m_accommodation_plan p ON h.hotel_id = p.hotel_id "
        "WHERE h.hotel_name LIKE :pattern"
    )
    df = pd.read_sql(sql, get_engine(), params={"pattern": f"%{key_word}%"})

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
    sql = text(
        "SELECT p.hotel_id, h.hotel_name, h.address AS hotel_address, h.introduction AS hotel_introduction, "
        "       p.plan_id, p.plan_name, p.price, p.area, p.room_size, "
        "       p.has_breakfast, p.has_lunch, p.has_dinner, p.introduction "
        "FROM m_accommodation_plan p "
        "LEFT JOIN m_hotel h ON p.hotel_id = h.hotel_id "
        "WHERE p.plan_id = :plan_id"
    )
    df = pd.read_sql(sql, get_engine(), params={"plan_id": plan_id})
    if not df.empty:
        df = df.astype({"has_breakfast": bool, "has_lunch": bool, "has_dinner": bool})

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
    sql = text("SELECT capacity FROM m_accommodation_plan WHERE plan_id = :plan_id")
    df = pd.read_sql(sql, get_engine(), params={"plan_id": plan_id})
    if df.empty:
        return None

    return int(df["capacity"].values[0])


def select_reservation_counts(plan_id: int) -> pd.Series:
    """
    t_reservationテーブルから、指定プランについて日付ごとのキャンセルを除く有効な予約件数を取得する

    Args
    -----------------
    - plan_id: int,                 宿泊プランID

    Returns
    -----------------
    - counts: pd.Series,            日付(Timestamp)をインデックスとした予約件数

    """
    sql = text(
        "SELECT date_of_stay, COUNT(*) AS reservation_count "
        "FROM t_reservation "
        "WHERE plan_id = :plan_id AND status IN :status_codes "
        "GROUP BY date_of_stay"
    ).bindparams(bindparam("status_codes", expanding=True))
    df = pd.read_sql(
        sql,
        get_engine(),
        params={"plan_id": plan_id, "status_codes": tuple(ACTIVE_RESERVATION_STATUS_CODES)},
        parse_dates=["date_of_stay"],
    )

    return df.set_index("date_of_stay")["reservation_count"]


def insert_reservation(user_id: int, plan_id: int, date_of_stay: pd.Timestamp) -> None:
    """
    t_reservationテーブルに新しい予約を1件追加する

    Args
    -----------------
    - user_id: int,                     予約するユーザのID
    - plan_id: int,                     予約する宿泊プランID
    - date_of_stay: pd.Timestamp,       宿泊日

    """
    sql = text(
        "INSERT INTO t_reservation (user_id, plan_id, date_of_stay, status) "
        "VALUES (:user_id, :plan_id, :date_of_stay, '1')"
    )
    with get_engine().begin() as conn:
        conn.execute(sql, {"user_id": user_id, "plan_id": plan_id, "date_of_stay": date_of_stay.date()})


############################################################
## 旅行者向け:マイページ
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
    sql = text(
        "SELECT h.hotel_id, h.hotel_name, p.plan_id, p.plan_name, p.price, r.date_of_stay, r.status "
        "FROM t_reservation r "
        "LEFT JOIN m_accommodation_plan p ON r.plan_id = p.plan_id "
        "LEFT JOIN m_hotel h ON p.hotel_id = h.hotel_id "
        "WHERE r.user_id = :user_id "
        "ORDER BY r.date_of_stay ASC"
    )
    df = pd.read_sql(sql, get_engine(), params={"user_id": user_id}, parse_dates=["date_of_stay"])

    return df


############################################################
## 管理者向け:ホテル管理
############################################################
def select_hotels_by_owner(owner_user_id: int) -> pd.DataFrame:
    """
    m_hotelテーブルから、指定オーナーが所有する施設の一覧を取得する

    Args
    -----------------
    - owner_user_id: int,           施設オーナーのユーザID

    Returns
    -----------------
    - df: pd.DataFrame,             取得した施設一覧(該当なしの場合は空)

    """
    sql = text(
        "SELECT hotel_id, hotel_name, address "
        "FROM m_hotel WHERE owner_user_id = :owner_user_id"
    )
    df = pd.read_sql(sql, get_engine(), params={"owner_user_id": owner_user_id})

    return df


def select_hotel(hotel_id: int) -> pd.DataFrame:
    """
    m_hotelテーブルからhotel_idに一致する施設の基本情報を取得する

    Args
    -----------------
    - hotel_id: int,                施設ID

    Returns
    -----------------
    - df: pd.DataFrame,             取得した施設情報(該当なしの場合は空)

    """
    sql = text(
        "SELECT hotel_id, hotel_name, address, introduction "
        "FROM m_hotel WHERE hotel_id = :hotel_id"
    )
    df = pd.read_sql(sql, get_engine(), params={"hotel_id": hotel_id})

    return df


def select_plans_by_hotel(hotel_id: int) -> pd.DataFrame:
    """
    m_accommodation_planテーブルからhotel_idに一致する宿泊プランの一覧を取得する

    Args
    -----------------
    - hotel_id: int,                施設ID

    Returns
    -----------------
    - df: pd.DataFrame,             取得した宿泊プラン一覧(該当なしの場合は空)

    """
    sql = text(
        "SELECT plan_id, plan_name, price, area, room_size, capacity, "
        "       has_breakfast, has_lunch, has_dinner, introduction "
        "FROM m_accommodation_plan WHERE hotel_id = :hotel_id"
    )
    df = pd.read_sql(sql, get_engine(), params={"hotel_id": hotel_id})
    if not df.empty:
        df = df.astype({"has_breakfast": bool, "has_lunch": bool, "has_dinner": bool})

    return df


def insert_hotel(owner_user_id: int, hotel_name: str, address: str, introduction: str) -> int:
    """
    m_hotelテーブルに新しい施設を1件追加する

    Args
    -----------------
    - owner_user_id: int,           施設オーナーのユーザID
    - hotel_name: str,              施設名称
    - address: str,                 住所
    - introduction: str,            紹介文

    Returns
    -----------------
    - hotel_id: int,                採番された施設ID

    """
    sql = text(
        "INSERT INTO m_hotel (owner_user_id, hotel_name, address, introduction) "
        "VALUES (:owner_user_id, :hotel_name, :address, :introduction)"
    )
    with get_engine().begin() as conn:
        result = conn.execute(
            sql,
            {"owner_user_id": owner_user_id, "hotel_name": hotel_name, "address": address, "introduction": introduction},
        )
        return result.lastrowid


def update_hotel(hotel_id: int, hotel_name: str, address: str, introduction: str) -> None:
    """
    m_hotelテーブルの施設の基本情報(名称・住所・紹介文)を更新する

    Args
    -----------------
    - hotel_id: int,                更新対象の施設ID
    - hotel_name: str,              施設名称
    - address: str,                 住所
    - introduction: str,            紹介文

    """
    sql = text(
        "UPDATE m_hotel SET hotel_name = :hotel_name, address = :address, introduction = :introduction "
        "WHERE hotel_id = :hotel_id"
    )
    with get_engine().begin() as conn:
        conn.execute(
            sql,
            {"hotel_id": hotel_id, "hotel_name": hotel_name, "address": address, "introduction": introduction},
        )


def insert_plan(
    hotel_id: int,
    plan_name: str,
    price: int,
    area: str,
    room_size: int,
    capacity: int,
    has_breakfast: bool,
    has_lunch: bool,
    has_dinner: bool,
    introduction: str,
) -> int:
    """
    m_accommodation_planテーブルに新しい宿泊プランを1件追加する

    Args
    -----------------
    - hotel_id: int,                プランを追加する施設ID
    - plan_name: str,               プラン名
    - price: int,                   価格
    - area: str,                    エリアコード
    - room_size: int,               部屋の広さ
    - capacity: int,                1日あたりの最大予約可能室数
    - has_breakfast: bool,          朝食有無
    - has_lunch: bool,              昼食有無
    - has_dinner: bool,             夕食有無
    - introduction: str,            プラン紹介文

    Returns
    -----------------
    - plan_id: int,                 採番された宿泊プランID

    """
    sql = text(
        "INSERT INTO m_accommodation_plan "
        "(hotel_id, plan_name, price, area, room_size, capacity, has_breakfast, has_lunch, has_dinner, introduction) "
        "VALUES (:hotel_id, :plan_name, :price, :area, :room_size, :capacity, :has_breakfast, :has_lunch, :has_dinner, :introduction)"
    )
    with get_engine().begin() as conn:
        result = conn.execute(
            sql,
            {
                "hotel_id": hotel_id,
                "plan_name": plan_name,
                "price": price,
                "area": area,
                "room_size": room_size,
                "capacity": capacity,
                "has_breakfast": has_breakfast,
                "has_lunch": has_lunch,
                "has_dinner": has_dinner,
                "introduction": introduction,
            },
        )
        return result.lastrowid


def update_plan(
    plan_id: int,
    plan_name: str,
    price: int,
    area: str,
    room_size: int,
    capacity: int,
    has_breakfast: bool,
    has_lunch: bool,
    has_dinner: bool,
    introduction: str,
) -> None:
    """
    m_accommodation_planテーブルの既存の宿泊プランを更新する

    Args
    -----------------
    - plan_id: int,                 更新対象の宿泊プランID
    - plan_name: str,               プラン名
    - price: int,                   価格
    - area: str,                    エリアコード
    - room_size: int,               部屋の広さ
    - capacity: int,                1日あたりの最大予約可能室数
    - has_breakfast: bool,          朝食有無
    - has_lunch: bool,              昼食有無
    - has_dinner: bool,             夕食有無
    - introduction: str,            プラン紹介文

    """
    sql = text(
        "UPDATE m_accommodation_plan SET "
        "plan_name = :plan_name, price = :price, area = :area, room_size = :room_size, capacity = :capacity, "
        "has_breakfast = :has_breakfast, has_lunch = :has_lunch, has_dinner = :has_dinner, introduction = :introduction "
        "WHERE plan_id = :plan_id"
    )
    with get_engine().begin() as conn:
        conn.execute(
            sql,
            {
                "plan_id": plan_id,
                "plan_name": plan_name,
                "price": price,
                "area": area,
                "room_size": room_size,
                "capacity": capacity,
                "has_breakfast": has_breakfast,
                "has_lunch": has_lunch,
                "has_dinner": has_dinner,
                "introduction": introduction,
            },
        )


def delete_plan(plan_id: int) -> None:
    """
    m_accommodation_planテーブルから宿泊プランを1件削除する

    予約(t_reservation)が紐づいている場合は外部キー制約によりIntegrityErrorが送出される。

    Args
    -----------------
    - plan_id: int,                 削除対象の宿泊プランID

    """
    sql = text("DELETE FROM m_accommodation_plan WHERE plan_id = :plan_id")
    with get_engine().begin() as conn:
        conn.execute(sql, {"plan_id": plan_id})
