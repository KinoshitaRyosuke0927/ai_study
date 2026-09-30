"""管理者向けの講座編集(講座情報・単元・セル・演習・小テスト・検証・公開)を扱うモジュール。

検証のルール:
- コード問題は、作成者の解答をブラウザ(Pyodide)で実行した出力で検証する。
  AI の模範解答がある場合は、その出力と作成者の出力が一致すれば検証済み(一致しなければ不一致)。
  AI の模範解答が無い場合は、作成者の出力を想定出力として検証済みにする。
- 選択式・数値入力は、正解が正しく設定されていれば保存時に検証済みにする。
- 採点に関わる項目を変えた問題は、内容バージョンを上げて未検証に戻す(その問題だけ再検証)。
"""

from __future__ import annotations

import io
import math
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.common.constants import (
    AnswerFormat,
    CellType,
    CourseLevel,
    CourseStatus,
    Grading,
    ProblemKind,
    VerifyStatus,
)
from app.models import (
    Cell,
    Course,
    CourseCompletion,
    CoursePrerequisite,
    Dataset,
    Problem,
    Unit,
    UnitProgress,
    User,
)
from app.schemas_admin import (
    AdminCourseRowOut,
    CellAdminOut,
    CheckItemOut,
    CheckOut,
    CourseEditorOut,
    CourseInfoIn,
    ProblemIn,
    ProblemOut,
    PublishCheckOut,
    QuizContentIn,
    UnitAdminOut,
    UnitContentIn,
    UnitInfoIn,
    VerifyIn,
    VerifyOut,
)
from app.services.course_service import NotFoundError, dataset_out
from app.services.grading import outputs_match
from app.services.notebook_import import NotebookFormatError, add_parsed_unit, import_course, parse_notebook

# 採点に関わる項目(変更したら再検証が必要)
_GRADED_FIELDS = (
    "prompt",
    "starter_code",
    "grading",
    "test_code",
    "choices",
    "correct_answer",
    "tolerance",
    "author_answer",
    "ai_model_answer",
)
# データファイルの上限サイズ
MAX_DATASET_BYTES = 20 * 1024 * 1024
# 取り込む zip / .ipynb の上限サイズ
MAX_IMPORT_BYTES = 50 * 1024 * 1024


class AdminInputError(Exception):
    """入力内容に誤りがある(画面にそのまま表示するメッセージを持つ)。"""


# ---------- 取得・変換 ----------
def _get_course(session: Session, course_id: int) -> Course:
    """
    講座を単元とあわせて取得する

    Args
    -----------------
    - session: Session,                 DB セッション
    - course_id: int,                   講座 ID

    Returns
    -----------------
    - course: Course,                   講座

    """
    # 講座を取得(見つからなければエラー)
    course = session.scalar(
        select(Course).where(Course.id == course_id).options(selectinload(Course.units))
    )
    if course is None:
        raise NotFoundError(course_id)
    return course


def _get_unit(session: Session, unit_id: int) -> Unit:
    """
    単元をセル・問題とあわせて取得する

    Args
    -----------------
    - session: Session,                 DB セッション
    - unit_id: int,                     単元 ID

    Returns
    -----------------
    - unit: Unit,                       単元

    """
    # 単元を取得(見つからなければエラー)
    unit = session.scalar(
        select(Unit).where(Unit.id == unit_id).options(selectinload(Unit.cells).selectinload(Cell.problem))
    )
    if unit is None:
        raise NotFoundError(unit_id)
    return unit


def _problem_out(p: Problem) -> ProblemOut:
    """
    問題を管理者向けの出力形式に変換する

    Args
    -----------------
    - p: Problem,                       問題

    Returns
    -----------------
    - out: ProblemOut,                  出力形式(すべての項目)

    """
    # すべての項目を移して返却
    return ProblemOut(
        id=p.id,
        answer_format=p.answer_format,
        title=p.title,
        prompt=p.prompt,
        hint=p.hint,
        starter_code=p.starter_code,
        grading=p.grading,
        test_code=p.test_code,
        choices=list(p.choices or []),
        correct_answer=p.correct_answer,
        tolerance=p.tolerance,
        explanation=p.explanation,
        related_unit_id=p.related_unit_id,
        ai_model_answer=p.ai_model_answer,
        author_answer=p.author_answer,
        expected_output=p.expected_output,
        verify_status=p.verify_status,
        content_version=p.content_version,
    )


