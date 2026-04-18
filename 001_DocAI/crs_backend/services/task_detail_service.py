import pandas as pd
from azure.core.exceptions import ResourceNotFoundError
from azure_operation import azure_ai_operation_service, azure_files_operation_service
from common import common_validate
from common.constant import FileShareName, TaskState
from database import db_access_service
from fastapi import BackgroundTasks, File
from models import TaskDetailResponse


def create_new_task(task_name: str, user_id: int) -> TaskDetailResponse:
    """
    タスク新規作成処理

    Args
    -----------------
    - task_name: str,                   タスク名称
    - user_id: int,                     ユーザID

    Returns
    -----------------
    - response: TaskDetailResponse,     レスポンス

    """
    # タスク名称が条件を満たしているか確認
    error_list = common_validate.length_validation("タスク名称", task_name, 1, 255)
    # エラーが検知された場合
    if len(error_list) > 0:
        return TaskDetailResponse(status=200, messages=error_list, task_detail={})

    # DBにタスク作成
    df = db_access_service.insert_task(task_name, user_id)
    # 作成したタスク情報を辞書に変換
    task_dict = df.iloc[0].to_dict()
    # レスポンス返却
    return TaskDetailResponse(status=200, messages=[], task_detail=task_dict)


def get_task_info(task_id: int) -> TaskDetailResponse:
    """
    タスク状態取得処理

    Args
    -----------------
    - task_id: int,                     タスクID

    Returns
    -----------------
    - response: TaskDetailResponse,     レスポンス

    """
    # DBに接続してタスク情報を取得
    df = db_access_service.select_task_by_task_id(task_id)
    # タスク情報が取得できなかった場合
    if df.empty:
        # 該当のエラーメッセージを取得
        error_dict = db_access_service.select_message("msg-E-0005")
        # エラーを返却
        return TaskDetailResponse(status=200, messages=[error_dict], task_detail={})

    # 入れ物用意
    message_list = []
    display_object_info = []
    # 取得したタスク情報を辞書に変換
    task_dict = df.iloc[0].to_dict()
    # タスク状態を取得
    task_state = task_dict["task_state_id"]
    # タスク状態ごとに処理
    match task_state:
        # タスク状態が翻訳中の場合
        case TaskState.DOING.value:
            # 登録データテーブルからタスクIDに紐づく表示情報を取得
            display_object_info = generate_display_info(task_id, task_state)
        # タスク状態が翻訳失敗の場合
        case TaskState.RERUN.value:
            # 該当のエラーメッセージを取得
            error_dict = db_access_service.select_message("msg-E-0010")
            # メッセージに追加
            message_list.append(error_dict)
        # タスク状態が翻訳済の場合
        case TaskState.DONE.value:
            # 登録データテーブルからタスクIDに紐づく表示情報を取得
            # ※変換結果ファイルの取得は処理時間がかかるため別途get_task_detailで取得する
            display_object_info = generate_display_info(task_id, TaskState.DOING.value)
    # レスポンス返却
    return TaskDetailResponse(status=200, messages=message_list, task_detail=task_dict, display_object_info=display_object_info)


def get_task_detail(task_id: int) -> TaskDetailResponse:
    """
    翻訳済みのタスクに紐づくファイルの情報を取得する処理

    Args
    -----------------
    - task_id: int,                     タスクID

    Returns
    -----------------
    - response: TaskDetailResponse,     レスポンス

    """
    # DBに接続してタスク情報を取得
    df = db_access_service.select_task_by_task_id(task_id)
    # タスク情報が取得できなかった場合
    if df.empty:
        # 該当のエラーメッセージを取得
        error_dict = db_access_service.select_message("msg-E-0005")
        # エラーを返却
        return TaskDetailResponse(status=200, messages=[error_dict], task_detail={})

    # 取得したタスク情報を辞書に変換
    task_dict = df.iloc[0].to_dict()
    # タスクの状態を取得
    task_state = task_dict["task_state_id"]
    # 対象のタスクが翻訳済以外の場合
    if task_state != TaskState.DONE.value:
        # 該当のエラーメッセージを取得
        error_dict = db_access_service.select_message("msg-E-0005")
        # エラーを返却
        return TaskDetailResponse(status=200, messages=[error_dict], task_detail=task_dict)

    # 登録データテーブルからタスクIDに紐づく表示情報を取得
    display_object_info = generate_display_info(task_id, task_state)
    # レスポンス返却
    return TaskDetailResponse(status=200, messages=[], task_detail=task_dict, display_object_info=display_object_info)


