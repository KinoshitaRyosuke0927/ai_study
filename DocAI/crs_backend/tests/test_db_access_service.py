"""
本ファイルのテストはすべてAzure SQLDatabaseに接続する処理なので, 必要に応じてスキップなどすること
NOTE テスト対象のDB crs-test は一定時間アクセスが無いと停止する設定なので, テスト前にあらかじめDBを起動状態にしておかないとテストはエラーになることがあります
"""

from datetime import datetime, timedelta

import pandas as pd

from database import db_access_service
from services import login_service


# Azure SQLDatabaseへの接続確認を行うためのテスト
# NOTE 本テストがエラーになる場合は作業PCのODBCドライバーのバージョンがdb_access_infoの設定値と異なるか, 許可されていないIPアドレスからの実行である可能性が高い
def test_azure_database_connection_test():
    ## テストデータ用意
    # メールアドレス
    mail_address = "r-kinoshita@jbd.co.jp"
    # 接続を実施
    df = db_access_service.select_user(mail_address)
    # 接続時にエラーが出ないことを確認
    print(df)
    print(df.info())


############################################################
## m_messageテーブル
############################################################
# 正常系
# m_messageテーブルのデータが正常に取得できること(ERROR)
def test_select_message_OK_01():
    ## テストデータ用意
    # メッセージID
    message_id = "msg-E-0001"

    ## 期待値
    message_type = "error"
    message = "メールアドレスまたはパスワードが正しくありません。"

    ## テスト処理
    result_dict = db_access_service.select_message(message_id)

    assert result_dict["message_type"] == message_type
    assert result_dict["message"] == message


# 正常系
# m_messageテーブルのデータが正常に取得できること(INFO)
def test_select_message_OK_02():
    ## テストデータ用意
    # メッセージID
    message_id = "msg-I-0001"

    ## 期待値
    message_type = "info"
    message = "タスク「{}」を削除しました。"

    ## テスト処理
    result_dict = db_access_service.select_message(message_id)

    assert result_dict["message_type"] == message_type
    assert result_dict["message"] == message


############################################################
## m_userテーブル
############################################################
# 正常系
# DBに登録されているIDとパスワードで正常にユーザ情報の照合が行えること
def test_login_OK_01():
    ## テストデータ用意
    # メールアドレス
    mail_address = "r-kinoshita@jbd.co.jp"
    # パスワード
    password = "4406"

    ## 期待値
    # ユーザID
    user_id = 3
    # ユーザ名称
    user_name = "木下 凌介"

    ## テスト処理実施
    res = login_service.login(mail_address, password)

    assert res.user_id == user_id
    assert res.user_name == user_name


# 正常系
# IDが誤っている場合にログインに失敗すること
def test_login_NG_01():
    ## テストデータ用意
    # メールアドレス
    mail_address = "r-kinoshitaaaaaaaaaa@jbd-test.co.jp"
    # パスワード
    password = "4406"

    ## 期待値
    expected_dict = {"message_id": "msg-E-0001", "message_type": "error", "message": "メールアドレスまたはパスワードが正しくありません。"}

    ## テスト処理実施
    res = login_service.login(mail_address, password)

    assert len(res.messages) == 1
    assert res.messages[0] == expected_dict
    assert res.user_name == ""
    assert res.user_id is None


# 正常系
# パスワードが誤っている場合にログインに失敗すること
def test_login_NG_02():
    ## テストデータ用意
    # メールアドレス
    mail_address = "r-kinoshita@jbd.co.jp"
    # パスワード
    password = "kinoshita0927"

    ## 期待値
    expected_dict = {"message_id": "msg-E-0001", "message_type": "error", "message": "メールアドレスまたはパスワードが正しくありません。"}

    ## テスト処理実施
    res = login_service.login(mail_address, password)

    assert len(res.messages) == 1
    assert res.messages[0] == expected_dict
    assert res.user_name == ""
    assert res.user_id is None