def _unit_out(unit: Unit) -> UnitAdminOut:
    """
    単元を管理者向けの出力形式に変換する

    Args
    -----------------
    - unit: Unit,                       単元(セルと問題を読み込み済み)

    Returns
    -----------------
    - out: UnitAdminOut,                出力形式

    """
    # セルごとに変換して返却
    return UnitAdminOut(
        id=unit.id,
        position=unit.position,
        title=unit.title,
        summary=unit.summary,
        goals=list(unit.goals or []),
        estimated_minutes=unit.estimated_minutes,
        cells=[
            CellAdminOut(
                id=c.id,
                cell_type=c.cell_type,
                source=c.source,
                ai_generated=c.ai_generated,
                problem=_problem_out(c.problem) if c.problem else None,
            )
            for c in unit.cells
        ],
    )


# ---------- 講座 ----------
def list_courses(session: Session) -> list[AdminCourseRowOut]:
    """
    講座管理の一覧(下書きを含むすべての講座)を返す

    Args
    -----------------
    - session: Session,                 DB セッション

    Returns
    -----------------
    - rows: list[AdminCourseRowOut],    講座の一覧

    """
    # 講座を作成者・単元とあわせて取得
    courses = list(
        session.scalars(
            select(Course).options(selectinload(Course.units), selectinload(Course.author)).order_by(Course.id)
        )
    )
    # 講座ごとの問題数・検証済み数
    problem_counts: dict[int, tuple[int, int]] = {}
    for course_id, status, count in session.execute(
        select(Problem.course_id, Problem.verify_status, func.count()).group_by(Problem.course_id, Problem.verify_status)
    ):
        total, verified = problem_counts.get(course_id, (0, 0))
        problem_counts[course_id] = (total + count, verified + (count if status == VerifyStatus.VERIFIED else 0))
    # 講座ごとの受講者数(1単元以上完了した人数)
    learners = dict(
        session.execute(
            select(Unit.course_id, func.count(func.distinct(UnitProgress.user_id)))
            .join(UnitProgress, UnitProgress.unit_id == Unit.id)
            .group_by(Unit.course_id)
        ).all()
    )
    # 講座ごとの修了者数
    completers = dict(
        session.execute(
            select(CourseCompletion.course_id, func.count()).group_by(CourseCompletion.course_id)
        ).all()
    )
    # 一覧を組み立てて返却
    return [
        AdminCourseRowOut(
            id=c.id,
            slug=c.slug,
            title=c.title,
            level=c.level,
            status=c.status,
            unit_count=len(c.units),
            problem_count=problem_counts.get(c.id, (0, 0))[0],
            verified_count=problem_counts.get(c.id, (0, 0))[1],
            learner_count=learners.get(c.id, 0),
            completer_count=completers.get(c.id, 0),
            author_name=c.author.display_name if c.author else None,
            updated_at=c.updated_at,
        )
        for c in courses
    ]


def _apply_info(session: Session, course: Course, info: CourseInfoIn) -> None:
    """
    講座情報を講座に反映する(識別名の重複・レベル・前提講座を確認する)

    Args
    -----------------
    - session: Session,                 DB セッション
    - course: Course,                   講座
    - info: CourseInfoIn,               講座情報

    """
    # レベルの確認
    if info.level not in CourseLevel.ALL:
        raise AdminInputError("レベルの指定が正しくありません")
    # 識別名の重複確認
    other = session.scalar(select(Course).where(Course.slug == info.slug))
    if other is not None and other.id != course.id:
        raise AdminInputError(f"識別名 '{info.slug}' は別の講座で使われています")
    # 項目を反映(空行は取り除く)
    course.slug = info.slug
    course.title = info.title.strip()
    course.summary = info.summary.strip()
    course.level = info.level
    course.tags = [t.strip() for t in info.tags if t.strip()]
    course.outcomes = [t.strip() for t in info.outcomes if t.strip()]
    course.libraries = [t.strip() for t in info.libraries if t.strip()]
    session.flush()
    # 前提講座を置き換える(自分自身は指定できない)
    for pre in list(course.prerequisites):
        session.delete(pre)
    session.flush()
    for pre_id in dict.fromkeys(info.prerequisite_ids):
        if pre_id == course.id or session.get(Course, pre_id) is None:
            raise AdminInputError("前提講座の指定が正しくありません")
        session.add(CoursePrerequisite(course_id=course.id, prerequisite_id=pre_id))
    session.flush()


def create_course(session: Session, author: User, info: CourseInfoIn) -> Course:
    """
    下書きの講座を作成する(単元を1つ用意する)

    Args
    -----------------
    - session: Session,                 DB セッション
    - author: User,                     作成者
    - info: CourseInfoIn,               講座情報

    Returns
    -----------------
    - course: Course,                   作成した講座

    """
    # 識別名の重複を先に確認(登録時の一意制約エラーを避ける)
    if session.scalar(select(Course).where(Course.slug == info.slug)) is not None:
        raise AdminInputError(f"識別名 '{info.slug}' は別の講座で使われています")
    # 下書きとして講座を作成
    course = Course(slug=info.slug, title=info.title, status=CourseStatus.DRAFT, author_id=author.id)
    session.add(course)
    session.flush()
    _apply_info(session, course, info)
    # 最初の単元を用意
    session.add(Unit(course_id=course.id, position=1, title="単元1", goals=[]))
    session.flush()
    # 作成した講座を返却
    return course