def update_task_name(task_id: int, task_name: str) -> TaskDetailResponse:
    """
    タスク名称更新処理

    Args
    -----------------
    - task_id: int,                     タスクID
    - task_name: str,                   更新するタスク名称

    Returns
    -----------------
    - response: TaskDetailResponse,     レスポンス

    """
    # タスク名称が条件を満たしているか確認
    error_list = common_validate.length_validation("タスク名称", task_name, 1, 255)
    # エラーが検知された場合
    if len(error_list) > 0:
        return TaskDetailResponse(status=200, messages=error_list, task_detail={})

    # DBに接続して該当するタスクIDのタスク名を更新
    df = db_access_service.update_task_name(task_id, task_name)
    # タスク名称が更新されなかった場合
    if df.empty:
        # 該当のエラーメッセージを取得
        error_dict = db_access_service.select_message("msg-E-0003")
        # エラーを返却
        return TaskDetailResponse(status=200, messages=[error_dict], task_detail={})
    # 更新したタスク情報を辞書に変換
    task_dict = df.iloc[0].to_dict()
    # レスポンス返却
    return TaskDetailResponse(status=200, messages=[], task_detail=task_dict)


def delete_task(task_id: int) -> TaskDetailResponse:
    """
    タスク削除処理
    削除対象のタスクに紐づくアップロードデータ, 変換データも同時に削除する

    Args
    -----------------
    - task_id: int,                     タスクID

    Returns
    -----------------
    - response: TaskDetailResponse,     レスポンス

    """
    ## 対象のタスクが存在するか確認
    # 削除対象のタスク情報取得
    df = db_access_service.select_task_by_task_id(task_id)
    # タスク情報が取得できなかった場合
    if df.empty:
        # 該当のエラーメッセージを取得
        error_dict = db_access_service.select_message("msg-E-0005")
        # エラーを返却
        return TaskDetailResponse(status=200, messages=[error_dict], task_detail={})

    ## 対象のタスクが削除可能か確認
    # 取得したタスク情報を辞書に変換
    task_dict = df.iloc[0].to_dict()
    # タスクの状態を取得
    task_state = task_dict["task_state_id"]
    # 削除対象のタスクが変換実行中の場合
    if task_state == TaskState.DOING.value:
        # 該当のエラーメッセージを取得
        error_dict = db_access_service.select_message("msg-E-0006")
        # エラーを返却
        return TaskDetailResponse(status=200, messages=[error_dict], task_detail={})

    # DBに接続してt_taskテーブルから該当するタスクIDのタスクを削除
    df = db_access_service.delete_task(task_id)
    if df.empty:
        ## タスクが削除されなかった場合
        # 該当のエラーメッセージを取得
        error_dict = db_access_service.select_message("msg-E-0004")
        # エラーを返却
        return TaskDetailResponse(status=200, messages=[error_dict], task_detail={})
    else:
        ## タスクが削除できた場合のみ配下のデータを削除する
        # DBに接続してt_upload_objectテーブルから該当するタスクIDのオブジェクトを削除
        df_upload = db_access_service.delete_upload_object(task_id)
        # DBに接続してt_result_fileテーブルから該当するタスクIDのファイルを削除
        df_result = db_access_service.delete_result_file(task_id)
        # 削除対象のresult_fileが存在する場合のみ処理
        if len(df_result) > 0:
            # 削除したタスクのユーザID取得
            user_id = df["user_id"].values[0]
            # ファイル共有上のファイルを削除
            try:
                azure_files_operation_service.delete_task_directory(user_id, task_id)
            except ResourceNotFoundError as e:
                # ファイルの削除に失敗した場合はログに出力
                print(f"ファイル共有のデータ削除に失敗しました。ユーザID : {user_id}, タスクID : {task_id}, エラー : {str(e)}")

    # 削除したタスク情報を辞書に変換
    task_dict = df.iloc[0].to_dict()
    # 表示するメッセージを取得
    message_dict = db_access_service.select_message("msg-I-0001")
    # 削除したタスクの名称をセット
    message_dict["message"] = message_dict["message"].format(task_dict["task_name"])
    # レスポンス返却
    return TaskDetailResponse(status=200, messages=[message_dict], task_detail=task_dict)


