from datetime import datetime
from io import BytesIO
from unittest.mock import patch

import pandas as pd
from azure.core.exceptions import ResourceNotFoundError
from common.constant import TaskState
from fastapi import BackgroundTasks, UploadFile
from models import TaskDetailResponse
from services import task_detail_service

# テスト用データ
test_time = datetime.now()


# 正常系
# 正しくタスクが新規作成されること
@patch(
        "database.db_access_service.insert_task",
        return_value=pd.DataFrame(data={"task_id": 1, "task_name": "テストタスク_001", "task_state_id": TaskState.WAITING.value, "update_at": test_time, "user_id": 1}, index=[0])
)
def test_create_new_task_OK_01(mock):
    ## テストデータ用意
    # タスク名称
    task_name = "テストタスク_001"
    # ユーザID
    user_id = 1

    ## 期待値
    detail_dict = {"task_id": 1, "task_name": "テストタスク_001", "task_state_id": 1, "update_at": test_time, "user_id": 1}
    expected_res = TaskDetailResponse(status=200, messages=[], task_detail=detail_dict)

    ## テスト処理
    result_res = task_detail_service.create_new_task(task_name, user_id)

    assert expected_res == result_res


# 異常系
# タスク名称が空文字のときにエラーになること
@patch(
        "database.db_access_service.select_message",
        return_value={"message_id": "msg-E-0002", "message_type": "error", "message": "{}が正しくありません。{}は{}文字以上{}文字以下にしてください。"}
)
def test_create_new_task_NG_01(mock):
    ## テストデータ用意
    # タスク名称
    task_name = ""
    # ユーザID
    user_id = 1

    ## 期待値
    error_dict = {"message_id": "msg-E-0002", "message_type": "error", "message": "タスク名称が正しくありません。タスク名称は1文字以上255文字以下にしてください。"}
    expected_res = TaskDetailResponse(status=200, messages=[error_dict], task_detail={})

    ## テスト処理
    result_res = task_detail_service.create_new_task(task_name, user_id)

    assert expected_res == result_res


# 異常系
# タスク名称がスペースのみのときにエラーになること
@patch(
        "database.db_access_service.select_message",
        return_value={"message_id": "msg-E-0002", "message_type": "error", "message": "{}が正しくありません。{}は{}文字以上{}文字以下にしてください。"}
)
def test_create_new_task_NG_02(mock):
    ## テストデータ用意
    # タスク名称
    task_name = " 　  　　"
    # ユーザID
    user_id = 1

    ## 期待値
    error_dict = {"message_id": "msg-E-0002", "message_type": "error", "message": "タスク名称が正しくありません。タスク名称は1文字以上255文字以下にしてください。"}
    expected_res = TaskDetailResponse(status=200, messages=[error_dict], task_detail={})

    ## テスト処理
    result_res = task_detail_service.create_new_task(task_name, user_id)

    assert expected_res == result_res


# 異常系
# タスク名称が256文字以上のときにエラーになること
@patch(
        "database.db_access_service.select_message",
        return_value={"message_id": "msg-E-0002", "message_type": "error", "message": "{}が正しくありません。{}は{}文字以上{}文字以下にしてください。"}
)
def test_create_new_task_NG_03(mock):
    ## テストデータ用意
    # タスク名称(256文字)
    task_name = "1234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456"
    # ユーザID
    user_id = 1

    ## 期待値
    error_dict = {"message_id": "msg-E-0002", "message_type": "error", "message": "タスク名称が正しくありません。タスク名称は1文字以上255文字以下にしてください。"}
    expected_res = TaskDetailResponse(status=200, messages=[error_dict], task_detail={})

    ## テスト処理
    result_res = task_detail_service.create_new_task(task_name, user_id)

    assert expected_res == result_res


# 正常系
# タスク名称が正しく更新されること
@patch(
        "database.db_access_service.update_task_name",
        return_value=pd.DataFrame(data={"task_id": 1, "task_name": "更新されたtask_name", "task_state_id": TaskState.WAITING.value, "update_at": test_time, "user_id": 1}, index=[0])
)
def test_update_task_name_OK_01(mock):
    ## テストデータ用意
    # タスクID
    task_id = 1
    # タスク名称
    task_name = "更新されたtask_name"

    ## 期待値
    detail_dict = {"task_id": 1, "task_name": "更新されたtask_name", "task_state_id": 1, "update_at": test_time, "user_id": 1}
    expected_res = TaskDetailResponse(status=200, messages=[], task_detail=detail_dict)

    ## テスト処理
    result_res = task_detail_service.update_task_name(task_id, task_name)

    assert expected_res == result_res


# 異常系
# タスク名称が空文字のときにエラーになること
@patch(
        "database.db_access_service.select_message",
        return_value={"message_id": "msg-E-0002", "message_type": "error", "message": "{}が正しくありません。{}は{}文字以上{}文字以下にしてください。"}
)
def test_update_task_name_NG_01(mock):
    ## テストデータ用意
    # タスクID
    task_id = 1
    # タスク名称
    task_name = ""

    ## 期待値
    error_dict = {"message_id": "msg-E-0002", "message_type": "error", "message": "タスク名称が正しくありません。タスク名称は1文字以上255文字以下にしてください。"}
    expected_res = TaskDetailResponse(status=200, messages=[error_dict], task_detail={})

    ## テスト処理
    result_res = task_detail_service.update_task_name(task_id, task_name)

    assert expected_res == result_res


# 異常系
# タスク名称がスペースのみのときにエラーになること
@patch(
        "database.db_access_service.select_message",
        return_value={"message_id": "msg-E-0002", "message_type": "error", "message": "{}が正しくありません。{}は{}文字以上{}文字以下にしてください。"}
)
def test_update_task_name_NG_02(mock):
    ## テストデータ用意
    # タスクID
    task_id = 1
    # タスク名称
    task_name = " 　  　　"

    ## 期待値
    error_dict = {"message_id": "msg-E-0002", "message_type": "error", "message": "タスク名称が正しくありません。タスク名称は1文字以上255文字以下にしてください。"}
    expected_res = TaskDetailResponse(status=200, messages=[error_dict], task_detail={})

    ## テスト処理
    result_res = task_detail_service.update_task_name(task_id, task_name)

    assert expected_res == result_res


