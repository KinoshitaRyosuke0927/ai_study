"""ルーター共通の依存性(ログイン中ユーザの取得など)。"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.infra.db import get_db
from app.models import User

# セッション Cookie に保存するユーザ ID のキー
SESSION_USER_KEY = "uid"


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """
    ログイン中のユーザを返す(未ログインなら 401)

    Args
    -----------------
    - request: Request,                 リクエスト(セッション Cookie を含む)
    - db: Session,                      DB セッション

    Returns
    -----------------
    - user: User,                       ログイン中のユーザ

    """
    # セッションからユーザ ID を取り出す
    user_id = request.session.get(SESSION_USER_KEY)
    # ユーザ ID が無い場合は未ログイン
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "ログインしてください")
    # ユーザを取得し、削除・無効化されていれば未ログイン扱い
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        request.session.clear()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "ログインしてください")
    # ユーザを返却
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """
    管理者であることを確認する(管理者以外は 403)

    Args
    -----------------
    - user: User,                       ログイン中のユーザ

    Returns
    -----------------
    - user: User,                       管理者ユーザ

    """
    # 管理者でなければ拒否
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "管理者のみ操作できます")
    # 管理者ユーザを返却
    return user