############################################################
## t_taskテーブル
############################################################
# 正常系
# 該当ユーザのタスク情報のみ取得されること
def test_select_task_by_user_id_OK_01():
    ## テストデータ用意
    # ユーザID
    user_id_1 = 101

    # タスク新規作成
    df = db_access_service.insert_task("task_001", user_id_1)
    task_id_001 = int(df["task_id"].iloc[0])
    df = db_access_service.insert_task("task_002", user_id_1)
    task_id_002 = int(df["task_id"].iloc[0])
    df = db_access_service.insert_task("task_003", user_id_1)
    task_id_003 = int(df["task_id"].iloc[0])

    # 別のユーザID
    user_id_2 = 102
    user_id_3 = 103
    # タスク新規作成
    df = db_access_service.insert_task("task_001", user_id_2)
    task_id_004 = int(df["task_id"].iloc[0])
    df = db_access_service.insert_task("task_002", user_id_2)
    task_id_005 = int(df["task_id"].iloc[0])

    # タスク情報取得
    df_task_01 = db_access_service.select_task_by_user_id(user_id_1)
    df_task_02 = db_access_service.select_task_by_user_id(user_id_2)
    df_task_03 = db_access_service.select_task_by_user_id(user_id_3)

    # タスクが登録されていること
    assert len(df_task_01) == 3
    assert len(df_task_02) == 2
    assert len(df_task_03) == 0

    # タスクを削除
    db_access_service.delete_task(task_id_001)
    db_access_service.delete_task(task_id_002)
    db_access_service.delete_task(task_id_003)
    db_access_service.delete_task(task_id_004)
    db_access_service.delete_task(task_id_005)

    # タスク情報取得
    df_task_01 = db_access_service.select_task_by_user_id(user_id_1)
    df_task_02 = db_access_service.select_task_by_user_id(user_id_2)
    df_task_03 = db_access_service.select_task_by_user_id(user_id_3)

    # タスクが登録されていないこと
    assert len(df_task_01) == 0
    assert len(df_task_02) == 0
    assert len(df_task_03) == 0


# 正常系
# タスク新規作成 -> タスク名称変更 -> タスク削除と一連の流れで動作確認
# NOTE テスト中で作成したデータは最終的に削除されるので, テストが正常終了する限りは既存のデータに影響はない想定
def test_task_operation_scenario_OK_01():
    ## テストデータ用意
    # ユーザID
    user_id = 99
    # タスク名称
    task_name = "タスク操作シナリオテスト"

    # タスク新規作成
    # NOTE Database上ではミリ秒が上2桁に丸まってしまいdatetime.datetimeより有効桁数が少なくなるため, 比較のためにdatetime.datetime型の値を秒単位で丸めている
    start_time = datetime.now().replace(microsecond=0)
    df_task = db_access_service.insert_task(task_name, user_id)
    end_time = datetime.now().replace(microsecond=0) + timedelta(seconds=1)

    # タスクが正常に作成されていること
    assert len(df_task) == 1
    # タスク名称が設定したものになっていること
    assert df_task["task_name"].iloc[0] == task_name
    # タスクの作成者が指定したユーザになっていること
    assert df_task["user_id"].iloc[0] == user_id
    # タスクの状態が「準備中」であること
    assert df_task["task_state_id"].iloc[0] == 1
    # タスクの作成時刻がテスト実施時間内であること
    assert start_time <= pd.to_datetime(df_task["update_at"].iloc[0]) and pd.to_datetime(df_task["update_at"].iloc[0]) <= end_time

    # 作成したタスクのタスクIDを取得
    task_id = int(df_task["task_id"].iloc[0])
    # タスクの情報を取得
    df_task_read = db_access_service.select_task_by_task_id(task_id)

    # 参照したタスクの情報が登録したタスクの情報と一致すること
    assert df_task.equals(df_task_read)

    # 更新するタスク名
    update_task_name = "update_タスク操作シナリオテスト"
    # 作成したタスクの名称を更新
    start_time = datetime.now().replace(microsecond=0)
    df_update = db_access_service.update_task_name(task_id, update_task_name)
    end_time = datetime.now().replace(microsecond=0) + timedelta(seconds=1)

    # タスク名称が正常に更新されていること
    assert len(df_update) == 1
    # 更新した名称が設定したものになっていること
    assert df_update["task_name"].iloc[0] == update_task_name
    # タスク名称の更新時刻がテスト実施時間内であること
    assert start_time <= pd.to_datetime(df_update["update_at"].iloc[0]) and pd.to_datetime(df_update["update_at"].iloc[0]) <= end_time

    # 作成したタスクを削除する
    df_delete = db_access_service.delete_task(task_id)
    # タスクが正常に削除されていること
    assert len(df_delete) == 1
    # 削除したタスクのIDが指定したものであること
    assert df_delete["task_id"].iloc[0] == task_id
    # 削除したタスクの名称が指定したものであること
    assert df_delete["task_name"].iloc[0] == update_task_name
    # 削除したタスクの作成者が削除者であること
    assert df_delete["user_id"].iloc[0] == user_id

    # 削除したタスクのタスク情報を取得
    df = db_access_service.select_task_by_task_id(task_id)
    # 削除したタスクの情報がDBから消えていること
    assert len(df) == 0