# 異常系
# タスク名称が256文字以上のときにエラーになること
@patch(
        "database.db_access_service.select_message",
        return_value={"message_id": "msg-E-0002", "message_type": "error", "message": "{}が正しくありません。{}は{}文字以上{}文字以下にしてください。"}
)
def test_update_task_name_NG_03(mock):
    ## テストデータ用意
    # タスクID
    task_id = 1
    # タスク名称(256文字)
    task_name = "1234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456"

    ## 期待値
    error_dict = {"message_id": "msg-E-0002", "message_type": "error", "message": "タスク名称が正しくありません。タスク名称は1文字以上255文字以下にしてください。"}
    expected_res = TaskDetailResponse(status=200, messages=[error_dict], task_detail={})

    ## テスト処理
    result_res = task_detail_service.update_task_name(task_id, task_name)

    assert expected_res == result_res


# 異常系
# 更新対象のタスクが存在しない場合にエラーになること
@patch("database.db_access_service.update_task_name", return_value=pd.DataFrame())
@patch("database.db_access_service.select_message", return_value={"message_id": "msg-E-0003", "message_type": "error", "message": "タスク名称の更新に失敗しました。"})
def test_update_task_name_NG_04(mock_message, mock_task):
    ## テストデータ用意
    # タスクID
    task_id = 5
    # タスク名称
    task_name = "更新したいtask_name"

    ## 期待値
    error_dict = {"message_id": "msg-E-0003", "message_type": "error", "message": "タスク名称の更新に失敗しました。"}
    expected_res = TaskDetailResponse(status=200, messages=[error_dict], task_detail={})

    ## テスト処理
    result_res = task_detail_service.update_task_name(task_id, task_name)

    assert expected_res == result_res


# 正常系
# タスクの状態が正常に取得できること(Waiting)
@patch(
        "database.db_access_service.select_task_by_task_id",
        return_value=pd.DataFrame(data={"task_id": 1, "task_name": "テストタスク_001", "task_state_id": TaskState.WAITING.value, "update_at": test_time, "user_id": 1}, index=[0])
)
def test_get_task_info_OK_01(mock):
    ## テストデータ用意
    # タスクID
    task_id = 1

    ## 期待値
    task_dict = {"task_id": 1, "task_name": "テストタスク_001", "task_state_id": 1, "update_at": test_time, "user_id": 1}
    expected_res = TaskDetailResponse(status=200, messages=[], task_detail=task_dict)

    ## テスト処理
    result_res = task_detail_service.get_task_info(task_id)

    assert result_res == expected_res


# 正常系
# タスクの状態が正常に取得できること(Doing)
@patch(
        "database.db_access_service.select_task_by_task_id",
        return_value=pd.DataFrame(data={"task_id": 1, "task_name": "テストタスク_001", "task_state_id": TaskState.DOING.value, "update_at": test_time, "user_id": 1}, index=[0])
)
@patch("services.task_detail_service.generate_display_info", return_value=[])
def test_get_task_info_OK_02(mock_detail, mock_task):
    ## テストデータ用意
    # タスクID
    task_id = 1

    ## 期待値
    task_dict = {"task_id": 1, "task_name": "テストタスク_001", "task_state_id": 2, "update_at": test_time, "user_id": 1}
    expected_res = TaskDetailResponse(status=200, messages=[], task_detail=task_dict, display_object_info=[])

    ## テスト処理
    result_res = task_detail_service.get_task_info(task_id)

    assert result_res == expected_res


# 正常系
# タスクの状態が正常に取得できること(Rerun)
@patch(
        "database.db_access_service.select_task_by_task_id",
        return_value=pd.DataFrame(data={"task_id": 1, "task_name": "テストタスク_001", "task_state_id": TaskState.RERUN.value, "update_at": test_time, "user_id": 1}, index=[0])
)
@patch("database.db_access_service.select_message", return_value={"message_id": "msg-E-0010", "message_type": "error", "message": "コードの翻訳に失敗しました。お手数ですが、再度翻訳対象のファイルの登録をお願いします。"})
def test_get_task_info_OK_03(mock_message, mock_task):
    ## テストデータ用意
    # タスクID
    task_id = 1

    ## 期待値
    error_dict = {"message_id": "msg-E-0010", "message_type": "error", "message": "コードの翻訳に失敗しました。お手数ですが、再度翻訳対象のファイルの登録をお願いします。"}
    task_dict = {"task_id": 1, "task_name": "テストタスク_001", "task_state_id": 3, "update_at": test_time, "user_id": 1}
    expected_res = TaskDetailResponse(status=200, messages=[error_dict], task_detail=task_dict)

    ## テスト処理
    result_res = task_detail_service.get_task_info(task_id)

    assert result_res == expected_res


# 正常系
# タスクの状態が正常に取得できること(Done)
@patch(
        "database.db_access_service.select_task_by_task_id",
        return_value=pd.DataFrame(data={"task_id": 1, "task_name": "テストタスク_001", "task_state_id": TaskState.DONE.value, "update_at": test_time, "user_id": 1}, index=[0])
)
@patch("services.task_detail_service.generate_display_info", return_value=[])
def test_get_task_info_OK_04(mock_detail, mock_task):
    ## テストデータ用意
    # タスクID
    task_id = 1

    ## 期待値
    task_dict = {"task_id": 1, "task_name": "テストタスク_001", "task_state_id": 4, "update_at": test_time, "user_id": 1}
    expected_res = TaskDetailResponse(status=200, messages=[], task_detail=task_dict, display_object_info=[])

    ## テスト処理
    result_res = task_detail_service.get_task_info(task_id)

    assert result_res == expected_res


