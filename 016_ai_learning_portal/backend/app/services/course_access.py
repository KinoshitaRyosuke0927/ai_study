"""講座ごとの閲覧・編集の権限を判定するモジュール。

- 編集(講座の作成・編集・検証・公開): 作成者本人と管理者だけ
- 閲覧(受講)の判定は course_service 側(公開中はだれでも、下書きは作成者本人と管理者だけ)
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AIJob, Course, CourseImage, Dataset, Problem, Unit, User
from app.services.course_service import NotFoundError


def can_edit(user: User, course: Course) -> bool:
    """
    講座を編集できるかを返す

    Args
    -----------------
    - user: User,                       ログイン中ユーザ
    - course: Course,                   講座

    Returns
    -----------------
    - allowed: bool,                    作成者本人または管理者なら True

    """
    # 管理者はすべて、一般ユーザは自分が作った講座だけ
    return user.is_admin or (course.author_id is not None and course.author_id == user.id)


def editable_course(session: Session, user: User, course_id: int | None) -> Course:
    """
    編集できる講座を返す(存在しない・権限が無い場合は、どちらも「見つからない」として扱う)

    Args
    -----------------
    - session: Session,                 DB セッション
    - user: User,                       ログイン中ユーザ
    - course_id: int | None,            講座 ID

    Returns
    -----------------
    - course: Course,                   講座

    """
    # 講座を取得して権限を確認(他人の講座の有無も分からないよう 404 にそろえる)
    course = session.get(Course, course_id) if course_id is not None else None
    if course is None or not can_edit(user, course):
        raise NotFoundError(course_id)
    return course


def course_id_of(session: Session, kind: str, object_id: int) -> int | None:
    """
    単元・問題・データファイル・画像・生成ジョブから、属する講座の ID を返す

    Args
    -----------------
    - session: Session,                 DB セッション
    - kind: str,                        対象の種類(unit / problem / dataset / image / job)
    - object_id: int,                   対象の ID

    Returns
    -----------------
    - course_id: int | None,            講座 ID(対象が無ければ None)

    """
    # 種類ごとに講座 ID の列を選ぶ
    column = {
        "unit": (Unit.id, Unit.course_id),
        "problem": (Problem.id, Problem.course_id),
        "dataset": (Dataset.id, Dataset.course_id),
        "image": (CourseImage.id, CourseImage.course_id),
        "job": (AIJob.id, AIJob.course_id),
    }[kind]
    # 講座 ID を取得して返却
    return session.scalar(select(column[1]).where(column[0] == object_id))
