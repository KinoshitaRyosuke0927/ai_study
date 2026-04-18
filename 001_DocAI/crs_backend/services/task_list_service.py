from database import db_access_service
from models import TaskListResponse


def get_task_list(user_id: int) -> TaskListResponse:
    """
    user_idに紐づくタスク情報の一覧を取得する

    Args
    -----------------
    - user_id: int,                     ユーザID

    Returns
    -----------------
    - response: TaskListResponse,       レスポンス

    """
    # DBからユーザIDに紐づくタスク情報を取得
    df = db_access_service.select_task_by_user_id(user_id)
    # 取得したタスク情報を辞書形式に変換
    task_dict_list = df.to_dict(orient="records")
    # レスポンス返却
    return TaskListResponse(status=200, messages=[], task_list=task_dict_list)