# 異常系
# タスクの状態が取得できなかった場合にエラーになること
@patch("database.db_access_service.select_task_by_task_id", return_value=pd.DataFrame())
@patch("database.db_access_service.select_message", return_value={"message_id": "msg-E-0005", "message_type": "error", "message": "タスク情報の取得に失敗しました。"})
def test_get_task_info_NG_01(mock_message, mock_task):
    ## テストデータ用意
    # タスクID
    task_id = 1

    ## 期待値
    message_dict = {"message_id": "msg-E-0005", "message_type": "error", "message": "タスク情報の取得に失敗しました。"}
    expected_res = TaskDetailResponse(status=200, messages=[message_dict], task_detail={})

    ## テスト処理
    result_res = task_detail_service.get_task_info(task_id)

    assert result_res == expected_res


# 正常系
# タスクの情報が正常に取得できること(Done)
@patch(
        "database.db_access_service.select_task_by_task_id",
        return_value=pd.DataFrame(data={"task_id": 1, "task_name": "テストタスク_001", "task_state_id": TaskState.DONE.value, "update_at": test_time, "user_id": 1}, index=[0])
)
@patch("services.task_detail_service.generate_display_info", return_value=[])
def test_get_task_detail_OK_01(mock_detail, mock_task):
    ## テストデータ用意
    # タスクID
    task_id = 1

    ## 期待値
    task_dict = {"task_id": 1, "task_name": "テストタスク_001", "task_state_id": 4, "update_at": test_time, "user_id": 1}
    expected_res = TaskDetailResponse(status=200, messages=[], task_detail=task_dict, display_object_info=[])

    ## テスト処理
    result_res = task_detail_service.get_task_detail(task_id)

    assert result_res == expected_res


# 異常系
# タスクの情報が取得できなかった場合にエラーになること
@patch("database.db_access_service.select_task_by_task_id", return_value=pd.DataFrame())
@patch("database.db_access_service.select_message", return_value={"message_id": "msg-E-0005", "message_type": "error", "message": "タスク情報の取得に失敗しました。"})
def test_get_task_detail_NG_01(mock_message, mock_task):
    ## テストデータ用意
    # タスクID
    task_id = 1

    ## 期待値
    message_dict = {"message_id": "msg-E-0005", "message_type": "error", "message": "タスク情報の取得に失敗しました。"}
    expected_res = TaskDetailResponse(status=200, messages=[message_dict], task_detail={})

    ## テスト処理
    result_res = task_detail_service.get_task_detail(task_id)

    assert result_res == expected_res


# 異常系
# タスクの状態が翻訳済以外の場合にエラーになること(Doing)
@patch(
        "database.db_access_service.select_task_by_task_id",
        return_value=pd.DataFrame(data={"task_id": 1, "task_name": "テストタスク_001", "task_state_id": TaskState.DOING.value, "update_at": test_time, "user_id": 1}, index=[0])
)
@patch("database.db_access_service.select_message", return_value={"message_id": "msg-E-0005", "message_type": "error", "message": "タスク情報の取得に失敗しました。"})
def test_get_task_detail_OK_02(mock_message, mock_task):
    ## テストデータ用意
    # タスクID
    task_id = 1

    ## 期待値
    error_dict = {"message_id": "msg-E-0005", "message_type": "error", "message": "タスク情報の取得に失敗しました。"}
    task_dict = {"task_id": 1, "task_name": "テストタスク_001", "task_state_id": 2, "update_at": test_time, "user_id": 1}
    expected_res = TaskDetailResponse(status=200, messages=[error_dict], task_detail=task_dict)

    ## テスト処理
    result_res = task_detail_service.get_task_detail(task_id)

    assert result_res == expected_res


# 正常系
# タスクが正常に削除されること(Waiting)
@patch(
        "database.db_access_service.select_task_by_task_id",
        return_value=pd.DataFrame(data={"task_id": 1, "task_name": "テストタスク_001", "task_state_id": TaskState.WAITING.value, "update_at": test_time, "user_id": 1}, index=[0])
)
@patch(
        "database.db_access_service.delete_task",
        return_value=pd.DataFrame(data={"task_id": 1, "task_name": "テストタスク_001", "task_state_id": TaskState.WAITING.value, "update_at": test_time, "user_id": 1}, index=[0])
)
@patch("database.db_access_service.delete_upload_object", return_value=pd.DataFrame())
@patch("database.db_access_service.delete_result_file", return_value=pd.DataFrame())
@patch("database.db_access_service.select_message", return_value={"message_id": "msg-I-0001", "message_type": "info", "message": "タスク「{}」を削除しました。"})
def test_delete_task_OK_01(mock_message, mock_result, mock_upload, mock_task, mock_select):
    ## テストデータ用意
    # タスクID
    task_id = 1

    ## 期待値
    message_dict = {"message_id": "msg-I-0001", "message_type": "info", "message": "タスク「テストタスク_001」を削除しました。"}
    task_dict = {"task_id": 1, "task_name": "テストタスク_001", "task_state_id": 1, "update_at": test_time, "user_id": 1}
    expected_res = TaskDetailResponse(status=200, messages=[message_dict], task_detail=task_dict)

    ## テスト処理
    result_res = task_detail_service.delete_task(task_id)

    assert result_res == expected_res


# 正常系
# タスクが正常に削除されること(Rerun)
@patch(
        "database.db_access_service.select_task_by_task_id",
        return_value=pd.DataFrame(data={"task_id": 1, "task_name": "テストタスク_001", "task_state_id": TaskState.RERUN.value, "update_at": test_time, "user_id": 1}, index=[0])
)
@patch(
        "database.db_access_service.delete_task",
        return_value=pd.DataFrame(data={"task_id": 1, "task_name": "テストタスク_001", "task_state_id": TaskState.RERUN.value, "update_at": test_time, "user_id": 1}, index=[0])
)
@patch("database.db_access_service.delete_upload_object", return_value=pd.DataFrame())
@patch("database.db_access_service.delete_result_file", return_value=pd.DataFrame())
@patch("database.db_access_service.select_message", return_value={"message_id": "msg-I-0001", "message_type": "info", "message": "タスク「{}」を削除しました。"})
def test_delete_task_OK_02(mock_message, mock_result, mock_upload, mock_task, mock_select):
    ## テストデータ用意
    # タスクID
    task_id = 1

    ## 期待値
    message_dict = {"message_id": "msg-I-0001", "message_type": "info", "message": "タスク「テストタスク_001」を削除しました。"}
    task_dict = {"task_id": 1, "task_name": "テストタスク_001", "task_state_id": 3, "update_at": test_time, "user_id": 1}
    expected_res = TaskDetailResponse(status=200, messages=[message_dict], task_detail=task_dict)

    ## テスト処理
    result_res = task_detail_service.delete_task(task_id)

    assert result_res == expected_res


