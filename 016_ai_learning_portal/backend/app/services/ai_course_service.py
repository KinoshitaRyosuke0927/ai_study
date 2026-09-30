"""AI による講座下書きの生成(構成案 → 下書き)を扱うモジュール。

流れ:
1. generate_outline: 題材から構成案を作る(DB には保存しない。画面で編集してもらう)
2. create_draft_job: 編集後の構成案から講座(下書き)と単元を作り、生成ジョブを登録する
3. run_draft_job: 単元ごと・小テストの順に AI で下書きを作って保存する(バックグラウンドで実行)

AI が作った問題はすべて「未検証」で保存する。コード問題は作成者の解答で、選択式・数値入力は
作成者の確認で検証済みにする(AI の出力をそのまま公開しない)。
"""

from __future__ import annotations

import math
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.client import AIUnavailableError
from app.ai.generator import AIOutputError, generate
from app.ai.prompts import outline_prompt, quiz_prompt, unit_prompt
from app.ai.schemas import CourseOutline, GeneratedQuestion, OutlineRequest, QuizDraft, UnitDraft
from app.common.constants import AnswerFormat, CellType, CourseStatus, Grading, ProblemKind, VerifyStatus
from app.config.settings import get_settings
from app.infra.db import new_session
from app.models import AIJob, Cell, Course, Problem, Unit, User
from app.services.admin_course_service import AdminInputError
from app.services.course_service import NotFoundError

# ジョブの状態
JOB_QUEUED, JOB_RUNNING, JOB_DONE, JOB_FAILED = "queued", "running", "done", "failed"


def generate_outline(session: Session, req: OutlineRequest) -> CourseOutline:
    """
    題材から講座の構成案を作る

    Args
    -----------------
    - session: Session,                 DB セッション(AI 呼び出しの記録に使う)
    - req: OutlineRequest,              構成案の生成依頼

    Returns
    -----------------
    - outline: CourseOutline,           構成案

    """
    # プロンプトを組み立てて AI を呼び出す
    system, user = outline_prompt(req)
    return generate(session, CourseOutline, system, user, get_settings().ai_model_outline, "outline")


def create_draft_job(
    session: Session, author: User, slug: str, req: OutlineRequest, outline: CourseOutline
) -> AIJob:
    """
    構成案から講座(下書き)と単元を作り、下書き生成ジョブを登録する

    Args
    -----------------
    - session: Session,                 DB セッション
    - author: User,                     作成者
    - slug: str,                        講座の識別名
    - req: OutlineRequest,              元の生成依頼(レベルなど)
    - outline: CourseOutline,           画面で編集した構成案

    Returns
    -----------------
    - job: AIJob,                       登録したジョブ

    """
    # 識別名の重複を確認
    if session.scalar(select(Course).where(Course.slug == slug)) is not None:
        raise AdminInputError(f"識別名 '{slug}' は別の講座で使われています")
    # 講座を下書きで作成(構成案の内容を講座情報にする)
    course = Course(
        slug=slug,
        title=outline.title,
        summary=outline.summary,
        level=req.level,
        tags=outline.tags,
        outcomes=outline.outcomes,
        libraries=outline.libraries or req.libraries,
        status=CourseStatus.DRAFT,
        author_id=author.id,
    )
    session.add(course)
    session.flush()
    # 単元を作成(中身はジョブで生成する)
    for position, u in enumerate(outline.units, start=1):
        session.add(
            Unit(
                course_id=course.id,
                position=position,
                title=u.title,
                summary=u.summary,
                goals=u.goals,
                estimated_minutes=u.minutes,
            )
        )
    # ジョブを登録(単元の数 + 小テスト = 手順の数)
    job = AIJob(
        course_id=course.id,
        kind="course_draft",
        status=JOB_QUEUED,
        total_steps=len(outline.units) + 1,
        request={"request": req.model_dump(), "outline": outline.model_dump()},
        created_by=author.id,
    )
    session.add(job)
    session.flush()
    # 登録したジョブを返却
    return job


