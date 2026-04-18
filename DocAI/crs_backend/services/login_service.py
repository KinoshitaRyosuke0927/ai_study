import bcrypt

from database import db_access_service
from models import LoginResponse


def login(mail_address: str, password: str) -> LoginResponse:
    """
    メールアドレスとパスワードでログインを行う
    参考 : パスワードハッシュ化について
    https://zenn.dev/417/scraps/43f1ffbe90132c

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
        # 該当のエラーメッセージを取得
        message_dict = db_access_service.select_message("msg-E-0001")
        # レスポンス返却
        return LoginResponse(status=200, messages=[message_dict])
    # 対象のユーザ情報が存在する場合
    else:
        # パスワードが正しいか確認
        if bcrypt.checkpw(password.encode("utf-8"), df["password"].values[0]):
            # レスポンス返却
            return LoginResponse(
                status=200,
                messages=[],
                user_id=df["user_id"].values[0],
                user_name=df["user_name"].values[0]
            )
        # パスワードが誤っている場合
        else:
            # 該当のエラーメッセージを取得
            message_dict = db_access_service.select_message("msg-E-0001")
            # レスポンス返却
            return LoginResponse(status=200, messages=[message_dict])