def translate_files(target_file_list: list[File], metadata_list: list[dict], task_id: int, user_id: int, background_tasks: BackgroundTasks) -> TaskDetailResponse:
    """
    アップロードされたファイルをAIに送信して変換する処理

    Args
    -----------------
    - target_file_list: list[File],         変換対象のファイル情報からなる配列
        - File.filename: str,               ファイルのフルパス
        - File.file.read(): str,            ファイルの中身
    - metadata: list[dict],                 変換対象のオブジェクト情報(Metadata)からなる配列
    - task_id: int,                         タスクID
    - user_id: int,                         ユーザID
    - background_tasks: BackgroundTasks,    バックグラウンドタスク

    Returns
    -----------------
    - response: TaskDetailResponse,         レスポンス

    """
    ## アップロードされたファイル情報をDBに登録する
    try:
        ## 変換対象のファイルが存在するか確認
        # ファイルのデータのみ抽出
        file_list = [file for file in metadata_list if file["upload_object_type"] == "file"]
        # 変換対象のファイルのみ抽出
        TF_list = common_validate.filter_data(file_list)
        # 変換可能なファイルが存在しなかった場合
        if not (True in TF_list):
            # 該当のエラーメッセージを取得
            error_dict = db_access_service.select_message("msg-E-0009")
            # レスポンス返却
            return TaskDetailResponse(status=200, messages=[error_dict], task_detail={})
        else:
            # 変換対象のファイル情報をフィルタ
            target_file_list = [file for file, tf in zip(target_file_list, TF_list) if tf]
        # フォルダを含めて再度フィルタ
        TF_list = common_validate.filter_data(metadata_list)
        # 変換対象外のファイルを削除
        metadata_list = [md for md, tf in zip(metadata_list, TF_list) if tf]

        ## 対象のタスクが存在するか確認
        # ファイル登録対象のタスク情報取得
        df = db_access_service.select_task_by_task_id(task_id)
        # タスク情報が取得できなかった場合
        if df.empty:
            # 該当のエラーメッセージを取得
            error_dict = db_access_service.select_message("msg-E-0005")
            # エラーを返却
            return TaskDetailResponse(status=200, messages=[error_dict], task_detail={})

        ## 対象のタスクが翻訳可能か確認
        # 取得したタスク情報を辞書に変換
        task_dict = df.iloc[0].to_dict()
        # タスクの状態を取得
        task_state = task_dict["task_state_id"]
        # ファイル登録対象のタスクが翻訳中 or 翻訳済の場合
        if task_state in [TaskState.DOING.value, TaskState.DONE.value]:
            # 該当のエラーメッセージを取得
            error_dict = db_access_service.select_message("msg-E-0007")
            # エラーを返却
            return TaskDetailResponse(status=200, messages=[error_dict], task_detail={})

        # t_upload_objectテーブルに登録
        df_upload = db_access_service.insert_upload_objects(metadata_list, task_id, user_id)
    # ここまでの処理でエラーになった場合
    except Exception as e:
        # エラーが発生した場合はログに出力
        print(f"変換対象のファイル登録処理でエラーが発生しました。ユーザID : {user_id}, タスクID : {task_id}, エラー : {str(e)}")
        # 該当のエラーメッセージを取得
        error_dict = db_access_service.select_message("msg-E-0007")
        # レスポンス返却
        return TaskDetailResponse(status=200, messages=[error_dict], task_detail={})

    ## 変換対象データの作成
    # フルパスをキーに, オブジェクトIDを値に持つ辞書を作成
    path_to_id_dict = df_upload.set_index("full_path")["upload_object_id"].to_dict()
    # 入れ物用意
    upload_file_dict = {}
    # 全ての変換対象ファイルについて処理
    for target_file in target_file_list:
        # オブジェクトIDをキーに, ファイルの中身を値に持つ辞書を作成
        upload_file_dict[int(path_to_id_dict[target_file.filename])] = target_file.file.read()
    # アップロードされたオブジェクトからファイルのみ抽出
    df_upload_file = df_upload[df_upload["upload_object_type"].isin(["file"])]
    # ファイル変換を行う非同期処理をバックグラウンドで実行
    background_tasks.add_task(async_translate_file, df_upload_file, upload_file_dict, task_id, user_id)

    # タスクの状態を更新
    df_task = db_access_service.update_task_state(task_id, TaskState.DOING.value)
    # 更新したタスクの情報を辞書に変換
    task_dict = df_task.iloc[0].to_dict()
    # 該当メッセージを取得
    message_dict = db_access_service.select_message("msg-I-0002")
    # レスポンス返却
    return TaskDetailResponse(status=200, messages=[message_dict], task_detail=task_dict)