def update_info(session: Session, course_id: int, info: CourseInfoIn) -> None:
    """
    講座情報を更新する

    Args
    -----------------
    - session: Session,                 DB セッション
    - course_id: int,                   講座 ID
    - info: CourseInfoIn,               講座情報

    """
    # 講座を取得して反映
    course = _get_course(session, course_id)
    _apply_info(session, course, info)
    course.updated_at = datetime.now()


def delete_course(session: Session, course_id: int) -> None:
    """
    講座を削除する(受講記録も削除される)

    Args
    -----------------
    - session: Session,                 DB セッション
    - course_id: int,                   講座 ID

    """
    # 講座を取得して削除
    session.delete(_get_course(session, course_id))
    session.flush()


def get_editor(session: Session, course_id: int) -> CourseEditorOut:
    """
    講座エディタの表示内容(講座情報・全単元・小テスト・データファイル)を返す

    Args
    -----------------
    - session: Session,                 DB セッション
    - course_id: int,                   講座 ID

    Returns
    -----------------
    - editor: CourseEditorOut,          講座エディタの表示内容

    """
    # 講座を単元・セル・問題・データファイル・前提講座とあわせて取得
    course = session.scalar(
        select(Course)
        .where(Course.id == course_id)
        .options(
            selectinload(Course.units).selectinload(Unit.cells).selectinload(Cell.problem),
            selectinload(Course.datasets),
            selectinload(Course.prerequisites),
        )
    )
    if course is None:
        raise NotFoundError(course_id)
    # 小テストの問題
    quiz = session.scalars(
        select(Problem)
        .where(Problem.course_id == course.id, Problem.kind == ProblemKind.QUIZ)
        .order_by(Problem.position)
    )
    # 前提講座の候補(自分以外の講座)
    others = session.execute(select(Course.id, Course.title).where(Course.id != course.id).order_by(Course.id))
    # 表示内容を返却
    return CourseEditorOut(
        id=course.id,
        slug=course.slug,
        title=course.title,
        summary=course.summary,
        level=course.level,
        tags=list(course.tags or []),
        outcomes=list(course.outcomes or []),
        libraries=list(course.libraries or []),
        status=course.status,
        prerequisite_ids=[p.prerequisite_id for p in course.prerequisites],
        units=[_unit_out(u) for u in course.units],
        quiz=[_problem_out(p) for p in quiz],
        datasets=[dataset_out(d) for d in course.datasets],
        other_courses=[{"id": i, "title": t} for i, t in others],
    )


# ---------- 問題の保存 ----------
def _apply_problem(problem: Problem, data: ProblemIn, is_new: bool) -> None:
    """
    問題に入力内容を反映し、採点に関わる変更があれば未検証に戻す

    Args
    -----------------
    - problem: Problem,                 問題
    - data: ProblemIn,                  入力内容
    - is_new: bool,                     新規作成なら True

    """
    # 回答形式・採点方式の確認
    if data.answer_format not in AnswerFormat.ALL:
        raise AdminInputError("回答形式の指定が正しくありません")
    if data.answer_format == AnswerFormat.CODE and data.grading not in Grading.ALL:
        raise AdminInputError("採点方式の指定が正しくありません")
    choices = [c.strip() for c in data.choices if c.strip()]
    # 採点に関わる項目が変わったか(新規は常に変更扱い)
    new_values = data.model_dump()
    new_values["choices"] = choices
    changed = is_new or any(
        getattr(problem, f) != new_values[f] for f in _GRADED_FIELDS if f != "choices"
    ) or list(problem.choices or []) != choices
    # 項目を反映
    problem.answer_format = data.answer_format
    problem.title = data.title.strip()
    problem.prompt = data.prompt
    problem.hint = data.hint
    problem.starter_code = data.starter_code
    problem.grading = data.grading
    problem.test_code = data.test_code
    problem.choices = choices
    problem.correct_answer = data.correct_answer.strip()
    problem.tolerance = data.tolerance
    problem.explanation = data.explanation
    problem.ai_model_answer = data.ai_model_answer
    problem.author_answer = data.author_answer
    if not changed:
        return
    # 変更があれば内容バージョンを上げる(既存の問題のみ)
    if not is_new:
        problem.content_version = (problem.content_version or 1) + 1
    # 選択式・数値入力は正解が正しく設定されていれば検証済み
    if data.answer_format == AnswerFormat.CHOICE:
        valid = len(choices) >= 2 and problem.correct_answer in choices
        problem.verify_status = VerifyStatus.VERIFIED if valid else VerifyStatus.TODO
    elif data.answer_format == AnswerFormat.NUMERIC:
        try:
            valid = math.isfinite(float(problem.correct_answer))
        except ValueError:
            valid = False
        problem.verify_status = VerifyStatus.VERIFIED if valid else VerifyStatus.TODO
    # コード問題はブラウザでの検証が必要
    else:
        problem.verify_status = VerifyStatus.TODO


