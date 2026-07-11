from unittest.mock import patch

import pandas as pd

from models import LoginResponse
from services import login_service

# テスト用のuserテーブルデータ
user_df = pd.DataFrame(
    data={
        "user_id": 1,
        "user_name": "さくらみこ",
        "mail_address": "sakuramiko3535@hol.co.jp",
        "password": "$2b$12$hkm9glUpV5NPIVbgMajYMO5Qn2zEXlZQdOoSiJ7xPqrW5CwrPM5SG", # mikomiko
        "owner_flag": True,
    },
    index=[0],
).astype({"user_id": int, "user_name": str, "mail_address": str, "password": bytes, "owner_flag": bool})


# 正常系
# 正常にログインできること
@patch("database.db_access_service.select_user", return_value=user_df)
def test_login_OK_01(mock):
    ## テストデータ用意
    # メールアドレス
    mail_address = "sakuramiko3535@hol.co.jp"
    # パスワード
    password = "mikomiko"

    ## 期待値
    expected_res = LoginResponse(messages=[], user_id=1, user_name="さくらみこ")

    ## テスト処理
    result_res = login_service.login(mail_address, password)

    assert expected_res == result_res


# 異常系
# メールアドレスが存在しない場合にエラーが返ること
@patch("database.db_access_service.select_user", return_value=pd.DataFrame())
def test_login_NG_01(mock):
    ## テストデータ用意
    # メールアドレス
    mail_address = "suisei_h@hol.co.jp"
    # パスワード
    password = "suisui"

    ## 期待値
    error_dict = {"message_id": "msg-E-0001", "message_type": "error", "message": "ログイン情報が不正です。"}
    expected_res = LoginResponse(messages=[error_dict])

    ## テスト処理
    result_res = login_service.login(mail_address, password)

    assert expected_res == result_res


# 異常系
# パスワードが正しくない場合にエラーが返ること
@patch("database.db_access_service.select_user", return_value=user_df)
def test_login_NG_02(mock):
    ## テストデータ用意
    # メールアドレス
    mail_address = "sakuramiko3535@hol.co.jp"
    # パスワード
    password = "suisui"

    ## 期待値
    error_dict = {"message_id": "msg-E-0001", "message_type": "error", "message": "ログイン情報が不正です。"}
    expected_res = LoginResponse(messages=[error_dict])

    ## テスト処理
    result_res = login_service.login(mail_address, password)

    assert expected_res == result_res
