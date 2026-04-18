from typing import Optional

from pydantic import BaseModel


# ログインリクエスト
class LoginRequest(BaseModel):
    mail_address: str
    password: str

# ログインレスポンス
# ※ログインに失敗した場合にも返却するためuser_id, user_nameは指定せずに返却できるようにしている
class LoginResponse(BaseModel):
    status: int
    messages: list[dict[str, str]]
    user_id: Optional[int]=None
    user_name: Optional[str]=""

# タスク一覧リクエスト
class TaskListRequest(BaseModel):
    user_id: int

# タスク一覧レスポンス
class TaskListResponse(BaseModel):
    status: int
    messages: list[dict[str, str]]
    task_list: list[dict[str, object]]

# タスク詳細リクエスト
# ※タスク詳細画面はモードによって送信する情報が異なるため, すべての項目を指定せずに送信できるようにしている
class TaskDetailRequest(BaseModel):
    task_name: Optional[str]=None
    task_id: Optional[int]=None
    user_id: Optional[int]=None

# タスク詳細レスポンス
# ※タスク詳細画面はモードによって返却する情報が異なるため, すべての項目を指定せずに返却できるようにしている
class TaskDetailResponse(BaseModel):
    status: int
    messages: list[dict[str, str]]
    task_detail: dict[str, object]
    # metadata: Optional[list]=[]
    display_object_info: Optional[list[dict]]=[]

# 変換対象ファイル形式フィルターリクエスト
class FileFilterRequest(BaseModel):
    target_data: list

# 変換対象ファイル形式フィルターレスポンス
class FileFilterResponse(BaseModel):
    status: int
    filter_result: list[bool]

# 変換処理実行時に連携されるオブジェクトの形式
# ※実際のMetadataは画面からは辞書形式で送信されてくるためこのモデルは使用しないが, Metadataの辞書の形式確認のために記述している
class Metadata(BaseModel):
    upload_object_name: str
    upload_object_type: str
    full_path: str
    file_size: int
