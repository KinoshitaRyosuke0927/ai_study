"""小テストの出題・採点と、講座の修了を記録するモジュール。

受験できるのは講座の全単元を完了したユーザのみ。満点で講座修了となり、再受験は自由。
"""

from __future__ import annotations

import math
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.common.constants import AnswerFormat, Grading, ProblemKind
from app.models import Course, CourseCompletion, Problem, QuizAttempt, Submission, Unit, UnitProgress, User
from app.schemas import (
    QuizAnswerIn,
    QuizAttemptOut,
    QuizOut,
    QuizQuestionOut,
    QuizQuestionResultOut,
    QuizResultOut,
    QuizSubmitRequest,
    RelatedUnitOut,
)
from app.services.course_service import NotFoundError, dataset_out, visible_course_query
from app.services.submission_service import grade_code


class QuizLockedError(Exception):
    """全単元を完了していないため受験できない。"""


def _load_course(session: Session, user: User, slug: str) -> Course:
    """
    閲覧できる講座を単元・データファイルとあわせて取得する

    Args
    -----------------
    - session: Session,                 DB セッション
    - user: User,                       ログイン中ユーザ
    - slug: str,                        講座の識別名

    Returns
    -----------------
    - course: Course,                   講座

    """
    # 閲覧できる講座から識別名で検索
    course = session.scalar(
        visible_course_query(user).where(Course.slug == slug).options(selectinload(Course.datasets))
    )
    # 見つからない場合はエラー
    if course is None:
        raise NotFoundError(slug)
    # 講座を返却
    return course


def _remaining_units(session: Session, user: User, course: Course) -> list[Unit]:
    """
    講座内で未完了の単元を返す

    Args
    -----------------
    - session: Session,                 DB セッション
    - user: User,                       ログイン中ユーザ
    - course: Course,                   講座

    Returns
    -----------------
    - units: list[Unit],                未完了の単元(並び順)

    """
    # 完了済みの単元 ID を取得
    done = set(session.scalars(select(UnitProgress.unit_id).where(UnitProgress.user_id == user.id)))
    # 完了していない単元を返却
    return [u for u in course.units if u.id not in done]


def _questions(session: Session, course: Course) -> list[Problem]:
    """
    講座の小テストの問題を並び順で返す

    Args
    -----------------
    - session: Session,                 DB セッション
    - course: Course,                   講座

    Returns
    -----------------
    - problems: list[Problem],          問題

    """
    # 小テストの問題を並び順で取得して返却
    return list(
        session.scalars(
            select(Problem)
            .where(Problem.course_id == course.id, Problem.kind == ProblemKind.QUIZ)
            .order_by(Problem.position)
        )
    )


def _related(units: dict[int, Unit], unit_id: int | None) -> RelatedUnitOut | None:
    """
    関連単元を出力形式に変換する

    Args
    -----------------
    - units: dict[int, Unit],           単元 ID → 単元
    - unit_id: int | None,              関連単元 ID

    Returns
    -----------------
    - related: RelatedUnitOut | None,   関連単元(無ければ None)

    """
    # 関連単元が無い場合は None
    unit = units.get(unit_id) if unit_id is not None else None
    if unit is None:
        return None
    # 出力形式に変換して返却
    return RelatedUnitOut(id=unit.id, position=unit.position, title=unit.title)


def _attempts(session: Session, user: User, course: Course) -> list[QuizAttemptOut]:
    """
    ユーザの受験記録を新しい順に返す

    Args
    -----------------
    - session: Session,                 DB セッション
    - user: User,                       ログイン中ユーザ
    - course: Course,                   講座

    Returns
    -----------------
    - attempts: list[QuizAttemptOut],   受験記録

    """
    # 受験記録を新しい順に取得して返却
    rows = session.scalars(
        select(QuizAttempt)
        .where(QuizAttempt.user_id == user.id, QuizAttempt.course_id == course.id)
        .order_by(QuizAttempt.id.desc())
    )
    return [QuizAttemptOut(id=a.id, score=a.score, total=a.total, created_at=a.created_at) for a in rows]


def get_quiz(session: Session, user: User, slug: str) -> QuizOut:
    """
    小テスト画面の表示内容を返す(まだ受験できない場合は問題を含めない)

    Args
    -----------------
    - session: Session,                 DB セッション
    - user: User,                       ログイン中ユーザ
    - slug: str,                        講座の識別名

    Returns
    -----------------
    - quiz: QuizOut,                    小テストの表示内容

    """
    # 講座と未完了の単元を取得
    course = _load_course(session, user, slug)
    remaining = _remaining_units(session, user, course)
    unlocked = not remaining
    units = {u.id: u for u in course.units}
    # 受験できる場合だけ問題を渡す(正解・想定出力は含めない)
    questions: list[QuizQuestionOut] = []
    if unlocked:
        for p in _questions(session, course):
            questions.append(
                QuizQuestionOut(
                    problem_id=p.id,
                    position=p.position,
                    answer_format=p.answer_format,
                    prompt=p.prompt,
                    choices=list(p.choices or []),
                    starter_code=p.starter_code,
                    grading=p.grading,
                    test_code=p.test_code if p.grading == Grading.TEST else "",
                    related_unit=_related(units, p.related_unit_id),
                )
            )
    # 修了済みかどうか
    completed = session.get(CourseCompletion, (user.id, course.id)) is not None
    # 表示内容を返却
    return QuizOut(
        course_slug=course.slug,
        course_title=course.title,
        unlocked=unlocked,
        remaining_units=[RelatedUnitOut(id=u.id, position=u.position, title=u.title) for u in remaining],
        completed=completed,
        questions=questions,
        attempts=_attempts(session, user, course),
        datasets=[dataset_out(d) for d in course.datasets],
    )


