import bcrypt

from common.error_messages import ErrorMessages
from models import LoginResponse
from database import db_access_service


def login(mail_address: str, password: str) -> LoginResponse:
    """
    メールアドレスとパスワードでログインを行う

    Args
    -----------------
    - mail_address: str,        メールアドレス
    - password: str,            パスワード

    Returns
    -----------------
    - response: LoginResponse,    レスポンス

    """
    # メールアドレスからユーザ情報を取得
    df = db_access_service.select_user(mail_address)
    # 対象のユーザ情報が存在しない場合
    if df.empty:
        # レスポンス返却
        return LoginResponse(messages=[ErrorMessages.E_0001])
    # 対象のユーザ情報が存在する場合
    else:
        # パスワードが正しいか確認
        if bcrypt.checkpw(password.encode("utf-8"), df["password"].values[0]):
            # レスポンス返却
            return LoginResponse(messages=[], user_id=df["user_id"].values[0], user_name=df["user_name"].values[0])
        # パスワードが誤っている場合
        else:
            # レスポンス返却
            return LoginResponse(messages=[ErrorMessages.E_0001])
