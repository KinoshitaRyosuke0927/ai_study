import json

from common import common_validate
from common.constant import OperationType
from fastapi import BackgroundTasks, FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from models import *
from services import login_service, task_detail_service, task_list_service

app = FastAPI()

# サーバへのアクセスを許可するオリジンを設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/login", response_model=LoginResponse)
def login(request: LoginRequest):
    """
    ログイン画面の処理を行う
    """
    # ログイン状況を返却
    return login_service.login(request.mail_address, request.password)


@app.post("/task-list", response_model=TaskListResponse)
def task_list(request: TaskListRequest):
    """
    タスク一覧画面の処理を行う
    """
    # タスクの一覧を取得
    return task_list_service.get_task_list(request.user_id)


@app.post("/task-detail/{operation_mode}", response_model=TaskDetailResponse)
def task_detail(operation_mode: str, request: TaskDetailRequest):
    """
    ファイル変換以外のタスク詳細画面の処理を行う
    """
    ## タスク詳細画面の操作モードごとに処理振り分け
    match operation_mode:
        # 新規作成
        case OperationType.CREATE.value:
            # タスク新規作成処理
            return task_detail_service.create_new_task(request.task_name, request.user_id)
        # 状態取得
        case OperationType.INQUIRY.value:
            # タスク状態取得処理
            return task_detail_service.get_task_info(request.task_id)
        # 情報取得
        case OperationType.READ.value:
            # 翻訳結果ファイル取得処理
            return task_detail_service.get_task_detail(request.task_id)
        # 名称更新
        case OperationType.UPDATE.value:
            # タスク名称変更処理
            return task_detail_service.update_task_name(request.task_id, request.task_name)
        # 削除
        case OperationType.DELETE.value:
            # タスク削除処理
            return task_detail_service.delete_task(request.task_id)


@app.post("/task-detail-translate", response_model=TaskDetailResponse)
async def task_detail_translate(
    background_tasks: BackgroundTasks,
    task_id: int=Form(...),
    user_id: int=Form(...),
    metadata: str=Form(...),
    target_file_list: list[UploadFile]=File(...)
):
    """
    ファイル変換処理を行う
    ※ ファイル変換時のAPIリクエストにはファイルの中身が含まれていてJSON形式で送信できないので分離する
    """
    # アップロードされたファイルの情報を辞書形式の配列に変換
    metadata_list = json.loads(metadata)
    # ファイル変換処理
    return task_detail_service.translate_files(target_file_list, metadata_list, task_id, user_id, background_tasks)


@app.post("/file-filter", response_model=FileFilterResponse)
def file_filter(request: FileFilterRequest):
    """
    登録されたファイルが変換対象として適切なファイルなのかを判定して返却する
    """
    # 変換対象のファイルチェック処理
    filter_result = common_validate.filter_data(request.target_data)
    # レスポンス返却
    return FileFilterResponse(status=200, filter_result=filter_result)