# 正常系
# タスクの状態が正常に更新できること(Waiting -> Doing -> Rerun -> Done)
def test_update_task_state_OK_01():
    ## テストデータ用意
    # ユーザID
    user_id = 99
    # タスク名称
    task_name = "タスク状態更新テスト"

    # タスク新規作成
    df_task = db_access_service.insert_task(task_name, user_id)
    # 作成したタスクのタスクIDを取得
    task_id = int(df_task["task_id"].iloc[0])

    assert df_task["task_state_id"].iloc[0] == 1

    # タスク状態更新(Waiting -> Doing)
    df = db_access_service.update_task_state(task_id, 2)
    assert df["task_state_id"].iloc[0] == 2

    # タスク状態更新(Doing -> Rerun)
    df = db_access_service.update_task_state(task_id, 3)
    assert df["task_state_id"].iloc[0] == 3

    # タスク状態更新(Rerun -> Done)
    df = db_access_service.update_task_state(task_id, 4)
    assert df["task_state_id"].iloc[0] == 4

    # 作成したタスクを削除する
    df_delete = db_access_service.delete_task(task_id)
    assert df_delete["task_id"].iloc[0] == task_id


# 異常系
# 存在しないタスクIDが指定された場合にエラーにならず, 更新されていないことが検知できること
def test_update_task_state_NG_01():
    ## テストデータ用意
    # タスクID
    task_id = 99999

    # タスク新規作成
    df = db_access_service.update_task_state(task_id, 2)

    assert df.empty


############################################################
## t_upload_objectテーブル
############################################################
# 正常系
# タスク新規作成 -> アップロードオブジェクト作成 -> タスク&アップロードオブジェクト削除と一連の流れで動作確認
# NOTE テスト中で作成したデータは最終的に削除されるので, テストが正常終了する限りは既存のデータに影響はない想定
def test_upload_object_operation_scenario_OK_01():
    ## テストデータ用意
    # ユーザID
    user_id = 99
    # タスク名称
    task_name = "アップロードオブジェクト操作シナリオテスト"

    # タスク新規作成
    df_task = db_access_service.insert_task(task_name, user_id)
    # 作成したタスクのタスクIDを取得
    task_id = int(df_task["task_id"].iloc[0])
    # オブジェクトアップロード
    df_upload = db_access_service.insert_upload_object("sample_file_001.py", "file", "sample_file_001.py", task_id, user_id)

    # アップロードオブジェクトが正常に作成されていること(file)
    assert df_upload["upload_object_name"].iloc[0] == "sample_file_001.py"
    assert df_upload["upload_object_type"].iloc[0] == "file"
    assert df_upload["full_path"].iloc[0] == "sample_file_001.py"
    assert df_upload["task_id"].iloc[0] == task_id
    assert df_upload["user_id"].iloc[0] == user_id

    # オブジェクトアップロード
    df_upload = db_access_service.insert_upload_object("sample_folder_001", "folder", "sample_folder_001", task_id, user_id)

    # アップロードオブジェクトが正常に作成されていること(folder)
    assert df_upload["upload_object_name"].iloc[0] == "sample_folder_001"
    assert df_upload["upload_object_type"].iloc[0] == "folder"
    assert df_upload["full_path"].iloc[0] == "sample_folder_001"
    assert df_upload["task_id"].iloc[0] == task_id
    assert df_upload["user_id"].iloc[0] == user_id

    # オブジェクトの配列作成
    object_info_list = []
    # 登録オブジェクトの辞書作成
    object_info_list.append({"upload_object_name": "sample_file_002.py", "upload_object_type": "file", "full_path": "sample_folder_001/sample_file_002.py"})
    object_info_list.append({"upload_object_name": "sample_file_003.py", "upload_object_type": "file", "full_path": "sample_folder_001/sample_file_003.py"})
    object_info_list.append({"upload_object_name": "sample_file_004.py", "upload_object_type": "file", "full_path": "sample_folder_001/sample_file_004.py"})
    # 複数オブジェクトの同時登録
    db_access_service.insert_upload_objects(object_info_list, task_id, user_id)
    # 複数階層のフォルダをアップロード
    df_upload = db_access_service.insert_upload_object("sample_folder_002", "folder", "sample_folder_002", task_id, user_id)
    df_upload = db_access_service.insert_upload_object("sample_folder_003", "folder", "sample_folder_002/sample_folder_003", task_id, user_id)
    df_upload = db_access_service.insert_upload_object("sample_folder_004", "folder", "sample_folder_002/sample_folder_003/sample_folder_004", task_id, user_id)
    db_access_service.insert_upload_object("sample_file_004.py", "file", "sample_folder_002/sample_folder_003/sample_folder_004/sample_file_004.py", task_id, user_id)

    # アップロードされたオブジェクトの一覧を取得
    df_upload_object = db_access_service.select_upload_object_by_task_id(task_id)

    # 正しくオブジェクトが登録されていること
    assert len(df_upload_object) == 9

    # アップロードしたオブジェクトの削除
    df_delete = db_access_service.delete_upload_object(task_id)

    # 正しくオブジェクトが削除されていること
    assert len(df_delete) == 9

    # 作成したタスクの削除
    df_delete_task = db_access_service.delete_task(task_id)

    # 正しくタスクが削除されていること
    assert len(df_delete_task) == 1


