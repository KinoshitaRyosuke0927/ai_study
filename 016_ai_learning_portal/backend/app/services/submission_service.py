"""演習の提出を採点し、単元の完了を記録するモジュール。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.constants import AnswerFormat, CourseStatus, Grading, ProblemKind
from app.models import Course, Problem, Submission, UnitProgress, User
from app.schemas import CodeSubmitRequest, SubmitResultOut
from app.services.course_service import NotFoundError
from app.services.grading import outputs_match


def _grade_code(problem: Problem, req: CodeSubmitRequest) -> tuple[bool, str]:
    """
    コード問題を採点する

    Args
    -----------------
    - problem: Problem,                 問題
    - req: CodeSubmitRequest,           提出内容

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
    # 問題を取得
    problem = session.get(Problem, problem_id)
    # 存在しない、またはコード問題でない場合はエラー
    if problem is None or problem.answer_format != AnswerFormat.CODE:
        raise NotFoundError(problem_id)
    # 非公開講座の問題を管理者以外が提出した場合はエラー
    course = session.get(Course, problem.course_id)
    if not user.is_admin and course.status != CourseStatus.PUBLISHED:
        raise NotFoundError(problem_id)
    # 採点
    passed, message = _grade_code(problem, req)
    # 提出を記録
    session.add(
        Submission(
            user_id=user.id,
            problem_id=problem.id,
            answer=req.code,
            output=req.output,
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