def add_unit(session: Session, course_id: int, info: UnitInfoIn) -> UnitAdminOut:
    """
    講座の末尾に単元を追加する

    Args
    -----------------
    - session: Session,                 DB セッション
    - course_id: int,                   講座 ID
    - info: UnitInfoIn,                 単元の基本情報

    Returns
    -----------------
    - unit: UnitAdminOut,               追加した単元

    """
    # 講座を取得して末尾の位置を決める
    course = _get_course(session, course_id)
    position = max((u.position for u in course.units), default=0) + 1
    # 単元を追加
    unit = Unit(
        course_id=course.id,
        position=position,
        title=info.title,
        summary=info.summary,
        goals=info.goals,
        estimated_minutes=info.estimated_minutes,
    )
    session.add(unit)
    session.flush()
    # 追加した単元を返却
    return _unit_out(_get_unit(session, unit.id))


def save_unit(session: Session, unit_id: int, data: UnitContentIn) -> UnitAdminOut:
    """
    単元(基本情報とセル一式)を保存する

    画面から送られたセルの並びで置き換える。送られなかったセル・演習は削除する。

    Args
    -----------------
    - session: Session,                 DB セッション
    - unit_id: int,                     単元 ID
    - data: UnitContentIn,              単元の内容

    Returns
    -----------------
    - unit: UnitAdminOut,               保存後の単元

    """
    # 単元を取得して基本情報を反映
    unit = _get_unit(session, unit_id)
    unit.title = data.title.strip()
    unit.summary = data.summary.strip()
    unit.goals = [g.strip() for g in data.goals if g.strip()]
    unit.estimated_minutes = data.estimated_minutes
    # 既存のセル・演習を ID で引けるようにする
    cells_by_id = {c.id: c for c in unit.cells}
    problems_by_id = {c.problem.id: c.problem for c in unit.cells if c.problem is not None}
    kept_cells: set[int] = set()
    kept_problems: set[int] = set()
    exercise_no = 0
    # 送られたセルを順に保存
    for position, cell_in in enumerate(data.cells, start=1):
        if cell_in.cell_type not in CellType.ALL:
            raise AdminInputError("セルの種類の指定が正しくありません")
        problem_id = None
        # 演習セル: 問題を作成・更新する(演習はコード問題のみ)
        if cell_in.cell_type == CellType.EXERCISE:
            if cell_in.problem is None:
                raise AdminInputError("演習セルの内容がありません")
            exercise_no += 1
            p_in = cell_in.problem.model_copy(update={"answer_format": AnswerFormat.CODE})
            problem = problems_by_id.get(p_in.id) if p_in.id else None
            is_new = problem is None
            if problem is None:
                problem = Problem(course_id=unit.course_id, unit_id=unit.id, kind=ProblemKind.EXERCISE)
                session.add(problem)
            _apply_problem(problem, p_in, is_new)
            problem.position = exercise_no
            if not problem.title:
                problem.title = f"演習 {unit.position}-{exercise_no}"
            session.flush()
            kept_problems.add(problem.id)
            problem_id = problem.id
        # セルを作成・更新する
        cell = cells_by_id.get(cell_in.id) if cell_in.id else None
        if cell is None:
            cell = Cell(unit_id=unit.id)
            session.add(cell)
        cell.position = position
        cell.cell_type = cell_in.cell_type
        cell.source = "" if cell_in.cell_type == CellType.EXERCISE else cell_in.source
        cell.problem_id = problem_id
        session.flush()
        kept_cells.add(cell.id)
    # 送られなかったセル・演習を削除
    for cell_id, cell in cells_by_id.items():
        if cell_id not in kept_cells:
            session.delete(cell)
    for problem_id, problem in problems_by_id.items():
        if problem_id not in kept_problems:
            session.delete(problem)
    session.flush()
    # 講座の更新日時を更新して、保存後の単元を返却
    session.get(Course, unit.course_id).updated_at = datetime.now()  # type: ignore[union-attr]
    session.expire(unit)
    return _unit_out(_get_unit(session, unit.id))


