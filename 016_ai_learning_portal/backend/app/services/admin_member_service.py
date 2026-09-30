"""管理者向けのメンバー管理(受講状況の一覧・メンバーの追加/更新/削除)を扱うモジュール。

受講状況は学習支援と講座改善のための情報で、人事評価には使わない。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.common.constants import CourseStatus
from app.models import Course, CourseCompletion, QuizAttempt, Submission, UnitProgress, User
from app.schemas import MyPageOut
from app.schemas_admin import (
    MemberProgressOut,
    ProgressCellOut,
    ProgressMatrixOut,
    UserAdminOut,
    UserCreateIn,
    UserUpdateIn,
)
from app.services import dashboard_service
from app.services.admin_course_service import AdminInputError
from app.services.auth_service import create_user, hash_password
from app.services.course_service import NotFoundError


def progress_matrix(session: Session) -> ProgressMatrixOut:
    """
    メンバー × 公開中の講座の受講状況を返す

    Args
    -----------------
    - session: Session,                 DB セッション

    Returns
    -----------------
    - matrix: ProgressMatrixOut,        受講状況

    """
    # 公開中の講座と単元を取得
    courses = list(
        session.scalars(
            select(Course)
            .where(Course.status == CourseStatus.PUBLISHED)
            .options(selectinload(Course.units))
            .order_by(Course.id)
        )
    )
    unit_course = {u.id: c.id for c in courses for u in c.units}
    # 有効なメンバーを取得
    users = list(session.scalars(select(User).where(User.is_active.is_(True)).order_by(User.id)))
    # メンバー × 講座ごとの完了単元数
    done: dict[tuple[int, int], int] = {}
    for user_id, unit_id in session.execute(select(UnitProgress.user_id, UnitProgress.unit_id)):
        course_id = unit_course.get(unit_id)
        if course_id is not None:
            done[(user_id, course_id)] = done.get((user_id, course_id), 0) + 1
    # 修了と、小テストの受験有無
    completed = {tuple(r) for r in session.execute(select(CourseCompletion.user_id, CourseCompletion.course_id))}
    attempted = {tuple(r) for r in session.execute(select(QuizAttempt.user_id, QuizAttempt.course_id).distinct())}
    # メンバーごとの最終学習日時(提出・単元完了の新しい方)
    last_sub = dict(session.execute(select(Submission.user_id, func.max(Submission.created_at)).group_by(Submission.user_id)).all())
    last_unit = dict(
        session.execute(select(UnitProgress.user_id, func.max(UnitProgress.completed_at)).group_by(UnitProgress.user_id)).all()
    )
    # 行を組み立てる
    members: list[MemberProgressOut] = []
    for u in users:
        cells = []
        for c in courses:
            n = done.get((u.id, c.id), 0)
            if (u.id, c.id) in completed:
                state = "completed"
            elif n > 0 or (u.id, c.id) in attempted:
                state = "in_progress"
            else:
                state = "none"
            cells.append(ProgressCellOut(course_id=c.id, state=state, done=n, total=len(c.units)))
        times = [t for t in (last_sub.get(u.id), last_unit.get(u.id)) if t is not None]
        members.append(
            MemberProgressOut(
                id=u.id,
                login_name=u.login_name,
                display_name=u.display_name,
                is_admin=u.is_admin,
                last_activity=max(times) if times else None,
                cells=cells,
            )
        )
    # 受講状況を返却
    return ProgressMatrixOut(
        courses=[{"id": c.id, "slug": c.slug, "title": c.title, "unit_count": len(c.units)} for c in courses],
        members=members,
    )


def member_detail(session: Session, user_id: int) -> MyPageOut:
    """
    メンバー1人の受講状況(マイページと同じ内容)を返す

    Args
    -----------------
    - session: Session,                 DB セッション
    - user_id: int,                     メンバーのユーザ ID

    Returns
    -----------------
    - page: MyPageOut,                  受講状況
    """
    # メンバーを取得(見つからなければエラー)
    user = session.get(User, user_id)
    if user is None:
        raise NotFoundError(user_id)
    # 受講者向けの画面と同じ集計を返す(公開中の講座のみが対象になるよう受講者として扱う)
    viewer = User(id=user.id, login_name=user.login_name, display_name=user.display_name, is_admin=False)
    return dashboard_service.get_my_page(session, viewer)


def _user_out(u: User) -> UserAdminOut:
    """
    ユーザを出力形式に変換する

    Args
    -----------------
    - u: User,                          ユーザ

    Returns
    -----------------
    - out: UserAdminOut,                出力形式(パスワードは含めない)

    """
    # 公開してよい項目だけを返却
    return UserAdminOut(
        id=u.id,
        login_name=u.login_name,
        display_name=u.display_name,
        is_admin=u.is_admin,
        is_active=u.is_active,
        created_at=u.created_at,
    )


def list_users(session: Session) -> list[UserAdminOut]:
    """
    メンバーの一覧を返す

    Args
    -----------------
    - session: Session,                 DB セッション

    Returns
    -----------------
    - users: list[UserAdminOut],        メンバー一覧

    """
    # 全ユーザを返却
    return [_user_out(u) for u in session.scalars(select(User).order_by(User.id))]


def add_user(session: Session, data: UserCreateIn) -> UserAdminOut:
    """
    メンバーを追加する

    Args
    -----------------
    - session: Session,                 DB セッション
    - data: UserCreateIn,               追加するメンバー

    Returns
    -----------------
    - user: UserAdminOut,               追加したメンバー

    """
    # ログイン名の重複はエラー
    try:
        user = create_user(session, data.login_name, data.display_name.strip(), data.password, data.is_admin)
    except ValueError as e:
        raise AdminInputError(str(e))
    return _user_out(user)


def update_user(session: Session, current: User, user_id: int, data: UserUpdateIn) -> UserAdminOut:
    """
    メンバーを更新する(自分自身の管理者権限・有効状態は外せない)

    Args
    -----------------
    - session: Session,                 DB セッション
    - current: User,                    操作している管理者
    - user_id: int,                     対象のユーザ ID
    - data: UserUpdateIn,               更新内容

    Returns
    -----------------
    - user: UserAdminOut,               更新後のメンバー

    """
    # 対象を取得
    user = session.get(User, user_id)
    if user is None:
        raise NotFoundError(user_id)
    # 自分で自分を締め出さないようにする
    if user.id == current.id and (not data.is_admin or not data.is_active):
        raise AdminInputError("自分自身の管理者権限・有効状態は変更できません")
    # 反映(パスワードは指定があるときだけ変更)
    user.display_name = data.display_name.strip()
    user.is_admin = data.is_admin
    user.is_active = data.is_active
    if data.password:
        user.password_hash = hash_password(data.password)
    session.flush()
    return _user_out(user)


def delete_user(session: Session, current: User, user_id: int) -> None:
    """
    メンバーを削除する(受講記録も削除される。自分自身は削除できない)

    Args
    -----------------
    - session: Session,                 DB セッション
    - current: User,                    操作している管理者
    - user_id: int,                     対象のユーザ ID

    """
    # 対象を取得
    user = session.get(User, user_id)
    if user is None:
        raise NotFoundError(user_id)
    if user.id == current.id:
        raise AdminInputError("自分自身は削除できません")
    # 作成した講座の作成者欄を外してから削除
    for course in session.scalars(select(Course).where(Course.author_id == user.id)):
        course.author_id = None
    session.delete(user)
    session.flush()
