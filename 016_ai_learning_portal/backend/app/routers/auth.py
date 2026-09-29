"""認証 API(ログイン・ログアウト・ログイン中ユーザ)。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.infra.db import get_db
from app.models import User
from app.routers.deps import SESSION_USER_KEY, get_current_user
from app.schemas import LoginRequest, UserOut
from app.services.auth_service import authenticate

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_out(user: User) -> UserOut:
    """
    ユーザを API 出力形式に変換する

    Args
    -----------------
    - user: User,                       ユーザ

    Returns
    -----------------
    - out: UserOut,                     出力形式

    """
    # 公開してよい項目だけを返却
    return UserOut(
        id=user.id, login_name=user.login_name, display_name=user.display_name, is_admin=user.is_admin
    )


@router.post("/login", response_model=UserOut)
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)) -> UserOut:
    """
    ログインする

    Args
    -----------------
    - req: LoginRequest,                ログイン名とパスワード
    - request: Request,                 リクエスト(セッションを書き込む)
    - db: Session,                      DB セッション

    Returns
    -----------------
    - user: UserOut,                    ログインしたユーザ

    """
    # ログイン名とパスワードを照合
    user = authenticate(db, req.login_name, req.password)
    # 失敗時はどちらが誤っているかを区別せずに返す
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "ログイン名またはパスワードが正しくありません")
    # セッションを作り直してユーザ ID を保存
    request.session.clear()
    request.session[SESSION_USER_KEY] = user.id
    # ユーザ情報を返却
    return _user_out(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request) -> None:
    """
    ログアウトする

    Args
    -----------------
    - request: Request,                 リクエスト(セッションを破棄する)

    """
    # セッションを破棄
    request.session.clear()


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    """
    ログイン中のユーザを返す

    Args
    -----------------
    - user: User,                       ログイン中のユーザ

    Returns
    -----------------
    - user: UserOut,                    ユーザ情報

    """
    # ユーザ情報を返却
    return _user_out(user)