def delete_unit(session: Session, unit_id: int) -> None:
    """
    単元を削除し、後ろの単元の並び順を詰める

    Args
    -----------------
    - session: Session,                 DB セッション
    - unit_id: int,                     単元 ID

    """
    # 単元を取得して削除
    unit = _get_unit(session, unit_id)
    course_id = unit.course_id
    session.delete(unit)
    session.flush()
    # 残りの単元を 1 から振り直す
    units = session.scalars(select(Unit).where(Unit.course_id == course_id).order_by(Unit.position))
    for position, u in enumerate(units, start=1):
        u.position = position
    session.flush()


def reorder_units(session: Session, course_id: int, unit_ids: list[int]) -> None:
    """
    単元の並び順を変更する

    Args
    -----------------
    - session: Session,                 DB セッション
    - course_id: int,                   講座 ID
    - unit_ids: list[int],              新しい並び順の単元 ID(講座の全単元)

    """
    # 講座の全単元がちょうど1回ずつ指定されているか確認
    course = _get_course(session, course_id)
    if sorted(unit_ids) != sorted(u.id for u in course.units):
        raise AdminInputError("単元の並び順の指定が正しくありません")
    # 指定された順に位置を振り直す
    by_id = {u.id: u for u in course.units}
    for position, unit_id in enumerate(unit_ids, start=1):
        by_id[unit_id].position = position
    session.flush()


def save_quiz(session: Session, course_id: int, data: QuizContentIn) -> list[ProblemOut]:
    """
    小テストの問題一式を保存する(送られなかった問題は削除する)

    Args
    -----------------
    - session: Session,                 DB セッション
    - course_id: int,                   講座 ID
    - data: QuizContentIn,              小テストの問題

    Returns
    -----------------
    - quiz: list[ProblemOut],           保存後の問題

    """
    # 講座と既存の問題を取得
    course = _get_course(session, course_id)
    unit_ids = {u.id for u in course.units}
    existing = {
        p.id: p
        for p in session.scalars(
            select(Problem).where(Problem.course_id == course.id, Problem.kind == ProblemKind.QUIZ)
        )
    }
    kept: list[Problem] = []
    # 送られた問題を順に保存
    for position, q in enumerate(data.questions, start=1):
        if q.related_unit_id is not None and q.related_unit_id not in unit_ids:
            raise AdminInputError(f"問{position} の関連単元の指定が正しくありません")
        problem = existing.get(q.id) if q.id else None
        is_new = problem is None
        if problem is None:
            problem = Problem(course_id=course.id, unit_id=None, kind=ProblemKind.QUIZ)
            session.add(problem)
        _apply_problem(problem, q, is_new)
        problem.position = position
        problem.title = f"問{position}"
        problem.related_unit_id = q.related_unit_id
        kept.append(problem)
    # 送られなかった問題を削除
    kept_ids = {id(p) for p in kept}
    for problem in existing.values():
        if id(problem) not in kept_ids:
            session.delete(problem)
    session.flush()
    course.updated_at = datetime.now()
    # 保存後の問題を返却
    return [_problem_out(p) for p in kept]


# ---------- 検証 ----------
def verify(session: Session, problem_id: int, data: VerifyIn) -> VerifyOut:
    """
    ブラウザで実行した作成者の解答(と AI の模範解答)の結果から、コード問題を検証する

    Args
    -----------------
    - session: Session,                 DB セッション
    - problem_id: int,                  問題 ID
    - data: VerifyIn,                   実行結果

    Returns
    -----------------
    - result: VerifyOut,                検証結果

    """
    # 問題を取得(コード問題のみ検証できる)
    problem = session.get(Problem, problem_id)
    if problem is None:
        raise NotFoundError(problem_id)
    if problem.answer_format != AnswerFormat.CODE:
        raise AdminInputError("コード問題以外は検証の必要がありません")
    if not problem.author_answer.strip():
        raise AdminInputError("作成者の解答を入力して保存してから検証してください")
    # 作成者の解答が実行時エラーなら検証できない
    if data.author.error:
        raise AdminInputError(f"作成者の解答の実行でエラーが発生しました:\n{data.author.error}")
    has_ai = bool(problem.ai_model_answer.strip())
    ai_output = data.ai.output if data.ai else None
    # 採点方式「テストコード」: 作成者の解答(と AI の模範解答)がテストに合格すること
    if problem.grading == Grading.TEST:
        if not data.author.test_passed:
            problem.verify_status = VerifyStatus.TODO
            message = "作成者の解答がテストに合格しませんでした。解答かテストコードを見直してください。"
        elif has_ai and not (data.ai and not data.ai.error and data.ai.test_passed):
            problem.verify_status = VerifyStatus.MISMATCH
            message = "AI の模範解答がテストに合格しませんでした。どちらが正しいか確認してください。"
        else:
            problem.verify_status = VerifyStatus.VERIFIED
            message = "検証済みになりました。"
    # 採点方式「出力一致」で AI の模範解答がある場合: 両者の出力が一致すること
    elif has_ai:
        if data.ai is None or data.ai.error:
            problem.verify_status = VerifyStatus.MISMATCH
            message = "AI の模範解答を実行できませんでした。どちらが正しいか確認してください。"
        elif outputs_match(data.ai.output, data.author.output, problem.tolerance):
            problem.expected_output = data.ai.output
            problem.verify_status = VerifyStatus.VERIFIED
            message = "AI の想定出力と一致しました。検証済みになりました。"
        else:
            problem.verify_status = VerifyStatus.MISMATCH
            message = "AI の想定出力と一致しません。どちらが正しいか確認してください。"
    # 採点方式「出力一致」で AI の模範解答が無い場合: 作成者の出力を想定出力にする
    else:
        if not data.author.output.strip():
            raise AdminInputError("作成者の解答の出力が空です。print などで結果を出力してください。")
        problem.expected_output = data.author.output
        problem.verify_status = VerifyStatus.VERIFIED
        message = "作成者の解答の出力を想定出力として、検証済みになりました。"
    session.flush()
    # 検証結果を返却
    return VerifyOut(
        verify_status=problem.verify_status,
        message=message,
        expected_output=problem.expected_output,
        author_output=data.author.output,
        ai_output=ai_output,
    )