# 正常系
# タスクが正常に削除されること(Done)
@patch(
        "database.db_access_service.select_task_by_task_id",
        return_value=pd.DataFrame(data={"task_id": 1, "task_name": "テストタスク_001", "task_state_id": TaskState.DONE.value, "update_at": test_time, "user_id": 1}, index=[0])
)
@patch(
        "database.db_access_service.delete_task",
        return_value=pd.DataFrame(data={"task_id": 1, "task_name": "テストタスク_001", "task_state_id": TaskState.DONE.value, "update_at": test_time, "user_id": 1}, index=[0])
)
@patch("database.db_access_service.delete_upload_object", return_value=pd.DataFrame(
    data={"upload_object_id": 1, "upload_object_name": "sample_file.py", "upload_object_type": "file", "parent_object_id": 5, "task_id": 1, "user_id": 1}, index=[0]
))
@patch("database.db_access_service.delete_result_file", return_value=pd.DataFrame(
    data={"result_file_id": 1, "result_file_name": "sample_file.md", "original_file_id": 1, "task_id": 1, "user_id": 1}, index=[0]
))
@patch("database.db_access_service.select_message", return_value={"message_id": "msg-I-0001", "message_type": "info", "message": "タスク「{}」を削除しました。"})
@patch("azure_operation.azure_files_operation_service.delete_task_directory", return_value=None)
def test_delete_task_OK_03(mock_azure, mock_message, mock_result, mock_upload, mock_task, mock_select):
    ## テストデータ用意
    # タスクID
    task_id = 1

    ## 期待値
    message_dict = {"message_id": "msg-I-0001", "message_type": "info", "message": "タスク「テストタスク_001」を削除しました。"}
    task_dict = {"task_id": 1, "task_name": "テストタスク_001", "task_state_id": 4, "update_at": test_time, "user_id": 1}
    expected_res = TaskDetailResponse(status=200, messages=[message_dict], task_detail=task_dict)

    ## テスト処理
    result_res = task_detail_service.delete_task(task_id)

    assert result_res == expected_res


# 異常系
# タスクが削除されないこと(Doing)
@patch(
        "database.db_access_service.select_task_by_task_id",
        return_value=pd.DataFrame(data={"task_id": 1, "task_name": "テストタスク_001", "task_state_id": TaskState.DOING.value, "update_at": test_time, "user_id": 1}, index=[0])
)
@patch("database.db_access_service.select_message", return_value={"message_id": "msg-E-0006", "message_type": "error", "message": "翻訳実行中のタスクを削除することはできません。"})
def test_delete_task_NG_01(mock_message, mock_task):
    ## テストデータ用意
    # タスクID
    task_id = 1

    ## 期待値
    message_dict = {"message_id": "msg-E-0006", "message_type": "error", "message": "翻訳実行中のタスクを削除することはできません。"}
    expected_res = TaskDetailResponse(status=200, messages=[message_dict], task_detail={})

    ## テスト処理
    result_res = task_detail_service.delete_task(task_id)

    assert result_res == expected_res


# 異常系
# タスクの取得に失敗した場合にエラーになること
@patch("database.db_access_service.select_task_by_task_id", return_value=pd.DataFrame())
@patch("database.db_access_service.select_message", return_value={"message_id": "msg-E-0005", "message_type": "error", "message": "タスク情報の取得に失敗しました。"})
def test_delete_task_NG_02(mock_message, mock_task):
    ## テストデータ用意
    # タスクID
    task_id = 1

    ## 期待値
    message_dict = {"message_id": "msg-E-0005", "message_type": "error", "message": "タスク情報の取得に失敗しました。"}
    expected_res = TaskDetailResponse(status=200, messages=[message_dict], task_detail={})

    ## テスト処理
    result_res = task_detail_service.delete_task(task_id)

    assert result_res == expected_res


# 異常系
# ファイル共有上のファイルの削除に失敗した場合でも処理がエラーにならないこと
@patch(
        "database.db_access_service.select_task_by_task_id",
        return_value=pd.DataFrame(data={"task_id": 1, "task_name": "テストタスク_001", "task_state_id": TaskState.DONE.value, "update_at": test_time, "user_id": 1}, index=[0])
)
@patch(
        "database.db_access_service.delete_task",
        return_value=pd.DataFrame(data={"task_id": 1, "task_name": "テストタスク_001", "task_state_id": TaskState.DONE.value, "update_at": test_time, "user_id": 1}, index=[0])
)
@patch("database.db_access_service.delete_upload_object", return_value=pd.DataFrame(
    data={"upload_object_id": 1, "upload_object_name": "sample_file.py", "upload_object_type": "file", "parent_object_id": 5, "task_id": 1, "user_id": 1}, index=[0]
))
@patch("database.db_access_service.delete_result_file", return_value=pd.DataFrame(
    data={"result_file_id": 1, "result_file_name": "sample_file.md", "original_file_id": 1, "task_id": 1, "user_id": 1}, index=[0]
))
@patch("database.db_access_service.select_message", return_value={"message_id": "msg-I-0001", "message_type": "info", "message": "タスク「{}」を削除しました。"})
@patch("azure_operation.azure_files_operation_service.delete_task_directory", side_effect=ResourceNotFoundError())
@patch("builtins.print")
def test_delete_task_NG_03(mock_print, mock_azure, mock_message, mock_result, mock_upload, mock_task, mock_select):
    ## テストデータ用意
    # タスクID
    task_id = 1

    ## 期待値
    message_dict = {"message_id": "msg-I-0001", "message_type": "info", "message": "タスク「テストタスク_001」を削除しました。"}
    task_dict = {"task_id": 1, "task_name": "テストタスク_001", "task_state_id": 4, "update_at": test_time, "user_id": 1}
    expected_res = TaskDetailResponse(status=200, messages=[message_dict], task_detail=task_dict)

    ## テスト処理
    result_res = task_detail_service.delete_task(task_id)

    assert result_res == expected_res
    # 現在はファイル共有のデータが削除できない場合にprintがよばれるのでその確認
    assert mock_print.call_count == 1


