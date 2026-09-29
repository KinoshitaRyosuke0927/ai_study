"""ログイン名・パスワードによる認証を扱うモジュール。

パスワードは標準ライブラリの scrypt でハッシュ化して保存する。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User

# scrypt のパラメータ(メモリ使用量 約16MB)
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


def hash_password(password: str) -> str:
    """
    パスワードをハッシュ化する

    Args
    -----------------
    - password: str,                    平文のパスワード

    Returns
    -----------------
    - hashed: str,                      "scrypt$n$r$p$salt$hash" 形式のハッシュ

    """
    # ユーザごとに異なるソルトを生成
    salt = secrets.token_bytes(16)
    # scrypt でハッシュ値を計算
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P
    )
    # パラメータとソルトを含めて文字列化して返却
    return "$".join(
        [
            "scrypt",
            str(_SCRYPT_N),
            str(_SCRYPT_R),
            str(_SCRYPT_P),
            base64.b64encode(salt).decode(),
            base64.b64encode(digest).decode(),
        ]
    )


def verify_password(password: str, hashed: str) -> bool:
    """
    パスワードがハッシュと一致するか検証する

    Args
    -----------------
    - password: str,                    入力された平文のパスワード
    - hashed: str,                      保存済みのハッシュ

    Returns
    -----------------
    - matched: bool,                    一致すれば True

    """
    # 保存形式を分解(形式が不正なら不一致扱い)
    try:
        algo, n, r, p, salt_b64, digest_b64 = hashed.split("$")
    except ValueError:
        return False
    # 未知のアルゴリズムは不一致扱い
    if algo != "scrypt":
        return False
    # 保存時と同じパラメータで入力値をハッシュ化
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=base64.b64decode(salt_b64),
        n=int(n),
        r=int(r),
        p=int(p),
    )
    # タイミング攻撃を避けるため定数時間で比較して返却
    return hmac.compare_digest(digest, base64.b64decode(digest_b64))


def authenticate(session: Session, login_name: str, password: str) -> User | None:
    """
    ログイン名とパスワードでユーザを認証する

    Args
    -----------------
    - session: Session,                 DB セッション
    - login_name: str,                  ログイン名
    - password: str,                    パスワード

    Returns
    -----------------
    - user: User | None,                認証できたユーザ(失敗時は None)

    """
    # ログイン名でユーザを検索
    user = session.scalar(select(User).where(User.login_name == login_name.strip()))
    # ユーザが存在しない、または無効化されている場合は失敗
    if user is None or not user.is_active:
        return None
    # パスワードが一致しない場合は失敗
    if not verify_password(password, user.password_hash):
        return None
    # 認証できたユーザを返却
    return user


def create_user(
    session: Session, login_name: str, display_name: str, password: str, is_admin: bool
) -> User:
    """
    ユーザを作成する

    Args
    -----------------
    - session: Session,                 DB セッション
    - login_name: str,                  ログイン名
    - display_name: str,                表示名
    - password: str,                    初期パスワード
    - is_admin: bool,                   管理者なら True

    Returns
    -----------------
    - user: User,                       作成したユーザ

    """
    # 同じログイン名が既に存在する場合はエラー
    if session.scalar(select(User).where(User.login_name == login_name)) is not None:
        raise ValueError(f"ログイン名 '{login_name}' は既に使われています")
    # ユーザを生成して登録
    user = User(
        login_name=login_name,
        display_name=display_name,
        password_hash=hash_password(password),
        is_admin=is_admin,
    )
    session.add(user)
    session.flush()
    # 作成したユーザを返却
    return user