def accept_author(session: Session, problem_id: int, output: str) -> VerifyOut:
    """
    AI の想定と不一致の問題について、作成者の解答の出力を正として検証済みにする

    Args
    -----------------
    - session: Session,                 DB セッション
    - problem_id: int,                  問題 ID
    - output: str,                      作成者の解答の出力

    Returns
    -----------------
    - result: VerifyOut,                検証結果

    """
    # 問題を取得(不一致の問題のみ対象)
    problem = session.get(Problem, problem_id)
    if problem is None:
        raise NotFoundError(problem_id)
    if problem.verify_status != VerifyStatus.MISMATCH:
        raise AdminInputError("AI の想定と不一致の問題だけが対象です")
    # 出力一致の問題は作成者の出力を想定出力にする
    if problem.grading == Grading.OUTPUT:
        if not output.strip():
            raise AdminInputError("作成者の解答の出力が空です")
        problem.expected_output = output
    problem.verify_status = VerifyStatus.VERIFIED
    session.flush()
    # 検証結果を返却
    return VerifyOut(
        verify_status=problem.verify_status,
        message="作成者の解答を正として、検証済みになりました。",
        expected_output=problem.expected_output,
        author_output=output,
        ai_output=None,
    )


def confirm_problem(session: Session, problem_id: int) -> VerifyOut:
    """
    選択式・数値入力の問題を、作成者が内容を確認したものとして検証済みにする(AI が作った問題など)

    Args
    -----------------
    - session: Session,                 DB セッション
    - problem_id: int,                  問題 ID

    Returns
    -----------------
    - result: VerifyOut,                検証結果

    """
    # 問題を取得(選択式・数値入力のみ対象)
    problem = session.get(Problem, problem_id)
    if problem is None:
        raise NotFoundError(problem_id)
    if problem.answer_format == AnswerFormat.CODE:
        raise AdminInputError("コード問題は「解答を実行して検証」で検証してください")
    # 正解が正しく設定されていることを確認
    if problem.answer_format == AnswerFormat.CHOICE:
        if len(problem.choices or []) < 2 or problem.correct_answer not in (problem.choices or []):
            raise AdminInputError("選択肢を2つ以上用意し、正解を選んで保存してください")
    else:
        try:
            if not math.isfinite(float(problem.correct_answer)):
                raise ValueError
        except ValueError:
            raise AdminInputError("正解の数値を入力して保存してください")
    # 検証済みにする
    problem.verify_status = VerifyStatus.VERIFIED
    session.flush()
    return VerifyOut(
        verify_status=problem.verify_status,
        message="内容を確認して、検証済みにしました。",
        expected_output="",
        author_output="",
        ai_output=None,
    )