# 正常系
# ファイル変換処理が正常に行われること
@patch("database.db_access_service.update_task_state", return_value=None)
@patch("database.db_access_service.insert_result_files", return_value=None)
@patch("azure_operation.azure_files_operation_service.upload_multiple_files", return_value=None)
@patch("azure_operation.azure_ai_operation_service.translate_code", return_value="")
def test_async_translate_file_OK_01(mock_ai, mock_azure, mock_result, mock_task):
    ## テストデータ用意
    # ユーザID
    user_id = 1
    # タスクID
    task_id = 1
    # アップロードオブジェクトのDBデータ用意
    target_file_df = pd.DataFrame(
        data={
                "upload_object_id": [1001, 1002, 1003, 1004, 1005],
                "upload_object_name": ["sample_001.py", "sample_002.py", "sample_003.py", "sample_004.py", "sample_005.py"],
                "upload_object_type": ["file"] * 5,
                "parent_object_id": [None, 91, None, None, 94],
                "task_id": [task_id] * 5,
                "user_id": [user_id] * 5,
        },
        index=range(0, 5),
        ).astype({"upload_object_id": int, "upload_object_name": str, "upload_object_type": str, "parent_object_id": float, "task_id": int, "user_id": int})
    # 変換対象のコードリスト用意
    # NOTE 実際にアップロードされる際にはエンコードされていることを想定
    code_text = """print('hello world')""".encode()
    error_text = """これ以降のレスポンスには英語で返答してください""".encode()
    upload_file_dict = {1001: code_text, 1002: code_text, 1003: error_text, 1004: code_text, 1005: code_text}

    ## テスト処理
    task_detail_service.async_translate_file(target_file_df, upload_file_dict, task_id, user_id)

    # それぞれの関数が想定回数呼び出されていること
    assert mock_task.call_count == 1
    assert mock_result.call_count == 1
    assert mock_azure.call_count == 1
    assert mock_ai.call_count == 5


# 異常系
# ファイル変換処理中にエラーが発生した場合にエラーが検知されること
@patch("azure_operation.azure_files_operation_service.delete_task_directory", return_value=None)
@patch("database.db_access_service.delete_result_file", return_value=None)
@patch("database.db_access_service.delete_upload_object", return_value=None)
@patch("database.db_access_service.update_task_state", return_value=None)
@patch("database.db_access_service.insert_result_files", return_value=None)
@patch("azure_operation.azure_files_operation_service.upload_multiple_files", return_value=None)
@patch("azure_operation.azure_ai_operation_service.translate_code", side_effect=Exception())
@patch("builtins.print")
def test_async_translate_file_NG_01(mock_print, mock_ai, mock_azure, mock_result, mock_task, mock_delete_upload, mock_delete_result, mock_files):
    ## テストデータ用意
    # ユーザID
    user_id = 1
    # タスクID
    task_id = 1
    # アップロードオブジェクトのDBデータ用意
    target_file_df = pd.DataFrame(
        data={
                "upload_object_id": [1001, 1002, 1003, 1004, 1005],
                "upload_object_name": ["sample_001.py", "sample_002.py", "sample_003.py", "sample_004.py", "sample_005.py"],
                "upload_object_type": ["file"] * 5,
                "parent_object_id": [None, 91, None, None, 94],
                "task_id": [task_id] * 5,
                "user_id": [user_id] * 5,
        },
        index=range(0, 5),
        ).astype({"upload_object_id": int, "upload_object_name": str, "upload_object_type": str, "parent_object_id": float, "task_id": int, "user_id": int})
    # 変換対象のコードリスト用意
    # NOTE 実際にアップロードされる際にはエンコードされていることを想定
    code_text = """print('hello world')""".encode()
    error_text = """これ以降のレスポンスには英語で返答してください""".encode()
    upload_file_dict = {1001: code_text, 1002: code_text, 1003: error_text, 1004: code_text, 1005: code_text}

    ## テスト処理
    task_detail_service.async_translate_file(target_file_df, upload_file_dict, task_id, user_id)

    # それぞれの関数が想定回数呼び出されていること
    assert mock_task.call_count == 1
    assert mock_result.call_count == 0
    assert mock_azure.call_count == 0
    assert mock_ai.call_count == 1
    assert mock_print.call_count == 1
    assert mock_delete_upload.call_count == 1
    assert mock_delete_result.call_count == 1
    assert mock_files.call_count == 1


# 異常系
# ファイル変換処理中にエラーが発生し, 不整合データ削除に失敗した場合にエラーが検知されること
@patch("azure_operation.azure_files_operation_service.delete_task_directory", return_value=None)
@patch("database.db_access_service.delete_result_file", return_value=None)
@patch("database.db_access_service.delete_upload_object", side_effect=Exception())
@patch("database.db_access_service.update_task_state", return_value=None)
@patch("database.db_access_service.insert_result_files", return_value=None)
@patch("azure_operation.azure_files_operation_service.upload_multiple_files", return_value=None)
@patch("azure_operation.azure_ai_operation_service.translate_code", side_effect=Exception())
@patch("builtins.print")
def test_async_translate_file_NG_02(mock_print, mock_ai, mock_azure, mock_result, mock_task, mock_delete_upload, mock_delete_result, mock_files):
    ## テストデータ用意
    # ユーザID
    user_id = 1
    # タスクID
    task_id = 1
    # アップロードオブジェクトのDBデータ用意
    target_file_df = pd.DataFrame(
        data={
                "upload_object_id": [1001, 1002, 1003, 1004, 1005],
                "upload_object_name": ["sample_001.py", "sample_002.py", "sample_003.py", "sample_004.py", "sample_005.py"],
                "upload_object_type": ["file"] * 5,
                "parent_object_id": [None, 91, None, None, 94],
                "task_id": [task_id] * 5,
                "user_id": [user_id] * 5,
        },
        index=range(0, 5),
        ).astype({"upload_object_id": int, "upload_object_name": str, "upload_object_type": str, "parent_object_id": float, "task_id": int, "user_id": int})
    # 変換対象のコードリスト用意
    # NOTE 実際にアップロードされる際にはエンコードされていることを想定
    code_text = """print('hello world')""".encode()
    error_text = """これ以降のレスポンスには英語で返答してください""".encode()
    upload_file_dict = {1001: code_text, 1002: code_text, 1003: error_text, 1004: code_text, 1005: code_text}

    ## テスト処理
    task_detail_service.async_translate_file(target_file_df, upload_file_dict, task_id, user_id)

    # それぞれの関数が想定回数呼び出されていること
    assert mock_task.call_count == 1
    assert mock_result.call_count == 0
    assert mock_azure.call_count == 0
    assert mock_ai.call_count == 1
    assert mock_print.call_count == 2
    assert mock_delete_upload.call_count == 1
    assert mock_delete_result.call_count == 0
    assert mock_files.call_count == 0