def _save_unit_draft(session: Session, unit: Unit, draft: UnitDraft) -> int:
    """
    単元の下書きをセル・演習として保存する(既存のセルは置き換える)

    Args
    -----------------
    - session: Session,                 DB セッション
    - unit: Unit,                       単元
    - draft: UnitDraft,                 AI が作った単元の下書き

    Returns
    -----------------
    - exercise_count: int,              保存した演習の数

    """
    # 既存のセルと演習を削除
    for cell in list(unit.cells):
        if cell.problem is not None:
            session.delete(cell.problem)
        session.delete(cell)
    session.flush()
    exercise_no = 0
    # セルを順に保存
    for position, c in enumerate(draft.cells, start=1):
        problem_id = None
        # 演習: 問題を作る(AI の模範解答は ai_model_answer に入れ、作成者の解答は空にする)
        if c.type == "exercise":
            if c.exercise is None:
                continue
            ex = c.exercise
            exercise_no += 1
            grading = ex.grading if ex.grading == Grading.OUTPUT or ex.test_code.strip() else Grading.OUTPUT
            problem = Problem(
                course_id=unit.course_id,
                unit_id=unit.id,
                kind=ProblemKind.EXERCISE,
                position=exercise_no,
                answer_format=AnswerFormat.CODE,
                title=ex.title,
                prompt=ex.prompt,
                hint=ex.hint,
                starter_code=ex.starter_code,
                grading=grading,
                test_code=ex.test_code if grading == Grading.TEST else "",
                explanation=ex.explanation,
                ai_model_answer=ex.model_answer,
                author_answer="",
                verify_status=VerifyStatus.TODO,
            )
            session.add(problem)
            session.flush()
            problem_id = problem.id
        # セルを保存(AI が作ったことを記録する)
        session.add(
            Cell(
                unit_id=unit.id,
                position=position,
                cell_type=CellType.EXERCISE if c.type == "exercise" else c.type,
                source="" if c.type == "exercise" else c.source,
                problem_id=problem_id,
                ai_generated=True,
            )
        )
    session.flush()
    # 保存した演習の数を返却
    return exercise_no


def _question_problem(course: Course, units: list[Unit], position: int, q: GeneratedQuestion) -> Problem:
    """
    AI が作った小テストの問題から Problem を生成する(すべて未検証)

    Args
    -----------------
    - course: Course,                   講座
    - units: list[Unit],                講座の単元(並び順)
    - position: int,                    並び順
    - q: GeneratedQuestion,             AI が作った問題

    Returns
    -----------------
    - problem: Problem,                 生成した問題(未登録)

    """
    # 関連単元(範囲外なら付けない)
    related = units[q.unit - 1].id if q.unit and 1 <= q.unit <= len(units) else None
    problem = Problem(
        course_id=course.id,
        unit_id=None,
        kind=ProblemKind.QUIZ,
        position=position,
        answer_format=q.type,
        title=f"問{position}",
        prompt=q.prompt,
        explanation=q.explanation,
        related_unit_id=related,
        verify_status=VerifyStatus.TODO,
    )
    # 選択式: 正解が選択肢に無ければ空にする(作成者に選んでもらう)
    if q.type == AnswerFormat.CHOICE:
        choices = [c.strip() for c in q.choices if c.strip()]
        problem.choices = choices
        problem.correct_answer = q.answer.strip() if q.answer.strip() in choices else ""
    # 数値入力: 数値として読めなければ空にする
    elif q.type == AnswerFormat.NUMERIC:
        try:
            value = float(q.answer)
            problem.correct_answer = q.answer.strip() if math.isfinite(value) else ""
        except ValueError:
            problem.correct_answer = ""
    # コード: 演習と同じく AI の模範解答を ai_model_answer に入れる
    else:
        grading = q.grading if q.grading == Grading.OUTPUT or q.test_code.strip() else Grading.OUTPUT
        problem.starter_code = q.starter_code
        problem.ai_model_answer = q.model_answer
        problem.grading = grading
        problem.test_code = q.test_code if grading == Grading.TEST else ""
    return problem