# ---------- .ipynb の取り込み ----------
def _safe_extract(data: bytes, dest: Path) -> Path:
    """
    zip を展開し、course.json のあるフォルダを返す(展開先の外に出るパスは拒否する)

    Args
    -----------------
    - data: bytes,                      zip の内容
    - dest: Path,                       展開先

    Returns
    -----------------
    - course_dir: Path,                 course.json のあるフォルダ

    """
    # zip として開けるか確認
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise AdminInputError("zip ファイルとして読み込めませんでした")
    root = dest.resolve()
    total = 0
    with archive:
        for info in archive.infolist():
            # 展開先の外を指すパス(../ や絶対パス)は拒否する
            target = (root / info.filename).resolve()
            if root not in target.parents and target != root:
                raise AdminInputError(f"zip に不正なパスが含まれています: {info.filename}")
            total += info.file_size
            if total > MAX_IMPORT_BYTES * 4:
                raise AdminInputError("zip の展開後のサイズが大きすぎます")
        archive.extractall(root)
    # course.json を探す(zip の直下、または1階層下のフォルダ)
    candidates = [p.parent for p in root.glob("course.json")] + [p.parent for p in root.glob("*/course.json")]
    if len(candidates) != 1:
        raise AdminInputError("zip の中に course.json が見つかりません(講座フォルダを zip にしてください)")
    return candidates[0]


def import_course_zip(session: Session, author: User, data: bytes, replace: bool) -> Course:
    """
    講座フォルダの zip(course.json + .ipynb + data/)を取り込み、下書きの講座として登録する

    Args
    -----------------
    - session: Session,                 DB セッション
    - author: User,                     作成者
    - data: bytes,                      zip の内容
    - replace: bool,                    同じ識別名の講座を置き換えるなら True

    Returns
    -----------------
    - course: Course,                   登録した講座

    """
    # サイズの確認
    if len(data) > MAX_IMPORT_BYTES:
        raise AdminInputError("ファイルが大きすぎます(上限 50MB)")
    # 一時フォルダに展開して取り込む(公開前チェックを通すため、必ず下書きで登録する)
    with tempfile.TemporaryDirectory() as tmp:
        course_dir = _safe_extract(data, Path(tmp))
        try:
            return import_course(session, course_dir, author=author, replace=replace, force_status=CourseStatus.DRAFT)
        except NotebookFormatError as e:
            raise AdminInputError(f"取り込みに失敗しました: {e}")
        except (KeyError, ValueError) as e:
            raise AdminInputError(f"course.json の内容が正しくありません: {e}")


def import_unit_notebook(session: Session, course_id: int, filename: str, data: bytes) -> UnitAdminOut:
    """
    .ipynb を1つ読み込み、講座の末尾に単元として追加する

    Args
    -----------------
    - session: Session,                 DB セッション
    - course_id: int,                   講座 ID
    - filename: str,                    ファイル名
    - data: bytes,                      .ipynb の内容

    Returns
    -----------------
    - unit: UnitAdminOut,               追加した単元

    """
    # サイズと拡張子の確認
    if len(data) > MAX_IMPORT_BYTES:
        raise AdminInputError("ファイルが大きすぎます(上限 50MB)")
    if not filename.lower().endswith(".ipynb"):
        raise AdminInputError(".ipynb ファイルを選んでください")
    course = _get_course(session, course_id)
    # 一時ファイルに書き出して解析する
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "unit.ipynb"
        path.write_bytes(data)
        try:
            parsed = parse_notebook(path)
        except NotebookFormatError as e:
            raise AdminInputError(f"取り込みに失敗しました: {str(e).replace('unit.ipynb', filename)}")
        except Exception:
            raise AdminInputError("ノートブックとして読み込めませんでした")
    # 講座の末尾に単元として登録
    position = max((u.position for u in course.units), default=0) + 1
    unit = add_parsed_unit(session, course.id, parsed, position, 20)
    return _unit_out(_get_unit(session, unit.id))


