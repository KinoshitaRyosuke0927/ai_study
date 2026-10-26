"""AI による講座下書きの生成(構成案 → 下書き)を扱うモジュール。

流れ:
1. generate_outline: 題材から構成案を作る(DB には保存しない。画面で編集してもらう)
2. create_draft_job: 編集後の構成案から講座(下書き)と単元を作り、生成ジョブを登録する
3. run_draft_job: 単元ごと・小テストの順に AI で下書きを作って保存する(バックグラウンドで実行)

AI が作った問題はすべて「未検証」で保存する。コード問題は作成者の解答で、選択式・数値入力・表形式は
作成者の確認で検証済みにする(AI の出力をそのまま公開しない)。
選択式・数値入力・表形式の問題では、正解の根拠を計算するコード(check_code)を ai_model_answer に保存する。

講座のタイプ(概念理解型 / 実践型)・講座の目的・データファイルの要約は、ジョブの依頼内容(request)から取り出してプロンプトに渡す。

実行環境(Node.js + Pyodide、app/ai/executor.py)が使える場合は、AI が作った単元・小テストのコードを実行し、
その結果を AI に渡して説明の数値・正解・エラーを直させる(app/ai/verify.py)。図はこのときに描いた画像を講座の画像として保存する。
直しきれなかった問題点は、ジョブの message に「要確認」として残す。
"""

from __future__ import annotations

import base64
import json
import math
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.client import AIUnavailableError
from app.ai.generator import AIOutputError, generate
from app.ai.executor import CodeRunner, RunnerError, get_runner
from app.ai.prompts import outline_prompt, quiz_prompt, quiz_review_prompt, unit_prompt, unit_review_prompt
from app.ai.schemas import CourseOutline, GeneratedExercise, GeneratedQuestion, OutlineRequest, QuizDraft, UnitDraft
from app.ai.verify import Execution, run_quiz, run_unit, strip_stray_images
from app.common.constants import AnswerFormat, CellType, CourseStatus, Grading, ProblemKind, VerifyStatus
from app.config.settings import get_settings
from app.infra.db import new_session
from app.models import AIJob, Cell, Course, Problem, Unit, User
from app.services.admin_course_service import AdminInputError
from app.services.course_service import NotFoundError
from app.services.image_service import add_image

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


def _set_keyed_answer(problem: Problem, q: GeneratedExercise | GeneratedQuestion) -> None:
    """
    選択式・数値入力・表形式の問題に、選択肢・正解・正解の根拠のコードを設定する
    (正解が正しく設定できない場合は空にして、作成者に設定してもらう)

    Args
    -----------------
    - problem: Problem,                 設定する問題
    - q: GeneratedExercise | GeneratedQuestion,  AI が作った問題

    """
    choices = [c.strip() for c in q.choices if c.strip()]
    problem.choices = choices
    problem.ai_model_answer = q.check_code
    # 選択式: 正解が選択肢に無ければ空にする
    if q.type == AnswerFormat.CHOICE:
        problem.correct_answer = q.answer.strip() if q.answer.strip() in choices else ""
    # 数値入力: 数値として読めなければ空にする。許容誤差は AI の指定(無ければ既定値)
    elif q.type == AnswerFormat.NUMERIC:
        try:
            value = float(q.answer)
            problem.correct_answer = q.answer.strip() if math.isfinite(value) else ""
        except ValueError:
            problem.correct_answer = ""
        if q.tolerance > 0:
            problem.tolerance = q.tolerance
    # 表形式: 行ごとの正解を JSON 配列にする(選択肢にない値があれば空にする)
    elif q.type == AnswerFormat.MATRIX:
        rows = [r.strip() for r in q.matrix_rows if r.strip()]
        answers = [a.strip() for a in q.matrix_answers]
        problem.matrix_rows = rows
        valid = len(answers) == len(rows) and all(a in choices for a in answers)
        problem.correct_answer = json.dumps(answers, ensure_ascii=False) if valid else ""