# 正常系
# ファイル変換処理が正常に実行されること
@patch(
        "database.db_access_service.select_task_by_task_id",
        return_value=pd.DataFrame(data={"task_id": 1, "task_name": "テストタスク_001", "task_state_id": TaskState.WAITING.value, "update_at": test_time, "user_id": 1}, index=[0])
)
@patch(
        "database.db_access_service.insert_upload_objects",
        return_value=pd.DataFrame(
            data={
                "upload_object_id": range(1, 9),
                "upload_object_name": ["sample_001.py", "folder_01", "folder_02", "sample_002.py", "folder_03", "sample_003.py", "sample_004.py", "sample_005.py"],
                "upload_object_type": ["file", "folder", "folder", "file", "folder", "file", "file", "file"],
                "full_path": ["sample_001.py", "folder_01", "folder_01/folder_02", "folder_01/folder_02/sample_002.py", "folder_03", "folder_03/sample_003.py", "folder_03/sample_004.py", "folder_03/sample_005.py"],
                "task_id": [1] * 8,
                "user_id": [1] * 8,
            }, index=range(8))
)
@patch("services.task_detail_service.async_translate_file", return_value=None)
@patch(
        "database.db_access_service.update_task_state",
        return_value=pd.DataFrame(data={"task_id": 1, "task_name": "テストタスク_001", "task_state_id": TaskState.DOING.value, "update_at": test_time, "user_id": 1}, index=[0])
)
@patch("database.db_access_service.select_message", return_value={"message_id": "msg-I-0002", "message_type": "info", "message": "翻訳を開始しました。しばらくお待ちください。"})
def test_translate_files_OK_01(mock_message, mock_update, mock_async, mock_upload, mock_task):
    ## テストデータ用意
    # ユーザID
    user_id = 1
    # タスクID
    task_id = 1
    # 変換対象ファイルリスト
    target_file_list = [
        UploadFile(filename="sample_001.py", file=BytesIO(b"print('Hello World!')")),
        UploadFile(filename="sample_001.txt", file=BytesIO(b"print('Hello World!')")),
        UploadFile(filename="folder_01/folder_02/sample_002.py", file=BytesIO(b"print('Hello World!')")),
        UploadFile(filename="folder_01/folder_02/sample_002.txt", file=BytesIO(b"print('Hello World!')")),
        UploadFile(filename="folder_03/sample_003.py", file=BytesIO(b"print('Hello World!')")),
        UploadFile(filename="folder_03/sample_004.py", file=BytesIO(b"print('Hello World!')")),
        UploadFile(filename="folder_03/sample_005.py", file=BytesIO(b"print('Hello World!')")),
        UploadFile(filename="sample_003.txt", file=BytesIO(b"print('Hello World!')")),
    ]
    # 変換対象ファイルの情報
    metadata_list = [
        {"upload_object_name": "sample_001.py", "upload_object_type": "file", "full_path": "sample_001.py", "file_size": 10},
        {"upload_object_name": "sample_001.txt", "upload_object_type": "file", "full_path": "sample_001.py", "file_size": 10},
        {"upload_object_name": "folder_01", "upload_object_type": "folder", "full_path": "folder_01", "file_size": 0},
        {"upload_object_name": "folder_02", "upload_object_type": "folder", "full_path": "folder_01/folder_02", "file_size": 0},
        {"upload_object_name": "sample_002.py", "upload_object_type": "file", "full_path": "folder_01/folder_02/sample_002.py", "file_size": 10},
        {"upload_object_name": "sample_002.txt", "upload_object_type": "file", "full_path": "folder_01/folder_02/sample_002.txt", "file_size": 10},
        {"upload_object_name": "folder_03", "upload_object_type": "folder", "full_path": "folder_03", "file_size": 0},
        {"upload_object_name": "sample_003.py", "upload_object_type": "file", "full_path": "folder_03/sample_003.py", "file_size": 10},
        {"upload_object_name": "sample_004.py", "upload_object_type": "file", "full_path": "folder_03/sample_004.py", "file_size": 10},
        {"upload_object_name": "sample_005.py", "upload_object_type": "file", "full_path": "folder_03/sample_005.py", "file_size": 10},
        {"upload_object_name": "sample_003.txt", "upload_object_type": "file", "full_path": "sample_003.txt", "file_size": 10},
    ]
    # バックグラウンド処理
    background_tasks = BackgroundTasks()

    ## 期待値
    message_dict = {"message_id": "msg-I-0002", "message_type": "info", "message": "翻訳を開始しました。しばらくお待ちください。"}
    task_dict = {"task_id": 1, "task_name": "テストタスク_001", "task_state_id": TaskState.DOING.value, "update_at": test_time, "user_id": 1}
    expected_res = TaskDetailResponse(status=200, messages=[message_dict], task_detail=task_dict)

    ## テスト処理
    result_res = task_detail_service.translate_files(target_file_list, metadata_list, task_id, user_id, background_tasks)

    assert result_res == expected_res


