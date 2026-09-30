"""ホーム画面とマイページの表示内容を組み立てるモジュール。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.constants import CourseLevel, CourseStatus, ProblemKind
from app.models import Course, CourseCompletion, Problem, QuizAttempt, Submission, Unit, UnitProgress, User
from app.schemas import (
    ActivityOut,
    CompletedCourseOut,
    CourseSummaryOut,
    HomeOut,
    MyPageOut,
    QuizHistoryOut,
    RoadmapCourseOut,
)
from app.services.course_service import load_progress, summarize, visible_course_query

# 新着講座として表示する件数
_NEW_COURSE_COUNT = 3
# 最近の学習として表示する件数
_ACTIVITY_COUNT = 8


def _summaries(session: Session, user: User) -> tuple[list[Course], list[CourseSummaryOut]]:
    """
    閲覧できる講座と、その要約を返す

    Args
    -----------------
    - session: Session,                 DB セッション
    - user: User,                       ログイン中ユーザ

    Returns
    -----------------
    - courses: list[Course],            講座
    - summaries: list[CourseSummaryOut], 講座の要約(courses と同じ並び)

    """
    # 閲覧できる講座を取得
    courses = list(session.scalars(visible_course_query(user).order_by(Course.id)))
    # 進捗を取得して要約を作る
    ctx = load_progress(session, user, [c.id for c in courses])
    return courses, [summarize(c, ctx) for c in courses]


def _is_in_progress(s: CourseSummaryOut) -> bool:
    """
    受講中(1単元以上完了、または小テスト受験済みで未修了)かどうか

    Args
    -----------------
    - s: CourseSummaryOut,              講座の要約

    Returns
    -----------------
    - in_progress: bool,                受講中なら True

    """
    # 修了していなくて、何か進めていれば受講中
    return not s.completed and (s.completed_unit_count > 0 or s.best_quiz_score is not None)


def _solved_exercise_count(session: Session, user: User) -> int:
    """
    正解済みの演習の数を返す

    Args
    -----------------
    - session: Session,                 DB セッション
    - user: User,                       ログイン中ユーザ

    Returns
    -----------------
    - count: int,                       正解済みの演習の数(同じ演習は1回と数える)

    """
    # 演習の提出のうち正解したものを、問題ごとに1回だけ数えて返却
    return session.scalar(
        select(func.count(func.distinct(Submission.problem_id)))
        .join(Problem, Problem.id == Submission.problem_id)
        .where(
            Submission.user_id == user.id,
            Submission.passed.is_(True),
            Problem.kind == ProblemKind.EXERCISE,
        )
    ) or 0


def get_home(session: Session, user: User) -> HomeOut:
    """
    ホーム画面の表示内容を返す

    Args
    -----------------
    - session: Session,                 DB セッション
    - user: User,                       ログイン中ユーザ

    Returns
    -----------------
    - home: HomeOut,                    ホーム画面の表示内容

    """
    # 講座の要約を取得
    courses, summaries = _summaries(session, user)
    in_progress = [s for s in summaries if _is_in_progress(s)]
    # 「続きから学習」は最後に単元を完了した受講中の講座にする
    last_unit = session.execute(
        select(Unit.course_id)
        .join(UnitProgress, UnitProgress.unit_id == Unit.id)
        .where(UnitProgress.user_id == user.id)
        .order_by(UnitProgress.completed_at.desc())
    ).first()
    continue_course = None
    if in_progress:
        by_id = {c.id: s for c, s in zip(courses, summaries)}
        candidate = by_id.get(last_unit[0]) if last_unit else None
        continue_course = candidate if candidate in in_progress else in_progress[0]
    # 続きの単元のタイトル
    continue_unit_title = None
    if continue_course and continue_course.next_unit_id:
        unit = session.get(Unit, continue_course.next_unit_id)
        continue_unit_title = unit.title if unit else None
    # 学習ロードマップ(レベルごとの講座と状態)
    roadmap: dict[str, list[RoadmapCourseOut]] = {level: [] for level in CourseLevel.ALL}
    for s in summaries:
        state = "completed" if s.completed else "in_progress" if _is_in_progress(s) else "not_started"
        roadmap[s.level].append(RoadmapCourseOut(slug=s.slug, title=s.title, state=state))
    # 新着講座(公開日の新しい順)
    published = [s for s in summaries if s.status == CourseStatus.PUBLISHED and s.published_at]
    new_courses = sorted(published, key=lambda s: s.published_at, reverse=True)[:_NEW_COURSE_COUNT]
    # 表示内容を返却
    return HomeOut(
        continue_course=continue_course,
        continue_unit_title=continue_unit_title,
        in_progress=in_progress,
        completed_course_count=sum(1 for s in summaries if s.completed),
        in_progress_count=len(in_progress),
        solved_exercise_count=_solved_exercise_count(session, user),
        roadmap=roadmap,
        new_courses=new_courses,
    )


def _activities(session: Session, user: User) -> list[ActivityOut]:
    """
    最近の学習(単元の完了・小テストの受験・講座の修了)を新しい順に返す

    Args
    -----------------
    - session: Session,                 DB セッション
    - user: User,                       ログイン中ユーザ

    Returns
    -----------------
    - activities: list[ActivityOut],    最近の学習

    """
    # 入れ物用意
    items: list[ActivityOut] = []
    # 単元の完了
    for at, unit_title, course_title in session.execute(
        select(UnitProgress.completed_at, Unit.title, Course.title)
        .join(Unit, Unit.id == UnitProgress.unit_id)
        .join(Course, Course.id == Unit.course_id)
        .where(UnitProgress.user_id == user.id)
        .order_by(UnitProgress.completed_at.desc())
        .limit(_ACTIVITY_COUNT)
    ):
        items.append(ActivityOut(at=at, text=f"{course_title} › {unit_title} を完了"))
    # 小テストの受験
    for at, score, total, course_title in session.execute(
        select(QuizAttempt.created_at, QuizAttempt.score, QuizAttempt.total, Course.title)
        .join(Course, Course.id == QuizAttempt.course_id)
        .where(QuizAttempt.user_id == user.id)
        .order_by(QuizAttempt.id.desc())
        .limit(_ACTIVITY_COUNT)
    ):
        items.append(ActivityOut(at=at, text=f"{course_title} › 小テストを受験({score} / {total})"))
    # 講座の修了
    for at, course_title in session.execute(
        select(CourseCompletion.completed_at, Course.title)
        .join(Course, Course.id == CourseCompletion.course_id)
        .where(CourseCompletion.user_id == user.id)
        .order_by(CourseCompletion.completed_at.desc())
        .limit(_ACTIVITY_COUNT)
    ):
        items.append(ActivityOut(at=at, text=f"{course_title} を修了"))
    # 新しい順に並べて件数を絞って返却
    return sorted(items, key=lambda a: a.at, reverse=True)[:_ACTIVITY_COUNT]


def get_my_page(session: Session, user: User) -> MyPageOut:
    """
    マイページの表示内容を返す

    Args
    -----------------
    - session: Session,                 DB セッション
    - user: User,                       ログイン中ユーザ

    Returns
    -----------------
    - page: MyPageOut,                  マイページの表示内容

    """
    # 講座の要約を取得
    _, summaries = _summaries(session, user)
    in_progress = [s for s in summaries if _is_in_progress(s)]
    # 講座ごとの受験回数
    attempt_counts = dict(
        session.execute(
            select(QuizAttempt.course_id, func.count())
            .where(QuizAttempt.user_id == user.id)
            .group_by(QuizAttempt.course_id)
        ).all()
    )
    # 修了した講座
    completed = [
        CompletedCourseOut(
            slug=slug, title=title, completed_at=at, attempt_count=attempt_counts.get(course_id, 0)
        )
        for course_id, slug, title, at in session.execute(
            select(Course.id, Course.slug, Course.title, CourseCompletion.completed_at)
            .join(CourseCompletion, CourseCompletion.course_id == Course.id)
            .where(CourseCompletion.user_id == user.id)
            .order_by(CourseCompletion.completed_at.desc())
        )
    ]
    # 小テストの受験履歴(新しい順)
    history = [
        QuizHistoryOut(course_slug=slug, course_title=title, score=score, total=total, created_at=at)
        for slug, title, score, total, at in session.execute(
            select(Course.slug, Course.title, QuizAttempt.score, QuizAttempt.total, QuizAttempt.created_at)
            .join(Course, Course.id == QuizAttempt.course_id)
            .where(QuizAttempt.user_id == user.id)
            .order_by(QuizAttempt.id.desc())
            .limit(20)
        )
    ]
    # 表示内容を返却
    return MyPageOut(
        completed_course_count=len(completed),
        in_progress_count=len(in_progress),
        solved_exercise_count=_solved_exercise_count(session, user),
        quiz_attempt_count=sum(attempt_counts.values()),
        in_progress=in_progress,
        completed=completed,
        quiz_history=history,
        activities=_activities(session, user),
    )
