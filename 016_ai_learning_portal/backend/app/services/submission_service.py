"""演習の提出を採点し、単元の完了を記録するモジュール。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.constants import AnswerFormat, CourseStatus, Grading, ProblemKind
from app.models import Course, Problem, Submission, UnitProgress, User
from app.schemas import AnswerSubmitRequest, CodeSubmitRequest, QuizAnswerIn, SubmitResultOut
from app.services.answer_check import grade_answer
from app.services.course_service import NotFoundError
from app.services.grading import outputs_match


def grade_code(problem: Problem, req: CodeSubmitRequest | QuizAnswerIn) -> tuple[bool, str]:
    """
    コード問題を採点する

    Args
    -----------------
    - problem: Problem,                 問題
    - req: CodeSubmitRequest | QuizAnswerIn, 提出内容(ブラウザでの実行結果を含む)

    Returns
    -----------------
    - passed: bool,                     正解なら True
    - message: str,                     受講者に表示するメッセージ

    """
    # 実行時にエラーが出ていた場合は不正解
    if req.error:
        return False, "コードの実行中にエラーが発生しました。エラーメッセージを確認してください。"
    # 採点方式が「テストコード」の場合はブラウザでのテスト結果で判定
    if problem.grading == Grading.TEST:
        if req.test_passed:
            return True, "正解です。"
        return False, "テストに合格しませんでした。問題文の条件を確認してください。"
    # 採点方式が「出力一致」の場合は想定出力と比較
    if outputs_match(problem.expected_output, req.output, problem.tolerance):
        return True, "正解です。"
    # 一致しない場合は不正解
    return False, "出力が期待値と一致しません。ヒントを確認してみましょう。"


def _update_unit_progress(session: Session, user: User, unit_id: int) -> tuple[bool, bool]:
    """
    単元内の演習がすべて正解済みなら単元の完了を記録する

    Args
    -----------------
    - session: Session,                 DB セッション
    - user: User,                       ログイン中ユーザ
    - unit_id: int,                     単元 ID

    Returns
    -----------------
    - completed: bool,                  単元が完了済みなら True
    - newly: bool,                      今回の提出で完了になったなら True

    """
    # すでに完了記録があれば何もしない
    if session.get(UnitProgress, (user.id, unit_id)) is not None:
        return True, False
    # 単元内の演習 ID を取得
    exercise_ids = set(
        session.scalars(
            select(Problem.id).where(
                Problem.unit_id == unit_id, Problem.kind == ProblemKind.EXERCISE
            )
        )
    )
    # 正解済みの演習 ID を取得
    passed_ids = set(
        session.scalars(
            select(Submission.problem_id).where(
                Submission.user_id == user.id,
                Submission.problem_id.in_(exercise_ids),
                Submission.passed.is_(True),
            )
        )
    )
    # 未正解の演習が残っていれば未完了
    if exercise_ids - passed_ids:
        return False, False
    # すべて正解済みなら完了を記録
    session.add(UnitProgress(user_id=user.id, unit_id=unit_id))
    session.flush()
    return True, True


def submit_code(
    session: Session, user: User, problem_id: int, req: CodeSubmitRequest
) -> SubmitResultOut:
    """
    コード問題の提出を採点して記録する

    Args
    -----------------
    - session: Session,                 DB セッション
    - user: User,                       ログイン中ユーザ
    - problem_id: int,                  問題 ID
    - req: CodeSubmitRequest,           提出内容

    Returns
    -----------------
    - result: SubmitResultOut,          採点結果

    """
    # 問題を取得(コード問題のみ対象)
    problem = _submittable_problem(session, user, problem_id)
    if problem.answer_format != AnswerFormat.CODE:
        raise NotFoundError(problem_id)
    # 採点
    passed, message = grade_code(problem, req)
    # 提出を記録して結果を返却
    return _record(session, user, problem, req.code, req.output, passed, message)


def submit_answer(
    session: Session, user: User, problem_id: int, req: AnswerSubmitRequest
) -> SubmitResultOut:
    """
    演習(選択式・数値入力・表形式の選択)の回答を採点して記録する

    小テストの問題は小テストとしてまとめて採点するため、ここでは単元の演習だけを受け付ける
    (1問ずつ正誤を確かめられないようにする)。

    Args
    -----------------
    - session: Session,                 DB セッション
    - user: User,                       ログイン中ユーザ
    - problem_id: int,                  問題 ID
    - req: AnswerSubmitRequest,         回答

    Returns
    -----------------
    - result: SubmitResultOut,          採点結果

    """
    # 問題を取得(単元の演習で、選択式・数値入力・表形式のみ対象)
    problem = _submittable_problem(session, user, problem_id)
    if problem.kind != ProblemKind.EXERCISE or problem.answer_format not in AnswerFormat.KEYED:
        raise NotFoundError(problem_id)
    # 採点(未回答は記録せずに返す)
    passed, answered, message = grade_answer(problem, req.answer)
    if not answered:
        return SubmitResultOut(passed=False, message=message, unit_completed=False, unit_newly_completed=False)
    # 提出を記録して結果を返却
    return _record(session, user, problem, req.answer, "", passed, message)


def _submittable_problem(session: Session, user: User, problem_id: int) -> Problem:
    """
    ユーザが提出できる問題を取得する

    Args
    -----------------
    - session: Session,                 DB セッション
    - user: User,                       ログイン中ユーザ
    - problem_id: int,                  問題 ID

    Returns
    -----------------
    - problem: Problem,                 問題

    """
    # 問題を取得(存在しなければエラー)
    problem = session.get(Problem, problem_id)
    if problem is None:
        raise NotFoundError(problem_id)
    # 非公開講座の問題を、管理者・作成者以外が提出した場合はエラー
    course = session.get(Course, problem.course_id)
    if not (user.is_admin or course.status == CourseStatus.PUBLISHED or course.author_id == user.id):
        raise NotFoundError(problem_id)
    return problem


def _record(
    session: Session, user: User, problem: Problem, answer: str, output: str, passed: bool, message: str
) -> SubmitResultOut:
    """
    提出を記録し、単元の完了状況を更新して採点結果を返す

    Args
    -----------------
    - session: Session,                 DB セッション
    - user: User,                       ログイン中ユーザ
    - problem: Problem,                 問題
    - answer: str,                      回答(コード・選択肢・数値など)
    - output: str,                      実行結果の出力(コード問題のみ)
    - passed: bool,                     正解なら True
    - message: str,                     採点のメッセージ

    Returns
    -----------------
    - result: SubmitResultOut,          採点結果

    """
    # 提出を記録
    session.add(
        Submission(
            user_id=user.id,
            problem_id=problem.id,
            answer=answer,
            output=output,
            passed=passed,
            content_version=problem.content_version,
        )
    )
    session.flush()
    # 演習なら単元の完了状況を更新
    completed, newly = False, False
    if problem.kind == ProblemKind.EXERCISE and problem.unit_id is not None:
        completed, newly = _update_unit_progress(session, user, problem.unit_id)
    # 正解時は解説を添える
    if passed and problem.explanation:
        message = f"{message}{problem.explanation}"
    # 採点結果を返却
    return SubmitResultOut(
        passed=passed, message=message, unit_completed=completed, unit_newly_completed=newly
    )