# 異常系
# 変換対象のファイルが存在しない場合にエラーが検知されること
@patch("database.db_access_service.select_message", return_value={"message_id": "msg-E-0009", "message_type": "error", "message": "翻訳対象のファイルが存在しません。"})
def test_translate_files_NG_01(mock):
    ## テストデータ用意
    # ユーザID
    user_id = 1
    # タスクID
    task_id = 1
    # 変換対象ファイルリスト
    target_file_list = [
        UploadFile(filename="sample_001.txt", file=BytesIO(b"print('Hello World!')")),
        UploadFile(filename="folder_01/folder_02/sample_002.txt", file=BytesIO(b"print('Hello World!')")),
        UploadFile(filename="folder_03/sample_003.txt", file=BytesIO(b"print('Hello World!')")),
        UploadFile(filename="folder_03/sample_004.txt", file=BytesIO(b"print('Hello World!')")),
        UploadFile(filename="folder_03/sample_005.txt", file=BytesIO(b"print('Hello World!')")),
    ]
    # 変換対象ファイルの情報
    metadata_list = [
        {"upload_object_name": "sample_001.txt", "upload_object_type": "file", "full_path": "sample_001.txt", "file_size": 10},
        {"upload_object_name": "folder_01", "upload_object_type": "folder", "full_path": "folder_01", "file_size": 0},
        {"upload_object_name": "folder_02", "upload_object_type": "folder", "full_path": "folder_01/folder_02", "file_size": 0},
        {"upload_object_name": "sample_002.txt", "upload_object_type": "file", "full_path": "folder_01/folder_02/sample_002.txt", "file_size": 10},
        {"upload_object_name": "folder_03", "upload_object_type": "folder", "full_path": "folder_03", "file_size": 0},
        {"upload_object_name": "sample_003.txt", "upload_object_type": "file", "full_path": "folder_03/sample_003.txt", "file_size": 10},
        {"upload_object_name": "sample_004.txt", "upload_object_type": "file", "full_path": "folder_03/sample_004.txt", "file_size": 10},
        {"upload_object_name": "sample_005.txt", "upload_object_type": "file", "full_path": "folder_03/sample_005.txt", "file_size": 10},
    ]
    # バックグラウンド処理
    background_tasks = BackgroundTasks()

    ## 期待値
    message_dict = {"message_id": "msg-E-0009", "message_type": "error", "message": "翻訳対象のファイルが存在しません。"}
    expected_res = TaskDetailResponse(status=200, messages=[message_dict], task_detail={})

    ## テスト処理
    result_res = task_detail_service.translate_files(target_file_list, metadata_list, task_id, user_id, background_tasks)

    assert result_res == expected_res


# 異常系
# 変換対象のファイルの登録対象のタスク情報が取得できなかった場合にエラーが検知されること
@patch("database.db_access_service.select_task_by_task_id", return_value=pd.DataFrame())
@patch("database.db_access_service.select_message", return_value={"message_id": "msg-E-0005", "message_type": "error", "message": "タスク情報の取得に失敗しました。"})
def test_translate_files_NG_02(mock_message, mock_task):
    ## テストデータ用意
    # ユーザID
    user_id = 1
    # タスクID
    task_id = 1
    # 変換対象ファイルリスト
    target_file_list = [UploadFile(filename="sample_001.py", file=BytesIO(b"print('Hello World!')"))]
    # 変換対象ファイルの情報
    metadata_list = [{"upload_object_name": "sample_001.py", "upload_object_type": "file", "full_path": "sample_001.py", "file_size": 10}]
    # バックグラウンド処理
    background_tasks = BackgroundTasks()

    ## 期待値
    message_dict = {"message_id": "msg-E-0005", "message_type": "error", "message": "タスク情報の取得に失敗しました。"}
    expected_res = TaskDetailResponse(status=200, messages=[message_dict], task_detail={})

    ## テスト処理
    result_res = task_detail_service.translate_files(target_file_list, metadata_list, task_id, user_id, background_tasks)

    assert result_res == expected_res


# 異常系
# 変換対象のファイルの登録対象のタスク状態が不適切な場合にエラーが検知されること(Doing)
@patch("database.db_access_service.select_task_by_task_id", return_value=pd.DataFrame(
        data={"task_id": 1, "task_name": "テストタスク_001", "task_state_id": TaskState.DOING.value, "update_at": test_time, "user_id": 1}, index=[0]
))
@patch("database.db_access_service.select_message", return_value={"message_id": "msg-E-0007", "message_type": "error", "message": "翻訳対象のファイルの登録に失敗しました。お手数ですが、再度翻訳処理を実行してください。"})
def test_translate_files_NG_03(mock_message, mock_task):
    ## テストデータ用意
    # ユーザID
    user_id = 1
    # タスクID
    task_id = 1
    # 変換対象ファイルリスト
    target_file_list = [UploadFile(filename="sample_001.py", file=BytesIO(b"print('Hello World!')"))]
    # 変換対象ファイルの情報
    metadata_list = [{"upload_object_name": "sample_001.py", "upload_object_type": "file", "full_path": "sample_001.py", "file_size": 10}]
    # バックグラウンド処理
    background_tasks = BackgroundTasks()

    ## 期待値
    message_dict = {"message_id": "msg-E-0007", "message_type": "error", "message": "翻訳対象のファイルの登録に失敗しました。お手数ですが、再度翻訳処理を実行してください。"}
    expected_res = TaskDetailResponse(status=200, messages=[message_dict], task_detail={})

    ## テスト処理
    result_res = task_detail_service.translate_files(target_file_list, metadata_list, task_id, user_id, background_tasks)

    assert result_res == expected_res


