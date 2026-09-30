"""講座・単元の表示内容を組み立てるモジュール。

受講者ごとの進捗(完了単元・正解済みの演習)を合わせて返す。
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.common.constants import CellType, CourseStatus, Grading, ProblemKind
from app.models import (
    Cell,
    Course,
    CourseCompletion,
    CoursePrerequisite,
    Dataset,
    Problem,
    QuizAttempt,
    Submission,
    Unit,
    UnitProgress,
    User,
)
from app.schemas import (
    CellOut,
    CourseDetailOut,
    CourseSummaryOut,
    DatasetOut,
    ExerciseOut,
    PrerequisiteOut,
    UnitDetailOut,
    UnitNavOut,
    UnitSummaryOut,
)


class NotFoundError(Exception):
    """対象が存在しない、または閲覧権限がない。"""


@dataclass
class ProgressContext:
    """講座の要約を作るための、ユーザの進捗と問題数の集計。"""

    completed_units: set[int]  # 完了済み単元 ID
    completed_courses: set[int]  # 修了済み講座 ID
    exercise_counts: dict[int, int]  # 単元 ID → 演習数
    quiz_counts: dict[int, int]  # 講座 ID → 小テストの問題数
    best_scores: dict[int, int]  # 講座 ID → 小テストの最高得点


def load_progress(session: Session, user: User, course_ids: list[int]) -> ProgressContext:
    """
    講座の要約に必要な進捗と問題数をまとめて取得する

    Args
    -----------------
    - session: Session,                 DB セッション
    - user: User,                       ログイン中ユーザ
    - course_ids: list[int],            対象の講座 ID

    Returns
    -----------------
    - context: ProgressContext,         集計結果

    """
    # 入れ物用意
    exercise_counts: dict[int, int] = {}
    quiz_counts: dict[int, int] = {}
    # 対象講座の問題を種類ごとに数える
    rows = session.execute(
        select(Problem.course_id, Problem.unit_id, Problem.kind).where(Problem.course_id.in_(course_ids))
    )
    for course_id, unit_id, kind in rows:
        # 単元内の演習は単元ごとに数える
        if kind == ProblemKind.EXERCISE and unit_id is not None:
            exercise_counts[unit_id] = exercise_counts.get(unit_id, 0) + 1
        # 小テストの問題は講座ごとに数える
        elif kind == ProblemKind.QUIZ:
            quiz_counts[course_id] = quiz_counts.get(course_id, 0) + 1
    # 小テストの講座ごとの最高得点を取得
    best_scores = dict(
        session.execute(
            select(QuizAttempt.course_id, func.max(QuizAttempt.score))
            .where(QuizAttempt.user_id == user.id)
            .group_by(QuizAttempt.course_id)
        ).all()
    )
    # 集計結果を返却
    return ProgressContext(
        completed_units=_completed_unit_ids(session, user),
        completed_courses=_completed_course_ids(session, user),
        exercise_counts=exercise_counts,
        quiz_counts=quiz_counts,
        best_scores=best_scores,
    )


def visible_course_query(user: User):
    """
    ユーザが閲覧できる講座を絞り込むクエリを返す

    Args
    -----------------
    - user: User,                       ログイン中ユーザ

    Returns
    -----------------
    - query: Select,                    講座の SELECT 文

    """
    # 講座と単元をまとめて読み込むクエリを用意
    query = select(Course).options(selectinload(Course.units))
    # 管理者以外は公開中の講座だけに絞る
    if not user.is_admin:
        query = query.where(Course.status == CourseStatus.PUBLISHED)
    # クエリを返却
    return query


def _completed_unit_ids(session: Session, user: User) -> set[int]:
    """
    ユーザが完了した単元 ID の集合を返す

    Args
    -----------------
    - session: Session,                 DB セッション
    - user: User,                       ログイン中ユーザ

    Returns
    -----------------
    - unit_ids: set[int],               完了済み単元 ID

    """
    # 単元の完了記録からユーザ分を取得して返却
    return set(session.scalars(select(UnitProgress.unit_id).where(UnitProgress.user_id == user.id)))


def _completed_course_ids(session: Session, user: User) -> set[int]:
    """
    ユーザが修了した講座 ID の集合を返す

    Args
    -----------------
    - session: Session,                 DB セッション
    - user: User,                       ログイン中ユーザ

    Returns
    -----------------
    - course_ids: set[int],             修了済み講座 ID

    """
    # 講座の修了記録からユーザ分を取得して返却
    return set(
        session.scalars(select(CourseCompletion.course_id).where(CourseCompletion.user_id == user.id))
    )


def dataset_out(dataset: Dataset) -> DatasetOut:
    """
    データファイルを API 出力形式に変換する

    Args
    -----------------
    - dataset: Dataset,                 データファイル

    Returns
    -----------------
    - out: DatasetOut,                  出力形式

    """
    # ダウンロード URL を付けて返却
    return DatasetOut(id=dataset.id, filename=dataset.filename, url=f"/api/datasets/{dataset.id}")


def summarize(course: Course, ctx: ProgressContext) -> CourseSummaryOut:
    """
    講座一覧用の要約を組み立てる

    Args
    -----------------
    - course: Course,                   講座(units を読み込み済み)
    - ctx: ProgressContext,             進捗と問題数の集計

    Returns
    -----------------
    - summary: CourseSummaryOut,        講座の要約

    """
    # 未完了の最初の単元を「続きから」の対象にする
    next_unit = next((u for u in course.units if u.id not in ctx.completed_units), None)
    completed_count = sum(1 for u in course.units if u.id in ctx.completed_units)
    # 要約を組み立てて返却
    return CourseSummaryOut(
        slug=course.slug,
        title=course.title,
        summary=course.summary,
        level=course.level,
        tags=list(course.tags or []),
        status=course.status,
        unit_count=len(course.units),
        completed_unit_count=completed_count,
        exercise_count=sum(ctx.exercise_counts.get(u.id, 0) for u in course.units),
        estimated_minutes=sum(u.estimated_minutes for u in course.units),
        next_unit_id=next_unit.id if next_unit else None,
        completed=course.id in ctx.completed_courses,
        quiz_question_count=ctx.quiz_counts.get(course.id, 0),
        # 全単元を完了していれば小テストを受けられる
        quiz_unlocked=len(course.units) > 0 and completed_count == len(course.units),
        best_quiz_score=ctx.best_scores.get(course.id),
        published_at=course.published_at,
    )


def list_courses(session: Session, user: User) -> list[CourseSummaryOut]:
    """
    閲覧できる講座の一覧を返す

    Args
    -----------------
    - session: Session,                 DB セッション
    - user: User,                       ログイン中ユーザ

    Returns
    -----------------
    - courses: list[CourseSummaryOut],  講座の要約一覧

    """
    # 閲覧できる講座を取得
    courses = list(session.scalars(visible_course_query(user).order_by(Course.id)))
    # 進捗と問題数を取得
    ctx = load_progress(session, user, [c.id for c in courses])
    # 講座ごとに要約を組み立てて返却
    return [summarize(c, ctx) for c in courses]


def get_course(session: Session, user: User, slug: str) -> CourseDetailOut:
    """
    講座詳細を返す

    Args
    -----------------
    - session: Session,                 DB セッション
    - user: User,                       ログイン中ユーザ
    - slug: str,                        講座の識別名

    Returns
    -----------------
    - detail: CourseDetailOut,          講座詳細

    """
    # 閲覧できる講座から識別名で検索
    course = session.scalar(
        visible_course_query(user)
        .where(Course.slug == slug)
        .options(
            selectinload(Course.datasets),
            selectinload(Course.prerequisites).selectinload(CoursePrerequisite.prerequisite),
            selectinload(Course.author),
        )
    )
    # 見つからない場合はエラー
    if course is None:
        raise NotFoundError(slug)
    # 進捗と問題数を取得
    ctx = load_progress(session, user, [course.id])
    # 講座の要約部分を組み立てる
    summary = summarize(course, ctx)
    # 詳細情報を加えて返却
    return CourseDetailOut(
        **summary.model_dump(),
        outcomes=list(course.outcomes or []),
        libraries=list(course.libraries or []),
        author_name=course.author.display_name if course.author else None,
        updated_at=course.updated_at,
        prerequisites=[
            PrerequisiteOut(
                slug=p.prerequisite.slug,
                title=p.prerequisite.title,
                completed=p.prerequisite_id in ctx.completed_courses,
            )
            for p in course.prerequisites
        ],
        units=[
            UnitSummaryOut(
                id=u.id,
                position=u.position,
                title=u.title,
                summary=u.summary,
                estimated_minutes=u.estimated_minutes,
                exercise_count=ctx.exercise_counts.get(u.id, 0),
                completed=u.id in ctx.completed_units,
            )
            for u in course.units
        ],
        datasets=[dataset_out(d) for d in course.datasets],
    )


def get_unit(session: Session, user: User, unit_id: int) -> UnitDetailOut:
    """
    単元画面の表示内容を返す

    Args
    -----------------
    - session: Session,                 DB セッション
    - user: User,                       ログイン中ユーザ
    - unit_id: int,                     単元 ID

    Returns
    -----------------
    - detail: UnitDetailOut,            単元の表示内容

    """
    # 単元をセル・問題・講座とあわせて取得
    unit = session.scalar(
        select(Unit)
        .where(Unit.id == unit_id)
        .options(
            selectinload(Unit.cells).selectinload(Cell.problem),
            selectinload(Unit.course).selectinload(Course.units),
            selectinload(Unit.course).selectinload(Course.datasets),
        )
    )
    # 存在しない、または非公開講座を管理者以外が開いた場合はエラー
    if unit is None or (not user.is_admin and unit.course.status != CourseStatus.PUBLISHED):
        raise NotFoundError(unit_id)
    # 進捗を取得
    completed_units = _completed_unit_ids(session, user)
    # この単元の演習の ID を集める
    problem_ids = [c.problem_id for c in unit.cells if c.problem_id is not None]
    # 正解済みの演習と、演習ごとの最後の提出を取得
    passed_ids: set[int] = set()
    last_answers: dict[int, str] = {}
    if problem_ids:
        # 提出を古い順に読み、最後の回答で上書きしていく
        for sub in session.scalars(
            select(Submission)
            .where(Submission.user_id == user.id, Submission.problem_id.in_(problem_ids))
            .order_by(Submission.id)
        ):
            last_answers[sub.problem_id] = sub.answer
            if sub.passed:
                passed_ids.add(sub.problem_id)
    # セルを出力形式に変換
    cells: list[CellOut] = []
    for cell in unit.cells:
        exercise = None
        # 演習セルの場合は問題の公開してよい項目だけを渡す
        if cell.cell_type == CellType.EXERCISE and cell.problem is not None:
            p = cell.problem
            exercise = ExerciseOut(
                problem_id=p.id,
                title=p.title,
                prompt=p.prompt,
                hint=p.hint,
                starter_code=p.starter_code,
                grading=p.grading,
                # テストコードはブラウザで実行するため、テスト採点の問題のみ渡す
                test_code=p.test_code if p.grading == Grading.TEST else "",
                passed=p.id in passed_ids,
                last_answer=last_answers.get(p.id),
            )
        cells.append(CellOut(id=cell.id, cell_type=cell.cell_type, source=cell.source, exercise=exercise))
    # 目次(講座内の単元一覧)を組み立てる
    nav = [
        UnitNavOut(id=u.id, position=u.position, title=u.title, completed=u.id in completed_units)
        for u in unit.course.units
    ]
    index = next(i for i, n in enumerate(nav) if n.id == unit.id)
    # 単元の表示内容を返却
    return UnitDetailOut(
        id=unit.id,
        course_slug=unit.course.slug,
        course_title=unit.course.title,
        position=unit.position,
        unit_count=len(nav),
        title=unit.title,
        goals=list(unit.goals or []),
        estimated_minutes=unit.estimated_minutes,
        exercise_count=len(problem_ids),
        completed=unit.id in completed_units,
        cells=cells,
        units=nav,
        prev_unit=nav[index - 1] if index > 0 else None,
        next_unit=nav[index + 1] if index + 1 < len(nav) else None,
        datasets=[dataset_out(d) for d in unit.course.datasets],
    )


def get_dataset(session: Session, user: User, dataset_id: int) -> Dataset:
    """
    データファイルを返す

    Args
    -----------------
    - session: Session,                 DB セッション
    - user: User,                       ログイン中ユーザ
    - dataset_id: int,                  データファイル ID

    Returns
    -----------------
    - dataset: Dataset,                 データファイル

    """
    # データファイルを取得
    dataset = session.get(Dataset, dataset_id)
    # 存在しない、または非公開講座のデータを管理者以外が要求した場合はエラー
    if dataset is None or (
        not user.is_admin and dataset.course.status != CourseStatus.PUBLISHED
    ):
        raise NotFoundError(dataset_id)
    # データファイルを返却
    return dataset
