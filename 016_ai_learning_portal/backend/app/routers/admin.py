"""管理者向け API(メンバーの受講状況・メンバー管理)。

すべての API で管理者権限を確認する(require_admin)。講座の作成・編集は routers/authoring.py(全ユーザ)。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.infra.db import get_db
from app.models import User
from app.routers.deps import require_admin
from app.schemas import MyPageOut
from app.schemas_admin import ProgressMatrixOut, UserAdminOut, UserCreateIn, UserUpdateIn
from app.services import admin_member_service as members
from app.services.admin_course_service import AdminInputError
from app.services.course_service import NotFoundError

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])

T = TypeVar("T")


def _call(fn: Callable[[], T]) -> T:
    """
    サービスを呼び出し、業務エラーを HTTP エラーに変換する

    Args
    -----------------
    - fn: Callable[[], T],              呼び出す処理

    Returns
    -----------------
    - result: T,                        処理の戻り値

    """
    try:
        return fn()
    # 対象が見つからない
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "対象が見つかりません")
    # 入力内容の誤り(メッセージを画面に表示する)
    except AdminInputError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


# ---------- メンバー ----------
@router.get("/progress", response_model=ProgressMatrixOut)
def progress(db: Session = Depends(get_db)) -> ProgressMatrixOut:
    """
    メンバー × 講座の受講状況を返す

    Args
    -----------------
    - db: Session,                      DB セッション

    Returns
    -----------------
    - matrix: ProgressMatrixOut,        メンバー × 講座の受講状況

    """
    # 受講状況を返却
    return members.progress_matrix(db)


@router.get("/members/{user_id}", response_model=MyPageOut)
def member_detail(user_id: int, db: Session = Depends(get_db)) -> MyPageOut:
    """
    メンバー1人の受講状況を返す

    Args
    -----------------
    - user_id: int,                     対象のユーザ ID
    - db: Session,                      DB セッション

    Returns
    -----------------
    - page: MyPageOut,                  メンバーの受講状況

    """
    # メンバーの受講状況を返却(見つからなければ 404)
    return _call(lambda: members.member_detail(db, user_id))


@router.get("/users", response_model=list[UserAdminOut])
def list_users(db: Session = Depends(get_db)) -> list[UserAdminOut]:
    """
    メンバーの一覧を返す

    Args
    -----------------
    - db: Session,                      DB セッション

    Returns
    -----------------
    - users: list[UserAdminOut],        メンバー一覧

    """
    # メンバー一覧を返却
    return members.list_users(db)


@router.post("/users", response_model=UserAdminOut)
def add_user(req: UserCreateIn, db: Session = Depends(get_db)) -> UserAdminOut:
    """
    メンバーを追加する

    Args
    -----------------
    - req: UserCreateIn,                追加するメンバー
    - db: Session,                      DB セッション

    Returns
    -----------------
    - user: UserAdminOut,               追加したメンバー

    """
    # メンバーを追加して返却
    return _call(lambda: members.add_user(db, req))


@router.put("/users/{user_id}", response_model=UserAdminOut)
def update_user(
    user_id: int, req: UserUpdateIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> UserAdminOut:
    """
    メンバーを更新する

    Args
    -----------------
    - user_id: int,                     対象のユーザ ID
    - req: UserUpdateIn,                更新内容
    - admin: User,                      ログイン中の管理者
    - db: Session,                      DB セッション

    Returns
    -----------------
    - user: UserAdminOut,               更新後のメンバー

    """
    # メンバーを更新して返却
    return _call(lambda: members.update_user(db, admin, user_id, req))


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> None:
    """
    メンバーを削除する(受講記録も削除される)

    Args
    -----------------
    - user_id: int,                     対象のユーザ ID
    - admin: User,                      ログイン中の管理者
    - db: Session,                      DB セッション

    """
    # メンバーを削除
    _call(lambda: members.delete_user(db, admin, user_id))