# ---------- 公開 ----------
def publish_check(session: Session, course_id: int) -> PublishCheckOut:
    """
    公開前チェックを行う(例題の実行チェックはブラウザで別途行う)

    Args
    -----------------
    - session: Session,                 DB セッション
    - course_id: int,                   講座 ID

    Returns
    -----------------
    - result: PublishCheckOut,          チェック結果

    """
    # 講座を単元・問題とあわせて取得
    course = session.scalar(
        select(Course)
        .where(Course.id == course_id)
        .options(selectinload(Course.units).selectinload(Unit.cells).selectinload(Cell.problem))
    )
    if course is None:
        raise NotFoundError(course_id)
    checks: list[CheckOut] = []
    # 1. 講座情報
    missing = [name for name, v in (("タイトル", course.title), ("概要", course.summary)) if not v.strip()]
    checks.append(
        CheckOut(
            key="info",
            label="講座情報(タイトル・概要・レベル)が入力されている",
            ok=not missing,
            detail="未入力: " + "、".join(missing) if missing else "",
        )
    )
    # 2. 単元に演習がある
    no_exercise = [u for u in course.units if not any(c.problem for c in u.cells)]
    checks.append(
        CheckOut(
            key="units",
            label="単元が1つ以上あり、すべての単元に演習が1問以上ある",
            ok=bool(course.units) and not no_exercise,
            detail="単元がありません" if not course.units else "",
            items=[
                CheckItemOut(label=f"単元{u.position} {u.title}", status="no_exercise", unit_id=u.id, problem_id=None)
                for u in no_exercise
            ],
        )
    )
    # 3. 演習がすべて検証済み
    exercises = [(u, c.problem) for u in course.units for c in u.cells if c.problem is not None]
    todo = [(u, p) for u, p in exercises if p.verify_status != VerifyStatus.VERIFIED]
    checks.append(
        CheckOut(
            key="exercises",
            label="演習の作成者解答がすべて検証済み",
            ok=not todo,
            detail=f"{len(exercises) - len(todo)} / {len(exercises)}",
            items=[
                CheckItemOut(
                    label=f"単元{u.position} {p.title}", status=p.verify_status, unit_id=u.id, problem_id=p.id
                )
                for u, p in todo
            ],
        )
    )
    # 4. 小テストがあり、すべて検証済み
    quiz = list(
        session.scalars(
            select(Problem)
            .where(Problem.course_id == course.id, Problem.kind == ProblemKind.QUIZ)
            .order_by(Problem.position)
        )
    )
    quiz_todo = [p for p in quiz if p.verify_status != VerifyStatus.VERIFIED]
    checks.append(
        CheckOut(
            key="quiz",
            label="小テストが1問以上あり、すべて検証済み",
            ok=bool(quiz) and not quiz_todo,
            detail=f"{len(quiz) - len(quiz_todo)} / {len(quiz)}" if quiz else "小テストの問題がありません",
            items=[
                CheckItemOut(label=p.title, status=p.verify_status, unit_id=None, problem_id=p.id) for p in quiz_todo
            ],
        )
    )
    # 結果を返却
    return PublishCheckOut(
        course_id=course.id,
        slug=course.slug,
        title=course.title,
        status=course.status,
        checks=checks,
        publishable=all(c.ok for c in checks),
    )


def publish(session: Session, course_id: int, examples_ok: bool) -> None:
    """
    講座を公開する(公開前チェックをすべて満たす場合のみ)

    Args
    -----------------
    - session: Session,                 DB セッション
    - course_id: int,                   講座 ID
    - examples_ok: bool,                ブラウザで例題がすべてエラーなく実行できたか

    """
    # サーバ側のチェックとブラウザ側の例題チェックを確認
    result = publish_check(session, course_id)
    if not result.publishable:
        raise AdminInputError("公開前チェックを満たしていない項目があります")
    if not examples_ok:
        raise AdminInputError("例題コードの実行チェックを完了してください")
    # 公開状態にする(初回のみ公開日時を記録)
    course = _get_course(session, course_id)
    course.status = CourseStatus.PUBLISHED
    if course.published_at is None:
        course.published_at = datetime.now()
    session.flush()


def unpublish(session: Session, course_id: int) -> None:
    """
    講座を下書きに戻す(受講者から見えなくなる。受講記録は残る)

    Args
    -----------------
    - session: Session,                 DB セッション
    - course_id: int,                   講座 ID

    """
    # 下書きに戻す
    _get_course(session, course_id).status = CourseStatus.DRAFT
    session.flush()


# ---------- データファイル ----------
def add_dataset(session: Session, course_id: int, filename: str, content_type: str, data: bytes) -> None:
    """
    講座にデータファイルを追加する(同名のファイルは置き換える)

    Args
    -----------------
    - session: Session,                 DB セッション
    - course_id: int,                   講座 ID
    - filename: str,                    ファイル名
    - content_type: str,                MIME タイプ
    - data: bytes,                      ファイルの内容

    """
    # ファイル名とサイズの確認(ディレクトリを含む名前は受け付けない)
    name = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name or name.startswith("."):
        raise AdminInputError("ファイル名が正しくありません")
    if len(data) > MAX_DATASET_BYTES:
        raise AdminInputError("ファイルが大きすぎます(上限 20MB)")
    course = _get_course(session, course_id)
    # 同名のファイルがあれば置き換え、無ければ追加
    existing = session.scalar(select(Dataset).where(Dataset.course_id == course.id, Dataset.filename == name))
    if existing is not None:
        existing.content = data
        existing.content_type = content_type or "application/octet-stream"
    else:
        session.add(
            Dataset(course_id=course.id, filename=name, content_type=content_type or "application/octet-stream", content=data)
        )
    session.flush()


def delete_dataset(session: Session, dataset_id: int) -> None:
    """
    データファイルを削除する

    Args
    -----------------
    - session: Session,                 DB セッション
    - dataset_id: int,                  データファイル ID

    """
    # データファイルを取得して削除
    dataset = session.get(Dataset, dataset_id)
    if dataset is None:
        raise NotFoundError(dataset_id)
    session.delete(dataset)
    session.flush()
