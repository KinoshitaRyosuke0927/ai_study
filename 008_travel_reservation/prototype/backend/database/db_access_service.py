import pandas as pd

from database.db_local_service import db_local


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
    # ホテル名で絞り込み
    df_hotel = df_hotel[df_hotel["hotel_name"].str.contains(key_word, na=False)]
    # 宿泊プランと結合して必要な列のみ抽出
    df = pd.merge(df_hotel, df_plan, on="hotel_id", how="left")[
        ["hotel_id", "hotel_name", "plan_id", "plan_name", "price"]
    ]

    return df