def _normalize(text: str) -> str:
    """
    回答文字列を比較用に正規化する(全角英数字を半角に、前後の空白を除去)

    Args
    -----------------
    - text: str,                        回答

    Returns
    -----------------
    - normalized: str,                  正規化した回答

    """
    # NFKC で全角・半角を揃えて前後の空白を除いて返却
    return unicodedata.normalize("NFKC", text).strip()


def _grade(problem: Problem, answer: QuizAnswerIn | None) -> tuple[bool, bool, str]:
    """
    小テストの1問を採点する

    Args
    -----------------
    - problem: Problem,                 問題
    - answer: QuizAnswerIn | None,      回答(未回答なら None)

    Returns
    -----------------
    - correct: bool,                    正解なら True
    - answered: bool,                   回答があれば True
    - message: str,                     受講者に表示するメッセージ

    """
    # 未回答は不正解
    if answer is None or (problem.answer_format != AnswerFormat.CODE and not answer.answer.strip()):
        return False, False, "未回答です。"
    # 選択式: 選択肢の文言が正解と一致するか
    if problem.answer_format == AnswerFormat.CHOICE:
        ok = answer.answer == problem.correct_answer
        return ok, True, "正解です。" if ok else "不正解です。"
    # 数値入力: 許容誤差内で一致するか
    if problem.answer_format == AnswerFormat.NUMERIC:
        try:
            value = float(_normalize(answer.answer).replace(",", ""))
        except ValueError:
            return False, True, "数値として読み取れませんでした。"
        expected = float(problem.correct_answer)
        ok = math.isfinite(value) and math.isclose(
            value, expected, rel_tol=problem.tolerance, abs_tol=problem.tolerance
        )
        return ok, True, "正解です。" if ok else "不正解です。"
    # コード: 演習と同じ方法で採点
    ok, message = grade_code(problem, answer)
    return ok, True, message


def submit_quiz(session: Session, user: User, slug: str, req: QuizSubmitRequest) -> QuizResultOut:
    """
    小テストを採点して記録する(満点なら講座の修了を記録する)

    Args
    -----------------
    - session: Session,                 DB セッション
    - user: User,                       ログイン中ユーザ
    - slug: str,                        講座の識別名
    - req: QuizSubmitRequest,           回答

    Returns
    -----------------
    - result: QuizResultOut,            採点結果

    """
    # 講座を取得し、全単元を完了しているか確認
    course = _load_course(session, user, slug)
    if _remaining_units(session, user, course):
        raise QuizLockedError(slug)
    problems = _questions(session, course)
    if not problems:
        raise NotFoundError(slug)
    units = {u.id: u for u in course.units}
    answers = {a.problem_id: a for a in req.answers}
    # 受験記録を作成(得点は採点後に設定)
    attempt = QuizAttempt(user_id=user.id, course_id=course.id, score=0, total=len(problems))
    session.add(attempt)
    session.flush()
    # 1問ずつ採点して提出を記録
    results: list[QuizQuestionResultOut] = []
    for p in problems:
        answer = answers.get(p.id)
        correct, answered, message = _grade(p, answer)
        session.add(
            Submission(
                user_id=user.id,
                problem_id=p.id,
                attempt_id=attempt.id,
                answer=answer.answer if answer else "",
                output=answer.output if answer else "",
                passed=correct,
                content_version=p.content_version,
            )
        )
        results.append(
            QuizQuestionResultOut(
                problem_id=p.id,
                correct=correct,
                answered=answered,
                message=message,
                # 解説は正解した問題だけに付ける(不正解の問題は関連単元で復習してもらう)
                explanation=p.explanation if correct else "",
                related_unit=_related(units, p.related_unit_id),
            )
        )
    attempt.score = sum(1 for r in results if r.correct)
    # 満点かつ未修了なら修了を記録
    perfect = attempt.score == attempt.total
    newly = False
    if perfect and session.get(CourseCompletion, (user.id, course.id)) is None:
        session.add(CourseCompletion(user_id=user.id, course_id=course.id))
        newly = True
    session.flush()
    session.refresh(attempt)
    # 採点結果を返却
    return QuizResultOut(
        attempt=QuizAttemptOut(
            id=attempt.id, score=attempt.score, total=attempt.total, created_at=attempt.created_at
        ),
        perfect=perfect,
        course_newly_completed=newly,
        results=results,
    )
