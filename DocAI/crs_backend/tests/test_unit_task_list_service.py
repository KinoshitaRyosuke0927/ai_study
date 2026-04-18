from datetime import datetime
from unittest.mock import patch

import pandas as pd

from models import TaskListResponse
from services import task_list_service

# テストデータ
task_df = pd.DataFrame(
    data={
        "task_id": range(1, 6),
        "task_name": ["task_001", "task_002", "task_003", "task_004", "task_005"],
        "task_state_id": [1, 2, 3, 4, 1],
        "update_at": [datetime(2025, 12, 24, 12, 34, 56, 789)] * 5,
        "user_id": [1] * 5,
    },
    index=range(1, 6),
).astype({"task_id": int, "task_name": str, "task_state_id": int, "user_id": int})


# 正常系
# タスク情報が存在しない場合に正常に処理されること
@patch("database.db_access_service.select_task_by_user_id", return_value=pd.DataFrame())
def test_get_task_list_OK_01(mock):
    ## テストデータ用意
    # ユーザID
    user_id = 1

    ## 期待値
    expected_res = TaskListResponse(status=200, messages=[], task_list=[])

    ## テスト処理
    result_res = task_list_service.get_task_list(user_id)

    assert expected_res == result_res


# 正常系
# タスク情報が存在する場合に正常に処理されること
@patch("database.db_access_service.select_task_by_user_id", return_value=task_df)
def test_get_task_list_OK_02(mock):
    ## テストデータ用意
    # ユーザID
    user_id = 1

    ## 期待値
    expected_task_list = [
        {
            "task_id": 1,
            "task_name": "task_001",
            "task_state_id": 1,
            "update_at": datetime(2025, 12, 24, 12, 34, 56, 789),
            "user_id": 1,
        },
        {
            "task_id": 2,
            "task_name": "task_002",
            "task_state_id": 2,
            "update_at": datetime(2025, 12, 24, 12, 34, 56, 789),
            "user_id": 1,
        },
        {
            "task_id": 3,
            "task_name": "task_003",
            "task_state_id": 3,
            "update_at": datetime(2025, 12, 24, 12, 34, 56, 789),
            "user_id": 1,
        },
        {
            "task_id": 4,
            "task_name": "task_004",
            "task_state_id": 4,
            "update_at": datetime(2025, 12, 24, 12, 34, 56, 789),
            "user_id": 1,
        },
        {
            "task_id": 5,
            "task_name": "task_005",
            "task_state_id": 1,
            "update_at": datetime(2025, 12, 24, 12, 34, 56, 789),
            "user_id": 1,
        }
    ]
    expected_res = TaskListResponse(status=200, messages=[], task_list=expected_task_list)

    ## テスト処理
    result_res = task_list_service.get_task_list(user_id)

    assert expected_res == result_res