############################################################
## t_result_fileテーブル
############################################################
# 正常系
# タスク新規作成 -> 変換結果ファイル作成 -> タスク&変換結果ファイル削除と一連の流れで動作確認
# NOTE テスト中で作成したデータは最終的に削除されるので, テストが正常終了する限りは既存のデータに影響はない想定
def test_result_file_operation_scenario_OK_01():
    ## テストデータ用意
    # ユーザID
    user_id = 99
    # タスク名称
    task_name = "変換結果ファイル操作シナリオテスト"

    # タスク新規作成
    df_task = db_access_service.insert_task(task_name, user_id)
    # 作成したタスクのタスクIDを取得
    task_id = int(df_task["task_id"].iloc[0])
    # 変換結果ファイル登録
    df_result = db_access_service.insert_result_file("sample_file_001.md", 101, task_id, user_id)

    # 変換結果ファイルが正常に登録されていること
    assert df_result["result_file_name"].iloc[0] == "sample_file_001.md"
    assert df_result["original_file_id"].iloc[0] == 101
    assert df_result["task_id"].iloc[0] == task_id
    assert df_result["user_id"].iloc[0] == user_id

    # 変換結果ファイル登録
    db_access_service.insert_result_file("sample_file_002.md", 102, task_id, user_id)
    db_access_service.insert_result_file("sample_file_003.md", 103, task_id, user_id)
    db_access_service.insert_result_file("sample_file_004.md", 104, task_id, user_id)
    # 変換結果ファイルの一覧を取得
    df_result_file = db_access_service.select_result_file_by_task_id(task_id)

    # 正しく変換結果ファイルが登録されていること
    assert len(df_result_file) == 4

    # 変換ファイルの配列作成
    file_info_list = []
    # 変換ファイルの辞書作成
    file_info_list.append({"result_file_name": "sample_file_005.md", "original_file_id": 105})
    file_info_list.append({"result_file_name": "sample_file_006.md", "original_file_id": 106})
    file_info_list.append({"result_file_name": "sample_file_007.md", "original_file_id": 107})
    file_info_list.append({"result_file_name": "sample_file_008.md", "original_file_id": 108})
    file_info_list.append({"result_file_name": "sample_file_009.md", "original_file_id": 109})
    # 複数データの同時登録
    db_access_service.insert_result_files(file_info_list, task_id, user_id)
    # 変換結果ファイルの一覧を取得
    df_result_file = db_access_service.select_result_file_by_task_id(task_id)

    # 正しく変換結果ファイルが登録されていること
    assert len(df_result_file) == 9

    # 作成した変換結果ファイルの削除
    df_delete = db_access_service.delete_result_file(task_id)

    # 正しく変換結果ファイルが削除されていること
    assert len(df_delete) == 9

    # 作成したタスクの削除
    df_delete_task = db_access_service.delete_task(task_id)

    # 正しくタスクが削除されていること
    assert len(df_delete_task) == 1
