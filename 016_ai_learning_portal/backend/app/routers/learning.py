"""受講 API(講座一覧・講座詳細・単元・データファイル・演習の提出)。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.infra.db import get_db
from app.models import User
from app.routers.deps import get_current_user
from app.schemas import (
    AppConfigOut,
    CodeSubmitRequest,
    CourseDetailOut,
    CourseSummaryOut,
    SubmitResultOut,
    UnitDetailOut,
)
from app.services import course_service, submission_service
from app.services.course_service import NotFoundError

router = APIRouter(prefix="/api", tags=["learning"])


@router.get("/config", response_model=AppConfigOut)
def app_config(user: User = Depends(get_current_user)) -> AppConfigOut:
    """
    フロントエンドの実行時設定を返す

    Args
    -----------------
    - user: User,                       ログイン中のユーザ

    Returns
    -----------------
    - config: AppConfigOut,             Pyodide の配信元など

    """
    # 設定から必要な項目だけを返却
    return AppConfigOut(pyodide_base_url=get_settings().pyodide_base_url)


@router.get("/courses", response_model=list[CourseSummaryOut])
def list_courses(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[CourseSummaryOut]:
    """
    講座一覧を返す

    Args
    -----------------
    - user: User,                       ログイン中のユーザ
    - db: Session,                      DB セッション

    Returns
    -----------------
    - courses: list[CourseSummaryOut],  講座の要約一覧

    """
    # 閲覧できる講座の一覧を返却
    return course_service.list_courses(db, user)


@router.get("/courses/{slug}", response_model=CourseDetailOut)
def get_course(
    slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> CourseDetailOut:
    """
    講座詳細を返す

    Args
    -----------------
    - slug: str,                        講座の識別名
    - user: User,                       ログイン中のユーザ
    - db: Session,                      DB セッション

    Returns
    -----------------
    - course: CourseDetailOut,          講座詳細

    """
    # 講座詳細を取得(見つからなければ 404)
    try:
        return course_service.get_course(db, user, slug)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "講座が見つかりません")


@router.get("/units/{unit_id}", response_model=UnitDetailOut)
def get_unit(
    unit_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> UnitDetailOut:
    """
    単元の表示内容を返す

    Args
    -----------------
    - unit_id: int,                     単元 ID
    - user: User,                       ログイン中のユーザ
    - db: Session,                      DB セッション

    Returns
    -----------------
    - unit: UnitDetailOut,              単元の表示内容

    """
    # 単元を取得(見つからなければ 404)
    try:
        return course_service.get_unit(db, user, unit_id)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "単元が見つかりません")


@router.get("/datasets/{dataset_id}")
def get_dataset(
    dataset_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Response:
    """
    データファイルを返す(ブラウザの Python 実行環境に配置するため)

    Args
    -----------------
    - dataset_id: int,                  データファイル ID
    - user: User,                       ログイン中のユーザ
    - db: Session,                      DB セッション

    Returns
    -----------------
    - response: Response,               ファイル本体

    """
    # データファイルを取得(見つからなければ 404)
    try:
        dataset = course_service.get_dataset(db, user, dataset_id)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "データファイルが見つかりません")
    # ファイル本体を返却
    return Response(content=dataset.content, media_type=dataset.content_type)


@router.post("/problems/{problem_id}/submit-code", response_model=SubmitResultOut)
def submit_code(
    problem_id: int,
    req: CodeSubmitRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SubmitResultOut:
    """
    コード問題を提出して採点する

    Args
    -----------------
    - problem_id: int,                  問題 ID
    - req: CodeSubmitRequest,           提出内容(ブラウザで実行した結果を含む)
    - user: User,                       ログイン中のユーザ
    - db: Session,                      DB セッション

    Returns
    -----------------
    - result: SubmitResultOut,          採点結果

    """
    # 採点して記録(見つからなければ 404)
    try:
        return submission_service.submit_code(db, user, problem_id, req)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "問題が見つかりません")
