from unittest.mock import patch

import pandas as pd

from models import LoginResponse
from services import login_service

# テスト用のuserテーブルデータ
user_df = pd.DataFrame(
    data={
        "user_id": 1,
        "user_name": "木下 凌介",
        "mail_address": "r-kinoshita@jbd-test.co.jp",
        "password": "$2b$12$vQOGHy67Z2TACpln9cl2D.zdeRVL4RfLp4AN183ETkn/FRSN7k4ii", # kinoshita@0927
    },
    index=[0],
).astype({"user_id": int, "user_name": str, "mail_address": str, "password": bytes})


# 正常系
# 正常にログインできること
@patch("database.db_access_service.select_user", return_value=user_df)
def test_login_OK_01(mock):
    ## テストデータ用意
    # メールアドレス
    mail_address = "r-kinoshita@jbd-test.co.jp"
    # パスワード
    password = "kinoshita@0927"

    ## 期待値
    expected_res = LoginResponse(status=200, messages=[], user_id=1, user_name="木下 凌介")

    ## テスト処理
    result_res = login_service.login(mail_address, password)

    assert expected_res == result_res


# 異常系
# メールアドレスが存在しない場合にエラーが返ること
@patch("database.db_access_service.select_user", return_value=pd.DataFrame())
@patch("database.db_access_service.select_message", return_value={"message_id": "msg-E-0001", "message_type": "error", "message": "メールアドレスまたはパスワードが正しくありません。"})
def test_login_NG_01(mock_message, mock_user):
    ## テストデータ用意
    # メールアドレス
    mail_address = "r-kinoshitaaaaaaaaaa@jbd-test.co.jp"
    # パスワード
    password = "kinoshita@0927"

    ## 期待値
    error_dict = {"message_id": "msg-E-0001", "message_type": "error", "message": "メールアドレスまたはパスワードが正しくありません。"}
    expected_res = LoginResponse(status=200, messages=[error_dict])

    ## テスト処理
    result_res = login_service.login(mail_address, password)

    assert expected_res == result_res


# 異常系
# パスワードが正しくない場合にエラーが返ること
@patch("database.db_access_service.select_user", return_value=user_df)
@patch("database.db_access_service.select_message", return_value={"message_id": "msg-E-0001", "message_type": "error", "message": "メールアドレスまたはパスワードが正しくありません。"})
def test_login_NG_02(mock_message, mock_user):
    ## テストデータ用意
    # メールアドレス
    mail_address = "r-kinoshita@jbd-test.co.jp"
    # パスワード
    password = "password"

    ## 期待値
    error_dict = {"message_id": "msg-E-0001", "message_type": "error", "message": "メールアドレスまたはパスワードが正しくありません。"}
    expected_res = LoginResponse(status=200, messages=[error_dict])

    ## テスト処理
    result_res = login_service.login(mail_address, password)

    assert expected_res == result_res