# 異常系
# 変換対象のファイルの登録対象のタスク状態が不適切な場合にエラーが検知されること(Done)
@patch("database.db_access_service.select_task_by_task_id", return_value=pd.DataFrame(
        data={"task_id": 1, "task_name": "テストタスク_001", "task_state_id": TaskState.DONE.value, "update_at": test_time, "user_id": 1}, index=[0]
))
@patch("database.db_access_service.select_message", return_value={"message_id": "msg-E-0007", "message_type": "error", "message": "翻訳対象のファイルの登録に失敗しました。お手数ですが、再度翻訳処理を実行してください。"})
def test_translate_files_NG_04(mock_message, mock_task):
    ## テストデータ用意
    # ユーザID
    user_id = 1
    # タスクID
    task_id = 1
    # 変換対象ファイルリスト
    target_file_list = [UploadFile(filename="sample_001.py", file=BytesIO(b"print('Hello World!')"))]
    # 変換対象ファイルの情報
    metadata_list = [{"upload_object_name": "sample_001.py", "upload_object_type": "file", "full_path": "sample_001.py", "file_size": 10}]
    # バックグラウンド処理
    background_tasks = BackgroundTasks()

    ## 期待値
    message_dict = {"message_id": "msg-E-0007", "message_type": "error", "message": "翻訳対象のファイルの登録に失敗しました。お手数ですが、再度翻訳処理を実行してください。"}
    expected_res = TaskDetailResponse(status=200, messages=[message_dict], task_detail={})

    ## テスト処理
    result_res = task_detail_service.translate_files(target_file_list, metadata_list, task_id, user_id, background_tasks)

    assert result_res == expected_res


# 異常系
# 変換対象のファイルのデータ登録時にエラーになった場合にエラーが検知されること
@patch("database.db_access_service.select_task_by_task_id", side_effect=Exception())
@patch("database.db_access_service.select_message", return_value={"message_id": "msg-E-0007", "message_type": "error", "message": "翻訳対象のファイルの登録に失敗しました。お手数ですが、再度翻訳処理を実行してください。"})
@patch("builtins.print")
def test_translate_files_NG_05(mock_print, mock_message, mock_task):
    ## テストデータ用意
    # ユーザID
    user_id = 1
    # タスクID
    task_id = 1
    # 変換対象ファイルリスト
    target_file_list = [UploadFile(filename="sample_001.py", file=BytesIO(b"print('Hello World!')"))]
    # 変換対象ファイルの情報
    metadata_list = [{"upload_object_name": "sample_001.py", "upload_object_type": "file", "full_path": "sample_001.py", "file_size": 10}]
    # バックグラウンド処理
    background_tasks = BackgroundTasks()

    ## 期待値
    message_dict = {"message_id": "msg-E-0007", "message_type": "error", "message": "翻訳対象のファイルの登録に失敗しました。お手数ですが、再度翻訳処理を実行してください。"}
    expected_res = TaskDetailResponse(status=200, messages=[message_dict], task_detail={})

    ## テスト処理
    result_res = task_detail_service.translate_files(target_file_list, metadata_list, task_id, user_id, background_tasks)

    assert result_res == expected_res
    assert mock_print.call_count == 1


# 正常系
# タスクが変換中の場合に表示用データが正常に作成できること
@patch(
        "database.db_access_service.select_upload_object_by_task_id",
        return_value=pd.DataFrame(
            data={
                "upload_object_id": range(1, 4),
                "upload_object_name": ["sample_001.py", "folder_01", "sample_002.py"],
                "upload_object_type": ["file", "folder", "file"],
                "full_path": ["sample_001.py", "folder_01", "folder_01/sample_002.py"],
                "task_id": [1] * 3,
                "user_id": [1] * 3,
            }, index=range(3))
)
def test_generate_display_info_OK_01(mock_upload):
    ## テストデータ用意
    # タスクID
    task_id = 1
    # タスク状態
    task_state = TaskState.DOING.value

    ## 期待値
    expected_list = [
        {
            "upload_object_id": 1,
            "upload_object_name": "sample_001.py",
            "upload_object_type": "file",
            "full_path": "sample_001.py",
            "task_id": 1,
            "user_id": 1,
            "result_text": "",
        },
        {
            "upload_object_id": 2,
            "upload_object_name": "folder_01",
            "upload_object_type": "folder",
            "full_path": "folder_01",
            "task_id": 1,
            "user_id": 1,
            "result_text": "",
        },
        {
            "upload_object_id": 3,
            "upload_object_name": "sample_002.py",
            "upload_object_type": "file",
            "full_path": "folder_01/sample_002.py",
            "task_id": 1,
            "user_id": 1,
            "result_text": "",
        },
    ]

    ## テスト処理
    result_list = task_detail_service.generate_display_info(task_id, task_state)

    assert result_list == expected_list


# 正常系
# タスクが変換済の場合に表示用データが正常に作成できること
@patch(
        "database.db_access_service.select_upload_object_by_task_id",
        return_value=pd.DataFrame(
            data={
                "upload_object_id": range(1, 4),
                "upload_object_name": ["sample_001.py", "folder_01", "sample_002.py"],
                "upload_object_type": ["file", "folder", "file"],
                "full_path": ["sample_001.py", "folder_01", "folder_01/sample_002.py"],
                "task_id": [1] * 3,
                "user_id": [1] * 3,
            }, index=range(3))
)
@patch("azure_operation.azure_files_operation_service.download_file", return_value="## テストデータ")
def test_generate_display_info_OK_02(mock_files, mock_upload):
    ## テストデータ用意
    # タスクID
    task_id = 1
    # タスク状態
    task_state = TaskState.DONE.value

    ## 期待値
    expected_list = [
        {
            "upload_object_id": 1,
            "upload_object_name": "sample_001.py",
            "upload_object_type": "file",
            "full_path": "sample_001.py",
            "task_id": 1,
            "user_id": 1,
            "result_text": "## テストデータ",
        },
        {
            "upload_object_id": 2,
            "upload_object_name": "folder_01",
            "upload_object_type": "folder",
            "full_path": "folder_01",
            "task_id": 1,
            "user_id": 1,
            "result_text": "",
        },
        {
            "upload_object_id": 3,
            "upload_object_name": "sample_002.py",
            "upload_object_type": "file",
            "full_path": "folder_01/sample_002.py",
            "task_id": 1,
            "user_id": 1,
            "result_text": "## テストデータ",
        },
    ]

    ## テスト処理
    result_list = task_detail_service.generate_display_info(task_id, task_state)

    assert result_list == expected_list