def async_translate_file(target_file_df: pd.DataFrame, upload_file_dict: dict[int, str], task_id: int, user_id: int):
    """
    アップロードされたファイルの情報とファイルの中身から, モデルにデータを送信して変換結果を取得するバックグラウンド処理

    Args
    -----------------
    - target_file_df: pd.DataFrame,     変換対象ファイルのアップロードオブジェクトテーブル情報
    - upload_file_dict: dict,           変換対象ファイルの中身  ex) {1: "import datetime ... def function(): ...", ... }
    - task_id: int,                     タスクID
    - user_id: int,                     ユーザID

    """
    ## 変換処理をバックグラウンドで実行
    try:
        # 入れ物用意
        file_info_list = []
        result_data_list = []
        # 変換対象ファイルごとに処理
        for row in target_file_df.itertuples():
            # アップロードされたファイルのオブジェクトIDを取得
            object_id = int(row.upload_object_id)
            # ファイルの中身を取得
            code = upload_file_dict[object_id].decode("utf-8")
            # コード変換処理を実行
            result_text = azure_ai_operation_service.translate_code(code)
            # 変換結果の辞書を作成
            file_dict = {}
            result_dict = {}
            # 変換結果を登録
            file_dict["result_file_name"] = str(object_id) + ".md"
            file_dict["original_file_id"] = object_id
            result_dict["object_id"] = object_id
            result_dict["text"] = result_text
            # 配列に追加
            file_info_list.append(file_dict)
            result_data_list.append(result_dict)
        # 変換結果のファイルをファイル共有にアップロード
        azure_files_operation_service.upload_multiple_files(result_data_list, user_id, task_id, FileShareName.RESULT.value)
        # 変換結果のデータをt_result_fileテーブルに登録
        db_access_service.insert_result_files(file_info_list, task_id, user_id)
        # すべてのファイル変換処理が完了した場合はタスク状態をDoneに更新
        db_access_service.update_task_state(task_id, TaskState.DONE.value)
    except Exception as e:
        # ファイル変換処理中にエラーが発生した場合はログに出力
        print(f"ファイル変換処理でエラーが発生しました。ユーザID : {user_id}, タスクID : {task_id}, エラー : {str(e)}")
        # 変換の途中で失敗した場合は登録されているデータの状態が確認できないため, 不整合が起きないように変換処理中に登録したデータをすべて削除する
        try:
            # t_upload_objectテーブルのデータを削除
            db_access_service.delete_upload_object(task_id)
            # t_result_fileテーブルのデータを削除
            db_access_service.delete_result_file(task_id)
            # ファイル共有のデータを削除
            azure_files_operation_service.delete_task_directory(user_id, task_id, FileShareName.RESULT.value)
        except Exception as err:
            # 不完全データの削除中にエラーが発生した場合
            print(f"不完全データの削除処理でエラーが発生しました。DB、およびファイル共有のデータを確認してください。ユーザID : {user_id}, タスクID : {task_id}, エラー : {str(err)}")
        finally:
            # タスク状態を中断に更新する
            db_access_service.update_task_state(task_id, TaskState.RERUN.value)


def generate_display_info(task_id: int, task_state: int) -> list[dict]:
    """
    指定されたtask_idを持つタスクに紐づく表示用オブジェクト情報からなる配列を生成する

    Args
    -----------------
    - task_id: int,                             タスクID
    - task_state: int,                          タスク状態

    Returns
    -----------------
    - display_object_info: list[dict],          表示用オブジェクト情報からなる配列

    """
    ## タスクの状態ごとに処理
    match task_state:
        # タスクが変換中の場合
        case TaskState.DOING.value:
            # 登録データテーブルからタスクIDに紐づく表示情報を取得
            df_object = db_access_service.select_upload_object_by_task_id(task_id)
            # レスポンスの形式を合わせるために列追加
            df_object["result_text"] = ""
            # データフレームを辞書形式の配列に変換して返却
            return df_object.to_dict(orient="records")
        # タスクが変換済の場合
        case TaskState.DONE.value:
            # 登録データテーブルからタスクIDに紐づく表示情報を取得
            df_object = db_access_service.select_upload_object_by_task_id(task_id)
            # 念のため型変換
            df_object["user_id"] = df_object["user_id"].astype(int)
            df_object["task_id"] = df_object["task_id"].astype(int)
            df_object["upload_object_id"] = df_object["upload_object_id"].astype(int)
            # 変換結果データ用列を作成
            df_object["result_text"] = ""
            # ファイル行のみ抽出
            df_file = df_object[df_object["upload_object_type"] == "file"]
            # 変換結果のファイル行ごとに処理
            for row in df_file.itertuples():
                # ファイル共有から紐づく変換結果のファイルの中身を取得
                result_text = azure_files_operation_service.download_file(row.user_id, row.task_id, row.upload_object_id)
                # 取得した変換結果をデータフレームにセット
                df_object.loc[df_object["upload_object_id"] == row.upload_object_id, "result_text"] = result_text
            # データフレームを辞書形式の配列に変換して返却
            return df_object.to_dict(orient="records")
