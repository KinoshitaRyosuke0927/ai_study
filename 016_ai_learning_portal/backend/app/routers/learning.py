"""受講 API(講座一覧・講座詳細・単元・データファイル・画像・演習の提出)。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.ai.figure_style import MATPLOTLIBRC
from app.config.settings import get_settings
from app.infra.db import get_db
from app.models import User
from app.routers.deps import get_current_user
from app.schemas import (
    AnswerSubmitRequest,
    AppConfigOut,
    CodeSubmitRequest,
    CourseDetailOut,
    CourseSummaryOut,
    HomeOut,
    MyPageOut,
    QuizOut,
    QuizResultOut,
    QuizSubmitRequest,
    SubmitResultOut,
    UnitDetailOut,
)
from app.services import course_service, dashboard_service, image_service, quiz_service, submission_service
from app.services.course_service import NotFoundError
from app.services.quiz_service import QuizLockedError

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
    - config: AppConfigOut,             Pyodide の配信元、グラフの共通スタイルなど

    """
    # 設定から必要な項目だけを返却
    return AppConfigOut(pyodide_base_url=get_settings().pyodide_base_url, matplotlibrc=MATPLOTLIBRC)


@router.get("/courses", response_model=list[CourseSummaryOut])
def list_courses(
    user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")
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
    slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")
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
    unit_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")
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
    dataset_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")
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


@router.get("/courses/{slug}/images/{filename}")
def get_image(
    slug: str, filename: str, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")
) -> Response:
    """
    講座の画像を返す(説明・問題文の Markdown の image:ファイル名 から参照される)

    Args
    -----------------
    - slug: str,                        講座の識別名
    - filename: str,                    ファイル名
    - user: User,                       ログイン中のユーザ
    - db: Session,                      DB セッション

    Returns
    -----------------
    - response: Response,               画像

    """
    # 閲覧できる講座の画像を読み込む(見つからなければ 404)
    try:
        data, content_type = image_service.load_image(db, user, slug, filename)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "画像が見つかりません")
    # 画像として返却(形式の推測をさせない。短時間だけブラウザにキャッシュさせる)
    return Response(
        content=data,
        media_type=content_type,
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=300"},
    )


@router.post("/problems/{problem_id}/submit-code", response_model=SubmitResultOut)
def submit_code(
    problem_id: int,
    req: CodeSubmitRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db, scope="function"),
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


@router.post("/problems/{problem_id}/submit-answer", response_model=SubmitResultOut)
def submit_answer(
    problem_id: int,
    req: AnswerSubmitRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db, scope="function"),
) -> SubmitResultOut:
    """
    演習(選択式・数値入力・表形式の選択)の回答を提出して採点する

    Args
    -----------------
    - problem_id: int,                  問題 ID
    - req: AnswerSubmitRequest,         回答
    - user: User,                       ログイン中のユーザ
    - db: Session,                      DB セッション

    Returns
    -----------------
    - result: SubmitResultOut,          採点結果

    """
    # 採点して記録(見つからなければ 404)
    try:
        return submission_service.submit_answer(db, user, problem_id, req)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "問題が見つかりません")


@router.get("/courses/{slug}/quiz", response_model=QuizOut)
def get_quiz(
    slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")
) -> QuizOut:
    """
    小テストの表示内容を返す

    Args
    -----------------
    - slug: str,                        講座の識別名
    - user: User,                       ログイン中のユーザ
    - db: Session,                      DB セッション

    Returns
    -----------------
    - quiz: QuizOut,                    小テストの表示内容(未完了の単元があれば問題は含めない)

    """
    # 小テストを取得(講座が見つからなければ 404)
    try:
        return quiz_service.get_quiz(db, user, slug)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "講座が見つかりません")


@router.post("/courses/{slug}/quiz/attempts", response_model=QuizResultOut)
def submit_quiz(
    slug: str,
    req: QuizSubmitRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db, scope="function"),
) -> QuizResultOut:
    """
    小テストを提出して採点する

    Args
    -----------------
    - slug: str,                        講座の識別名
    - req: QuizSubmitRequest,           回答(コード問題はブラウザで実行した結果を含む)
    - user: User,                       ログイン中のユーザ
    - db: Session,                      DB セッション

    Returns
    -----------------
    - result: QuizResultOut,            採点結果

    """
    # 採点して記録(未完了の単元があれば 403、講座が見つからなければ 404)
    try:
        return quiz_service.submit_quiz(db, user, slug, req)
    except QuizLockedError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "すべての単元を完了すると小テストを受けられます")
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "講座が見つかりません")


@router.get("/home", response_model=HomeOut)
def home(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")) -> HomeOut:
    """
    ホーム画面の表示内容を返す

    Args
    -----------------
    - user: User,                       ログイン中のユーザ
    - db: Session,                      DB セッション

    Returns
    -----------------
    - home: HomeOut,                    ホーム画面の表示内容

    """
    # ホーム画面の表示内容を返却
    return dashboard_service.get_home(db, user)


@router.get("/me/summary", response_model=MyPageOut)
def my_page(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")) -> MyPageOut:
    """
    マイページの表示内容を返す(ログイン中のユーザ本人の分のみ)

    Args
    -----------------
    - user: User,                       ログイン中のユーザ
    - db: Session,                      DB セッション

    Returns
    -----------------
    - page: MyPageOut,                  マイページの表示内容

    """
    # マイページの表示内容を返却
    return dashboard_service.get_my_page(db, user)
