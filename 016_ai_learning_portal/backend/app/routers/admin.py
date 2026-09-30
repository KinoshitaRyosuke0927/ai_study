"""管理者向け API(講座の作成・編集・検証・公開、メンバーの受講状況と管理)。

すべての API で管理者権限を確認する(require_admin)。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.ai.client import AIUnavailableError, ai_available
from app.ai.generator import AIOutputError
from app.ai.schemas import CourseOutline, OutlineRequest
from app.config.settings import get_settings

from app.infra.db import get_db
from app.models import User
from app.routers.deps import require_admin
from app.schemas import MyPageOut
from app.schemas_admin import (
    AcceptAuthorIn,
    AIJobOut,
    AIStatusOut,
    DraftCreateIn,
    AdminCourseRowOut,
    CourseEditorOut,
    CourseInfoIn,
    ProblemOut,
    ProgressMatrixOut,
    PublishCheckOut,
    PublishIn,
    QuizContentIn,
    ReorderIn,
    UnitAdminOut,
    UnitContentIn,
    UnitInfoIn,
    UserAdminOut,
    UserCreateIn,
    UserUpdateIn,
    VerifyIn,
    VerifyOut,
)
from app.services import admin_course_service as courses
from app.services import admin_member_service as members
from app.services import ai_course_service as ai_courses
from app.services.admin_course_service import MAX_DATASET_BYTES, MAX_IMPORT_BYTES, AdminInputError
from app.services.course_service import NotFoundError

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])

T = TypeVar("T")


def _call(fn: Callable[[], T]) -> T:
    """
    サービスを呼び出し、業務エラーを HTTP エラーに変換する

    Args
    -----------------
    - fn: Callable[[], T],              呼び出す処理

    Returns
    -----------------
    - result: T,                        処理の戻り値

    """
    try:
        return fn()
    # AI を使えない・AI の応答が不正(画面に理由を表示する)
    except AIUnavailableError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    except AIOutputError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI の応答を読み取れませんでした。もう一度お試しください。({e})")
    # 対象が見つからない
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "対象が見つかりません")
    # 入力内容の誤り(メッセージを画面に表示する)
    except AdminInputError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


# ---------- 講座 ----------
@router.get("/courses", response_model=list[AdminCourseRowOut])
def list_courses(db: Session = Depends(get_db)) -> list[AdminCourseRowOut]:
    """
    講座管理の一覧(下書きを含む)を返す

    Args
    -----------------
    - db: Session,                      DB セッション

    Returns
    -----------------
    - rows: list[AdminCourseRowOut],    講座の一覧

    """
    # 一覧を返却
    return courses.list_courses(db)


@router.post("/courses", response_model=CourseEditorOut)
def create_course(
    info: CourseInfoIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> CourseEditorOut:
    """
    下書きの講座を作成し、エディタの表示内容を返す

    Args
    -----------------
    - info: CourseInfoIn,               講座情報
    - admin: User,                      ログイン中の管理者
    - db: Session,                      DB セッション

    Returns
    -----------------
    - editor: CourseEditorOut,          作成した講座のエディタ表示内容

    """
    # 講座を作成し、エディタの表示内容を返却
    course = _call(lambda: courses.create_course(db, admin, info))
    return courses.get_editor(db, course.id)


@router.get("/courses/{course_id}", response_model=CourseEditorOut)
def get_editor(course_id: int, db: Session = Depends(get_db)) -> CourseEditorOut:
    """
    講座エディタの表示内容を返す

    Args
    -----------------
    - course_id: int,                   講座 ID
    - db: Session,                      DB セッション

    Returns
    -----------------
    - editor: CourseEditorOut,          講座エディタの表示内容

    """
    # エディタの表示内容を返却(見つからなければ 404)
    return _call(lambda: courses.get_editor(db, course_id))


@router.put("/courses/{course_id}", response_model=CourseEditorOut)
def update_info(course_id: int, info: CourseInfoIn, db: Session = Depends(get_db)) -> CourseEditorOut:
    """
    講座情報を更新する

    Args
    -----------------
    - course_id: int,                   講座 ID
    - info: CourseInfoIn,               講座情報
    - db: Session,                      DB セッション

    Returns
    -----------------
    - editor: CourseEditorOut,          更新後の講座エディタ表示内容

    """
    # 講座情報を更新し、エディタの表示内容を返却
    _call(lambda: courses.update_info(db, course_id, info))
    return courses.get_editor(db, course_id)


@router.delete("/courses/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course(course_id: int, db: Session = Depends(get_db)) -> None:
    """
    講座を削除する(受講記録も削除される)

    Args
    -----------------
    - course_id: int,                   講座 ID
    - db: Session,                      DB セッション

    """
    # 講座を削除
    _call(lambda: courses.delete_course(db, course_id))


@router.post("/courses/{course_id}/units", response_model=UnitAdminOut)
def add_unit(course_id: int, info: UnitInfoIn, db: Session = Depends(get_db)) -> UnitAdminOut:
    """
    単元を末尾に追加する

    Args
    -----------------
    - course_id: int,                   講座 ID
    - info: UnitInfoIn,                 単元の基本情報
    - db: Session,                      DB セッション

    Returns
    -----------------
    - unit: UnitAdminOut,               追加した単元

    """
    # 単元を追加して返却
    return _call(lambda: courses.add_unit(db, course_id, info))


@router.put("/courses/{course_id}/units/order", status_code=status.HTTP_204_NO_CONTENT)
def reorder_units(course_id: int, req: ReorderIn, db: Session = Depends(get_db)) -> None:
    """
    単元の並び順を変更する

    Args
    -----------------
    - course_id: int,                   講座 ID
    - req: ReorderIn,                   新しい並び順
    - db: Session,                      DB セッション

    """
    # 並び順を変更
    _call(lambda: courses.reorder_units(db, course_id, req.unit_ids))


@router.put("/units/{unit_id}", response_model=UnitAdminOut)
def save_unit(unit_id: int, req: UnitContentIn, db: Session = Depends(get_db)) -> UnitAdminOut:
    """
    単元(基本情報とセル一式)を保存する

    Args
    -----------------
    - unit_id: int,                     単元 ID
    - req: UnitContentIn,               単元の内容(基本情報とセル一式)
    - db: Session,                      DB セッション

    Returns
    -----------------
    - unit: UnitAdminOut,               保存後の単元

    """
    # 単元を保存して返却
    return _call(lambda: courses.save_unit(db, unit_id, req))


@router.delete("/units/{unit_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_unit(unit_id: int, db: Session = Depends(get_db)) -> None:
    """
    単元を削除する

    Args
    -----------------
    - unit_id: int,                     単元 ID
    - db: Session,                      DB セッション

    """
    # 単元を削除
    _call(lambda: courses.delete_unit(db, unit_id))


@router.put("/courses/{course_id}/quiz", response_model=list[ProblemOut])
def save_quiz(course_id: int, req: QuizContentIn, db: Session = Depends(get_db)) -> list[ProblemOut]:
    """
    小テストの問題一式を保存する

    Args
    -----------------
    - course_id: int,                   講座 ID
    - req: QuizContentIn,               小テストの問題一式
    - db: Session,                      DB セッション

    Returns
    -----------------
    - quiz: list[ProblemOut],           保存後の小テストの問題

    """
    # 小テストを保存して返却
    return _call(lambda: courses.save_quiz(db, course_id, req))


@router.post("/problems/{problem_id}/verify", response_model=VerifyOut)
def verify(problem_id: int, req: VerifyIn, db: Session = Depends(get_db)) -> VerifyOut:
    """
    ブラウザで実行した結果からコード問題を検証する

    Args
    -----------------
    - problem_id: int,                  問題 ID
    - req: VerifyIn,                    ブラウザで実行した結果
    - db: Session,                      DB セッション

    Returns
    -----------------
    - result: VerifyOut,                検証結果

    """
    # 検証して結果を返却
    return _call(lambda: courses.verify(db, problem_id, req))


@router.post("/problems/{problem_id}/accept-author", response_model=VerifyOut)
def accept_author(problem_id: int, req: AcceptAuthorIn, db: Session = Depends(get_db)) -> VerifyOut:
    """
    AI の想定と不一致の問題を、作成者の解答を正として検証済みにする

    Args
    -----------------
    - problem_id: int,                  問題 ID
    - req: AcceptAuthorIn,              作成者の解答の出力
    - db: Session,                      DB セッション

    Returns
    -----------------
    - result: VerifyOut,                検証結果

    """
    # 作成者の解答を正として結果を返却
    return _call(lambda: courses.accept_author(db, problem_id, req.output))


@router.get("/courses/{course_id}/publish-check", response_model=PublishCheckOut)
def publish_check(course_id: int, db: Session = Depends(get_db)) -> PublishCheckOut:
    """
    公開前チェックを行う

    Args
    -----------------
    - course_id: int,                   講座 ID
    - db: Session,                      DB セッション

    Returns
    -----------------
    - check: PublishCheckOut,           公開前チェックの結果

    """
    # チェック結果を返却
    return _call(lambda: courses.publish_check(db, course_id))


@router.post("/courses/{course_id}/publish", response_model=PublishCheckOut)
def publish(course_id: int, req: PublishIn, db: Session = Depends(get_db)) -> PublishCheckOut:
    """
    講座を公開する

    Args
    -----------------
    - course_id: int,                   講座 ID
    - req: PublishIn,                   例題の実行チェック結果
    - db: Session,                      DB セッション

    Returns
    -----------------
    - check: PublishCheckOut,           公開後のチェック結果

    """
    # 公開して、チェック結果を返却
    _call(lambda: courses.publish(db, course_id, req.examples_ok))
    return courses.publish_check(db, course_id)


@router.post("/courses/{course_id}/unpublish", response_model=PublishCheckOut)
def unpublish(course_id: int, db: Session = Depends(get_db)) -> PublishCheckOut:
    """
    講座を下書きに戻す

    Args
    -----------------
    - course_id: int,                   講座 ID
    - db: Session,                      DB セッション

    Returns
    -----------------
    - check: PublishCheckOut,           下書きに戻した後のチェック結果

    """
    # 下書きに戻して、チェック結果を返却
    _call(lambda: courses.unpublish(db, course_id))
    return courses.publish_check(db, course_id)


@router.post("/courses/{course_id}/datasets", response_model=CourseEditorOut)
async def upload_dataset(
    course_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)
) -> CourseEditorOut:
    """
    データファイルをアップロードする(同名は置き換え)

    Args
    -----------------
    - course_id: int,                   講座 ID
    - file: UploadFile,                 アップロードされたファイル
    - db: Session,                      DB セッション

    Returns
    -----------------
    - editor: CourseEditorOut,          更新後の講座エディタ表示内容

    """
    # 上限を少し超えるところまで読み、サイズ超過を検出する
    data = await file.read(MAX_DATASET_BYTES + 1)
    _call(lambda: courses.add_dataset(db, course_id, file.filename or "", file.content_type or "", data))
    return courses.get_editor(db, course_id)


@router.delete("/datasets/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dataset(dataset_id: int, db: Session = Depends(get_db)) -> None:
    """
    データファイルを削除する

    Args
    -----------------
    - dataset_id: int,                  データファイル ID
    - db: Session,                      DB セッション

    """
    # データファイルを削除
    _call(lambda: courses.delete_dataset(db, dataset_id))


# ---------- メンバー ----------
@router.get("/progress", response_model=ProgressMatrixOut)
def progress(db: Session = Depends(get_db)) -> ProgressMatrixOut:
    """
    メンバー × 講座の受講状況を返す

    Args
    -----------------
    - db: Session,                      DB セッション

    Returns
    -----------------
    - matrix: ProgressMatrixOut,        メンバー × 講座の受講状況

    """
    # 受講状況を返却
    return members.progress_matrix(db)


@router.get("/members/{user_id}", response_model=MyPageOut)
def member_detail(user_id: int, db: Session = Depends(get_db)) -> MyPageOut:
    """
    メンバー1人の受講状況を返す

    Args
    -----------------
    - user_id: int,                     対象のユーザ ID
    - db: Session,                      DB セッション

    Returns
    -----------------
    - page: MyPageOut,                  メンバーの受講状況

    """
    # メンバーの受講状況を返却(見つからなければ 404)
    return _call(lambda: members.member_detail(db, user_id))


@router.get("/users", response_model=list[UserAdminOut])
def list_users(db: Session = Depends(get_db)) -> list[UserAdminOut]:
    """
    メンバーの一覧を返す

    Args
    -----------------
    - db: Session,                      DB セッション

    Returns
    -----------------
    - users: list[UserAdminOut],        メンバー一覧

    """
    # メンバー一覧を返却
    return members.list_users(db)


@router.post("/users", response_model=UserAdminOut)
def add_user(req: UserCreateIn, db: Session = Depends(get_db)) -> UserAdminOut:
    """
    メンバーを追加する

    Args
    -----------------
    - req: UserCreateIn,                追加するメンバー
    - db: Session,                      DB セッション

    Returns
    -----------------
    - user: UserAdminOut,               追加したメンバー

    """
    # メンバーを追加して返却
    return _call(lambda: members.add_user(db, req))


@router.put("/users/{user_id}", response_model=UserAdminOut)
def update_user(
    user_id: int, req: UserUpdateIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> UserAdminOut:
    """
    メンバーを更新する

    Args
    -----------------
    - user_id: int,                     対象のユーザ ID
    - req: UserUpdateIn,                更新内容
    - admin: User,                      ログイン中の管理者
    - db: Session,                      DB セッション

    Returns
    -----------------
    - user: UserAdminOut,               更新後のメンバー

    """
    # メンバーを更新して返却
    return _call(lambda: members.update_user(db, admin, user_id, req))


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> None:
    """
    メンバーを削除する(受講記録も削除される)

    Args
    -----------------
    - user_id: int,                     対象のユーザ ID
    - admin: User,                      ログイン中の管理者
    - db: Session,                      DB セッション

    """
    # メンバーを削除
    _call(lambda: members.delete_user(db, admin, user_id))



# ---------- 作成者の確認(選択式・数値入力) ----------
@router.post("/problems/{problem_id}/confirm", response_model=VerifyOut)
def confirm_problem(problem_id: int, db: Session = Depends(get_db)) -> VerifyOut:
    """
    選択式・数値入力の問題を、作成者が内容を確認したものとして検証済みにする

    Args
    -----------------
    - problem_id: int,                  問題 ID
    - db: Session,                      DB セッション

    Returns
    -----------------
    - result: VerifyOut,                検証結果

    """
    # 確認済みにして結果を返却
    return _call(lambda: courses.confirm_problem(db, problem_id))


# ---------- .ipynb の取り込み ----------
@router.post("/import/course", response_model=CourseEditorOut)
async def import_course_zip(
    file: UploadFile = File(...),
    replace: bool = Form(False),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CourseEditorOut:
    """
    講座フォルダの zip(course.json + .ipynb + data/)を取り込み、下書きの講座として登録する

    Args
    -----------------
    - file: UploadFile,                 講座フォルダの zip
    - replace: bool,                    同じ識別名の講座を置き換えるなら True(受講記録も削除される)
    - admin: User,                      ログイン中の管理者
    - db: Session,                      DB セッション

    Returns
    -----------------
    - editor: CourseEditorOut,          取り込んだ講座のエディタ表示内容

    """
    # 上限を少し超えるところまで読み、サイズ超過を検出する
    data = await file.read(MAX_IMPORT_BYTES + 1)
    # 取り込んでエディタの表示内容を返却
    course = _call(lambda: courses.import_course_zip(db, admin, data, replace))
    return courses.get_editor(db, course.id)


@router.post("/courses/{course_id}/import-unit", response_model=UnitAdminOut)
async def import_unit(course_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)) -> UnitAdminOut:
    """
    .ipynb を1つ取り込み、講座の末尾に単元として追加する

    Args
    -----------------
    - course_id: int,                   講座 ID
    - file: UploadFile,                 単元の .ipynb
    - db: Session,                      DB セッション

    Returns
    -----------------
    - unit: UnitAdminOut,               追加した単元

    """
    # 上限を少し超えるところまで読み、サイズ超過を検出する
    data = await file.read(MAX_IMPORT_BYTES + 1)
    # 取り込んで単元を返却
    return _call(lambda: courses.import_unit_notebook(db, course_id, file.filename or "", data))


# ---------- AI による講座作成 ----------
@router.get("/ai/status", response_model=AIStatusOut)
def ai_status() -> AIStatusOut:
    """
    AI を使えるかどうかと、使うモデルを返す

    Returns
    -----------------
    - status: AIStatusOut,              AI の利用可否

    """
    # 設定から利用可否とモデル名を返却
    settings = get_settings()
    return AIStatusOut(enabled=ai_available(), model_outline=settings.ai_model_outline, model_draft=settings.ai_model_draft)


@router.post("/ai/outline", response_model=CourseOutline)
def ai_outline(req: OutlineRequest, db: Session = Depends(get_db)) -> CourseOutline:
    """
    題材から講座の構成案を作る(保存はしない。画面で編集してから下書きを作る)

    Args
    -----------------
    - req: OutlineRequest,              構成案の生成依頼
    - db: Session,                      DB セッション(AI 呼び出しの記録に使う)

    Returns
    -----------------
    - outline: CourseOutline,           構成案

    """
    # AI で構成案を作って返却
    return _call(lambda: ai_courses.generate_outline(db, req))


@router.post("/ai/drafts", response_model=AIJobOut)
def ai_create_draft(
    req: DraftCreateIn,
    background: BackgroundTasks,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AIJobOut:
    """
    構成案から講座(下書き)を作り、単元・小テストの下書き生成をバックグラウンドで始める

    Args
    -----------------
    - req: DraftCreateIn,               識別名・元の依頼・編集した構成案
    - background: BackgroundTasks,      バックグラウンド処理
    - admin: User,                      ログイン中の管理者
    - db: Session,                      DB セッション

    Returns
    -----------------
    - job: AIJobOut,                    登録したジョブ

    """
    # 入力の形式を確認
    try:
        request = OutlineRequest.model_validate(req.request)
        outline = CourseOutline.model_validate(req.outline)
    except ValidationError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"構成案の内容を確認してください: {e.error_count()} 件の誤り")
    # 講座・単元・ジョブを登録して確定(バックグラウンド処理から読めるようにする)
    job = _call(lambda: ai_courses.create_draft_job(db, admin, req.slug, request, outline))
    db.commit()
    # 応答を返した後に下書きの生成を始める
    background.add_task(ai_courses.run_draft_job, job.id)
    return _job_out(job)


@router.get("/ai/jobs/{job_id}", response_model=AIJobOut)
def ai_job(job_id: int, db: Session = Depends(get_db)) -> AIJobOut:
    """
    下書き生成ジョブの状態を返す(画面から数秒ごとに問い合わせる)

    Args
    -----------------
    - job_id: int,                      ジョブ ID
    - db: Session,                      DB セッション

    Returns
    -----------------
    - job: AIJobOut,                    ジョブの状態

    """
    # ジョブを取得して返却
    return _job_out(_call(lambda: ai_courses.get_job(db, job_id)))


@router.post("/ai/jobs/{job_id}/resume", response_model=AIJobOut)
def ai_resume_job(job_id: int, background: BackgroundTasks, db: Session = Depends(get_db)) -> AIJobOut:
    """
    失敗・中断したジョブを続きから再開する(中身がまだ無い単元と小テストだけを作る)

    Args
    -----------------
    - job_id: int,                      ジョブ ID
    - background: BackgroundTasks,      バックグラウンド処理
    - db: Session,                      DB セッション

    Returns
    -----------------
    - job: AIJobOut,                    待機中に戻したジョブ

    """
    # 待機中に戻して確定し、応答を返した後に続きの作成を始める
    job = _call(lambda: ai_courses.resume_job(db, job_id))
    db.commit()
    background.add_task(ai_courses.run_draft_job, job.id)
    return _job_out(job)


def _job_out(job) -> AIJobOut:
    """
    ジョブを出力形式に変換する

    Args
    -----------------
    - job: AIJob,                       ジョブ

    Returns
    -----------------
    - out: AIJobOut,                    出力形式

    """
    # 画面に必要な項目だけを返却
    return AIJobOut(
        id=job.id,
        course_id=job.course_id,
        status=job.status,
        total_steps=job.total_steps,
        done_steps=job.done_steps,
        current_step=job.current_step,
        message=job.message,
    )