def run_draft_job(job_id: int) -> None:
    """
    下書き生成ジョブを実行する(単元ごと・小テストの順に AI で作って保存する)

    バックグラウンドで実行するため、独自の DB セッションを使う。中身がまだ無い単元と、
    まだ無い小テストだけを作るため、中断・失敗したジョブを再開すると続きから作れる。
    一部の単元で失敗しても続け、失敗した内容はジョブの message に残す。

    Args
    -----------------
    - job_id: int,                      生成ジョブ ID

    """
    settings = get_settings()
    with new_session() as session:
        # ジョブを取得して実行中にする(待機中のジョブだけを実行する)
        job = session.get(AIJob, job_id)
        if job is None or job.status != JOB_QUEUED:
            return
        job.status = JOB_RUNNING
        job.message = ""
        session.commit()
        errors: list[str] = []
        try:
            course = session.scalar(
                select(Course)
                .where(Course.id == job.course_id)
                .options(
                    selectinload(Course.units).selectinload(Unit.cells).selectinload(Cell.problem),
                    selectinload(Course.datasets),
                )
            )
            if course is None:
                raise AdminInputError("講座が見つかりません")
            outline = CourseOutline.model_validate(job.request["outline"])
            datasets = [d.filename for d in course.datasets]
            units = list(course.units)
            # 作成済みの手順を数える(再開時は続きから)
            has_quiz = _has_quiz(session, course.id)
            job.done_steps = sum(1 for u in units if u.cells) + (1 if has_quiz else 0)
            session.commit()
            # 中身がまだ無い単元の下書きを作る
            for index, unit in enumerate(units):
                if unit.cells or index >= len(outline.units):
                    continue
                job.current_step = f"単元{index + 1}「{unit.title}」を作成中"
                session.commit()
                try:
                    system, user = unit_prompt(outline, index, course.level, datasets)
                    draft = generate(session, UnitDraft, system, user, settings.ai_model_draft, "unit", job.id, course.id)
                    if _save_unit_draft(session, unit, draft) == 0:
                        errors.append(f"単元{index + 1}: 演習が作られませんでした。エディタで追加してください。")
                    job.done_steps += 1
                except (AIOutputError, AIUnavailableError) as e:
                    session.rollback()
                    errors.append(f"単元{index + 1}: {e}")
                session.commit()
            # 小テストがまだ無ければ作る
            if not has_quiz:
                job.current_step = "小テストを作成中"
                session.commit()
                try:
                    system, user = quiz_prompt(outline, course.level, datasets)
                    quiz = generate(session, QuizDraft, system, user, settings.ai_model_draft, "quiz", job.id, course.id)
                    for position, q in enumerate(quiz.questions, start=1):
                        session.add(_question_problem(course, units, position, q))
                    job.done_steps += 1
                except (AIOutputError, AIUnavailableError) as e:
                    session.rollback()
                    errors.append(f"小テスト: {e}")
            # 完了(作れなかった手順が残っていれば失敗扱いにして、再開できるようにする)
            job.current_step = ""
            job.status = JOB_DONE if job.done_steps >= job.total_steps else JOB_FAILED
            job.message = "\n".join(errors)
            course.updated_at = datetime.now()
            session.commit()
        except Exception as e:
            # 想定外の失敗もジョブに記録する
            session.rollback()
            job = session.get(AIJob, job_id)
            job.status = JOB_FAILED
            job.current_step = ""
            job.message = "\n".join([*errors, f"下書きの作成に失敗しました: {e}"])
            session.commit()


def _has_quiz(session: Session, course_id: int) -> bool:
    """
    講座に小テストの問題があるかを返す

    Args
    -----------------
    - session: Session,                 DB セッション
    - course_id: int,                   講座 ID

    Returns
    -----------------
    - exists: bool,                     1問以上あれば True

    """
    # 小テストの問題を1件だけ探す
    found = session.scalar(
        select(Problem.id).where(Problem.course_id == course_id, Problem.kind == ProblemKind.QUIZ).limit(1)
    )
    return found is not None


def resume_job(session: Session, job_id: int) -> AIJob:
    """
    失敗・中断したジョブを再開できる状態にする(続きの実行は呼び出し側がバックグラウンドで始める)

    Args
    -----------------
    - session: Session,                 DB セッション
    - job_id: int,                      生成ジョブ ID

    Returns
    -----------------
    - job: AIJob,                       待機中に戻したジョブ

    """
    # 失敗・中断したジョブだけを再開できる
    job = get_job(session, job_id)
    if job.status != JOB_FAILED:
        raise AdminInputError("失敗・中断したジョブだけを再開できます")
    if job.course_id is None:
        raise AdminInputError("講座が削除されているため再開できません")
    # 待機中に戻す
    job.status = JOB_QUEUED
    job.message = ""
    session.flush()
    return job


def mark_interrupted_jobs() -> int:
    """
    実行中のまま残っているジョブを「中断」にする(アプリの起動時に呼ぶ)

    アプリが止まるとバックグラウンドの処理も止まるため、起動時点で実行中のジョブは続いていない。

    Returns
    -----------------
    - count: int,                       中断にしたジョブの数

    """
    with new_session() as session:
        # 実行中・待機中のジョブを失敗(中断)にする
        jobs = list(session.scalars(select(AIJob).where(AIJob.status.in_((JOB_QUEUED, JOB_RUNNING)))))
        for job in jobs:
            job.status = JOB_FAILED
            job.current_step = ""
            job.message = "アプリの再起動などで作成が中断されました。「続きから再開」で残りを作成できます。"
        session.commit()
        return len(jobs)


def get_job(session: Session, job_id: int) -> AIJob:
    """
    生成ジョブを返す

    Args
    -----------------
    - session: Session,                 DB セッション
    - job_id: int,                      生成ジョブ ID

    Returns
    -----------------
    - job: AIJob,                       ジョブ

    """
    # ジョブを取得(見つからなければエラー)
    job = session.get(AIJob, job_id)
    if job is None:
        raise NotFoundError(job_id)
    return job