def _save_figure(session: Session, course_id: int, filename: str, image_b64: str | None) -> str | None:
    """
    実行して描いた図を、講座の画像として保存する

    Args
    -----------------
    - session: Session,                 DB セッション
    - course_id: int,                   講座 ID
    - filename: str,                    画像のファイル名
    - image_b64: str | None,            図の画像(PNG, base64)。描けなかった場合は None

    Returns
    -----------------
    - filename: str | None,             保存したファイル名(保存できなければ None)

    """
    # 図が無ければ保存しない
    if not image_b64:
        return None
    # 画像として保存(同名は置き換え)して、ファイル名を返却
    add_image(session, course_id, filename, base64.b64decode(image_b64))
    return filename


def _with_figure(prompt: str, filename: str | None, alt: str) -> str:
    """
    問題文の末尾に、保存した図への参照を付ける

    Args
    -----------------
    - prompt: str,                      問題文
    - filename: str | None,             図のファイル名(無ければ付けない)
    - alt: str,                         図の説明

    Returns
    -----------------
    - prompt: str,                      図への参照を付けた問題文

    """
    # 図があれば、本文の後ろに Markdown の画像として付けて返却
    return f"{prompt}\n\n![{alt or '図'}](image:{filename})" if filename else prompt


def _save_unit_draft(session: Session, unit: Unit, draft: UnitDraft, execution: Execution | None = None) -> int:
    """
    単元の下書きをセル・演習として保存する(既存のセルは置き換える)

    Args
    -----------------
    - session: Session,                 DB セッション
    - unit: Unit,                       単元
    - draft: UnitDraft,                 AI が作った単元の下書き
    - execution: Execution | None,      下書きを実行した結果(図の画像に使う。実行していなければ None)

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
    position = 0
    # セルを順に保存(番号は実行結果のタスクの ID と合わせる)
    for index, c in enumerate(draft.cells, start=1):
        problem_id = None
        cell_type = c.type
        # 本文に直接書かれた画像の参照は表示できないので取り除く
        source = strip_stray_images(c.source) if c.type == "markdown" else c.source
        # 図: 描いた画像を保存し、画像を表示する説明セルにする(描けなかった図は載せない)
        if c.type == "figure":
            image = execution.image(f"cell{index}") if execution else None
            filename = _save_figure(session, unit.course_id, f"u{unit.position:02d}_fig{index}.png", image)
            if filename is None:
                continue
            cell_type = CellType.MARKDOWN
            source = f"![{c.alt or '図'}](image:{filename})"
        # 演習: 問題を作る(すべて未検証。作成者の解答は空にする)
        elif c.type == "exercise":
            if c.exercise is None:
                continue
            ex = c.exercise
            exercise_no += 1
            # 問題文の図
            image = execution.image(f"ex{exercise_no}.figure") if execution and ex.figure_code.strip() else None
            figure = _save_figure(session, unit.course_id, f"u{unit.position:02d}_ex{exercise_no}.png", image)
            problem = Problem(
                course_id=unit.course_id,
                unit_id=unit.id,
                kind=ProblemKind.EXERCISE,
                position=exercise_no,
                answer_format=ex.type,
                title=ex.title,
                prompt=_with_figure(strip_stray_images(ex.prompt), figure, ex.figure_alt),
                hint=strip_stray_images(ex.hint),
                explanation=strip_stray_images(ex.explanation),
                author_answer="",
                verify_status=VerifyStatus.TODO,
            )
            # コード: AI の模範解答は ai_model_answer に入れる
            if ex.type == AnswerFormat.CODE:
                grading = ex.grading if ex.grading == Grading.OUTPUT or ex.test_code.strip() else Grading.OUTPUT
                problem.starter_code = ex.starter_code
                problem.grading = grading
                problem.test_code = ex.test_code if grading == Grading.TEST else ""
                problem.ai_model_answer = ex.model_answer
            # 選択式・数値入力・表形式: 選択肢・正解・正解の根拠のコードを設定する
            else:
                _set_keyed_answer(problem, ex)
            session.add(problem)
            session.flush()
            problem_id = problem.id
            cell_type = CellType.EXERCISE
            source = ""
        # セルを保存(AI が作ったことを記録する)
        position += 1
        session.add(
            Cell(
                unit_id=unit.id,
                position=position,
                cell_type=cell_type,
                source=source,
                problem_id=problem_id,
                ai_generated=True,
            )
        )
    session.flush()
    # 保存した演習の数を返却
    return exercise_no


def _verify_and_fix(
    session: Session,
    runner: CodeRunner,
    draft: UnitDraft | QuizDraft,
    files: dict[str, bytes],
    req: OutlineRequest,
    job: AIJob,
) -> tuple[UnitDraft | QuizDraft, Execution | None, list[str]]:
    """
    下書きのコードを実行し、実行結果を AI に渡して直させる(最大 2 回)

    1回目は問題点が無くても、説明の数値と実行結果の食い違いを確かめるために必ず直させる。
    2回目は、直した後も問題点(エラー・図が描けない・正解の不一致など)が残る場合だけ行う。

    Args
    -----------------
    - session: Session,                 DB セッション
    - runner: CodeRunner,               実行環境
    - draft: UnitDraft | QuizDraft,     AI が作った下書き
    - files: dict[str, bytes],          講座のデータファイル
    - req: OutlineRequest,              元の生成依頼(講座のタイプ・データの要約)
    - job: AIJob,                       生成ジョブ

    Returns
    -----------------
    - draft: UnitDraft | QuizDraft,     直した下書き
    - execution: Execution | None,      最後の実行結果(実行できなければ None)
    - issues: list[str],                直しきれなかった問題点

    """
    settings = get_settings()
    is_unit = isinstance(draft, UnitDraft)
    run = run_unit if is_unit else run_quiz
    review = unit_review_prompt if is_unit else quiz_review_prompt
    # 下書きを実行する(実行環境の失敗は、検証できなかったことを問題点として返す)
    try:
        execution = run(runner, draft, files)
    except RunnerError as e:
        return draft, None, [f"コードを実行して確かめられませんでした: {e}"]
    for attempt in range(2):
        if attempt == 1 and not execution.issues:
            break
        # 実行結果を渡して直させる(形式の崩れなどで直せなければ、直す前の下書きを使う)
        system, user = review(draft.model_dump_json(), execution.report, execution.issues, req.course_type, req.data_summary)
        try:
            fixed = generate(session, type(draft), system, user, settings.ai_model_draft, "unit_review" if is_unit else "quiz_review", job.id, job.course_id)
            fixed_execution = run(runner, fixed, files)
        except (AIOutputError, RunnerError):
            break
        draft, execution = fixed, fixed_execution
    # 直した下書き・実行結果・残った問題点を返却
    return draft, execution, execution.issues


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
        prompt=strip_stray_images(q.prompt),
        explanation=strip_stray_images(q.explanation),
        related_unit_id=related,
        verify_status=VerifyStatus.TODO,
    )
    # 選択式・数値入力・表形式: 選択肢・正解・正解の根拠のコードを設定する(正解が不正なら空にする)
    if q.type in AnswerFormat.KEYED:
        _set_keyed_answer(problem, q)
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
    実行環境が使える場合は、作った下書きのコードを実行して AI に直させ、直しきれなかった問題点を「要確認」として残す。

    Args
    -----------------
    - job_id: int,                      生成ジョブ ID

    """
    settings = get_settings()
    runner = get_runner()
    with new_session() as session:
        # ジョブを取得して実行中にする(待機中のジョブだけを実行する)
        job = session.get(AIJob, job_id)
        if job is None or job.status != JOB_QUEUED:
            return
        job.status = JOB_RUNNING
        job.message = ""
        session.commit()
        errors: list[str] = []
        notes: list[str] = []  # 直しきれなかった問題点(作成者に確認してもらう)
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
            # 講座のタイプと目的(以前の版で登録されたジョブには無いため、既定値で補う)
            req = OutlineRequest.model_validate(job.request["request"])
            datasets = [d.filename for d in course.datasets]
            files = {d.filename: d.content for d in course.datasets}
            units = list(course.units)
            # 作成済みの手順を数える(再開時は続きから)
            has_quiz = _has_quiz(session, course.id)
            job.done_steps = sum(1 for u in units if u.cells) + (1 if has_quiz else 0)
            session.commit()
            # 作った演習のタイトル(後の単元で同じ題材を繰り返さないよう、プロンプトに渡す)
            previous: list[str] = []
            # 中身がまだ無い単元の下書きを作る
            for index, unit in enumerate(units):
                if unit.cells or index >= len(outline.units):
                    previous.extend(f"単元{index + 1}: {c.problem.title}" for c in unit.cells if c.problem is not None)
                    continue
                job.current_step = f"単元{index + 1}「{unit.title}」を作成中"
                session.commit()
                try:
                    system, user = unit_prompt(
                        outline, index, course.level, datasets, req.course_type, req.purpose, req.data_summary, previous
                    )
                    draft = generate(session, UnitDraft, system, user, settings.ai_model_draft, "unit", job.id, course.id)
                    # コードを実行して確かめ、AI に直させる
                    execution = None
                    if runner is not None:
                        job.current_step = f"単元{index + 1}「{unit.title}」のコードを実行して確認中"
                        session.commit()
                        draft, execution, issues = _verify_and_fix(session, runner, draft, files, req, job)
                        notes.extend(f"単元{index + 1}: 要確認: {i}" for i in issues)
                    previous.extend(f"単元{index + 1}: {c.exercise.title}" for c in draft.cells if c.exercise is not None)
                    if _save_unit_draft(session, unit, draft, execution) == 0:
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
                    system, user = quiz_prompt(outline, course.level, datasets, req.course_type, req.purpose, req.data_summary)
                    quiz = generate(session, QuizDraft, system, user, settings.ai_model_draft, "quiz", job.id, course.id)
                    # コードを実行して確かめ、AI に直させる
                    execution = None
                    if runner is not None:
                        job.current_step = "小テストのコードを実行して確認中"
                        session.commit()
                        quiz, execution, issues = _verify_and_fix(session, runner, quiz, files, req, job)
                        notes.extend(f"小テスト: 要確認: {i}" for i in issues)
                    for position, q in enumerate(quiz.questions, start=1):
                        problem = _question_problem(course, units, position, q)
                        # 問題文の図を保存して、問題文に付ける
                        image = execution.image(f"q{position}.figure") if execution and q.figure_code.strip() else None
                        figure = _save_figure(session, course.id, f"quiz_q{position}.png", image)
                        problem.prompt = _with_figure(problem.prompt, figure, q.figure_alt)
                        session.add(problem)
                    job.done_steps += 1
                except (AIOutputError, AIUnavailableError) as e:
                    session.rollback()
                    errors.append(f"小テスト: {e}")
            # 完了(作れなかった手順が残っていれば失敗扱いにして、再開できるようにする)
            job.current_step = ""
            job.status = JOB_DONE if job.done_steps >= job.total_steps else JOB_FAILED
            job.message = "\n".join([*errors, *notes])
            course.updated_at = datetime.now()
            session.commit()
        except Exception as e:
            # 想定外の失敗もジョブに記録する
            session.rollback()
            job = session.get(AIJob, job_id)
            job.status = JOB_FAILED
            job.current_step = ""
            job.message = "\n".join([*errors, *notes, f"下書きの作成に失敗しました: {e}"])
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
