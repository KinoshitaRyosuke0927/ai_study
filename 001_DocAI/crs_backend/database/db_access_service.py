from datetime import datetime

import pandas as pd
from sqlalchemy import delete, text

from common.constant import TaskState
from database.db_access_info import db, engine
from database.db_models import *


############################################################
## m_messageテーブル
############################################################
def select_message(message_id: int) -> dict[str, str]:
    """
    m_messageテーブルから該当するメッセージIDを持つメッセージを取得する

    Args
    -----------------
    - message_id: int,              メッセージID

    Returns
    -----------------
    - message_dict: dict,           取得したメッセージ情報

    """
    # SQLQueryの実行
    df = pd.read_sql(text("SELECT * FROM [dbo].[m_message] WHERE message_id = :message_id"), con=engine, params={"message_id": message_id})
    # 辞書に変換して返却
    return df.iloc[0].to_dict()


############################################################
## m_userテーブル
############################################################
def select_user(mail_address: str) -> pd.DataFrame:
    """
    m_userテーブルから該当するメールアドレスを持つユーザの情報を取得する

    Args
    -----------------
    - mail_address: str,            ユーザのメールアドレス

    Returns
    -----------------
    - df: pd.DataFrame,             取得したユーザ情報

    """
    # SQLQueryの実行
    df = pd.read_sql(text("SELECT * FROM [dbo].[m_user] WHERE mail_address = :mail_address"), con=engine, params={"mail_address": mail_address})
    # パスワードについては照合のためByte文字に変換
    df["password"] = df["password"].astype(bytes)

    return df


############################################################
## t_taskテーブル
############################################################
def select_task_by_user_id(user_id: int) -> pd.DataFrame:
    """
    t_taskテーブルから該当するユーザIDを持つタスクすべての情報を取得する

    Args
    -----------------
    - user_id: int,                 ユーザID

    Returns
    -----------------
    - df: pd.DataFrame,             取得したタスク情報

    """
    # SQLQueryの実行
    df = pd.read_sql(text("SELECT * FROM [dbo].[t_task] WHERE user_id = :user_id"), con=engine, params={"user_id": user_id})

    return df


def select_task_by_task_id(task_id: int) -> pd.DataFrame:
    """
    t_taskテーブルから該当するタスクIDを持つタスクの情報を取得する

    Args
    -----------------
    - task_id: int,                 タスクID

    Returns
    -----------------
    - df: pd.DataFrame,             取得したタスク情報

    """
    # SQLQueryの実行
    df = pd.read_sql(text("SELECT * FROM [dbo].[t_task] WHERE task_id = :task_id"), con=engine, params={"task_id": task_id})

    return df


def insert_task(task_name: str, user_id: int) -> pd.DataFrame:
    """
    t_taskテーブルに新しいタスクを作成する

    Args
    -----------------
    - task_name: str,                   作成するタスク名称
    - user_id: int,                     タスクを作成したユーザのユーザID

    Returns
    -----------------
    - df_task: pd.DataFrame,            DBにINSERTしたタスク情報からなるDataFrame

    """
    # INSERTするデータを作成
    task = TTask(task_name=task_name, task_state_id=TaskState.WAITING.value, update_at=datetime.now(), user_id=user_id)

    ## DB処理
    try:
        # INSERT処理実行
        db.add(task)
        # 問題なければコミット
        db.commit()
        # 自動採番された値を反映
        db.refresh(task)
    except Exception as e:
        # エラーが発生した場合はロールバック
        db.rollback()
        raise e
    finally:
        # セッションを閉じる
        db.close()

    # INSERTしたタスク情報をDataFrameに成形
    df_task = pd.DataFrame(
        [
            {"task_id": task.task_id, "task_name": task.task_name, "task_state_id": task.task_state_id, "update_at": task.update_at, "user_id": task.user_id}
        ]
    )

    return df_task


def update_task_name(task_id: int, task_name: str) -> pd.DataFrame:
    """
    t_taskテーブルに存在するタスクのタスク名称を更新する

    Args
    -----------------
    - task_id: int,                     タスク名称を更新するタスクのタスクID
    - task_name: str,                   更新するタスク名称

    Returns
    -----------------
    - df_task: pd.DataFrame,            UPDATEしたタスク情報からなるDataFrame

    """
    ## DB処理
    try:
        # 更新するタスク情報を取得
        task = db.get(TTask, task_id)
        # 対象のデータが存在しない場合
        if task is None:
            # 空のDataFrameを返却
            return pd.DataFrame()

        # タスク名称を更新
        task.task_name = task_name
        # タスクの更新時間を更新
        task.update_at = datetime.now()
        # 問題なければコミット
        db.commit()
        # 更新された値を反映
        db.refresh(task)
    except Exception as e:
        # エラーが発生した場合はロールバック
        db.rollback()
        raise e
    finally:
        # セッションを閉じる
        db.close()

    # UPDATEしたタスク情報をDataFrameに成形
    df_task = pd.DataFrame(
        [
            {"task_id": task.task_id, "task_name": task.task_name, "task_state_id": task.task_state_id, "update_at": task.update_at, "user_id": task.user_id}
        ]
    )

    return df_task


def update_task_state(task_id: int, task_state: int) -> pd.DataFrame:
    """
    t_taskテーブルに存在するタスクのタスク状態を更新する

    Args
    -----------------
    - task_id: int,                     タスク状態を更新するタスクのタスクID
    - task_state: int,                  更新するタスク状態

    Returns
    -----------------
    - df_task: pd.DataFrame,            UPDATEしたタスク情報からなるDataFrame

    """
    ## DB処理
    try:
        # 更新するタスク情報を取得
        task = db.get(TTask, task_id)
        # 対象のデータが存在しない場合
        if task is None:
            # 空のDataFrameを返却
            return pd.DataFrame()

        # タスク状態を更新
        task.task_state_id = task_state
        # タスクの更新時間を更新
        task.update_at = datetime.now()
        # 問題なければコミット
        db.commit()
        # 更新された値を反映
        db.refresh(task)
    except Exception as e:
        # エラーが発生した場合はロールバック
        db.rollback()
        raise e
    finally:
        # セッションを閉じる
        db.close()

    # UPDATEしたタスク情報をDataFrameに成形
    df_task = pd.DataFrame(
        [
            {"task_id": task.task_id, "task_name": task.task_name, "task_state_id": task.task_state_id, "update_at": task.update_at, "user_id": task.user_id}
        ]
    )

    return df_task


def delete_task(task_id: int) -> pd.DataFrame:
    """
    t_taskテーブルに存在するタスクを削除する

    Args
    -----------------
    - task_id: int,                     削除するタスクのタスクID

    Returns
    -----------------
    - df_task: pd.DataFrame,            DELETEしたタスク情報からなるDataFrame

    """
    ## DB処理
    try:
        # 削除するタスク情報を取得
        task = db.get(TTask, task_id)
        # 対象のデータが存在しない場合
        if task is None:
            # 空のDataFrameを返却
            return pd.DataFrame()

        # タスクを削除
        db.delete(task)
        # 問題なければコミット
        db.commit()
    except Exception as e:
        # エラーが発生した場合はロールバック
        db.rollback()
        raise e
    finally:
        # セッションを閉じる
        db.close()

    # DELETEしたタスク情報をDataFrameに成形
    df_task = pd.DataFrame(
        [
            {"task_id": task.task_id, "task_name": task.task_name, "task_state_id": task.task_state_id, "update_at": task.update_at, "user_id": task.user_id}
        ]
    )

    return df_task


############################################################
## t_upload_objectテーブル
############################################################
def select_upload_object_by_task_id(task_id: int) -> pd.DataFrame:
    """
    t_upload_objectテーブルから該当するタスクIDを持つアップロードオブジェクトの情報を取得する

    Args
    -----------------
    - task_id: int,                 タスクID

    Returns
    -----------------
    - df: pd.DataFrame,             取得したアップロードオブジェクト情報

    """
    # SQLQueryの実行
    df = pd.read_sql(text("SELECT * FROM [dbo].[t_upload_object] WHERE task_id = :task_id ORDER BY upload_object_id ASC"), con=engine, params={"task_id": task_id})

    return df


def insert_upload_object(upload_object_name: str, upload_object_type: str, full_path: str, task_id: int, user_id: int) -> pd.DataFrame:
    """
    t_upload_objectテーブルに新しいオブジェクトを追加する

    Args
    -----------------
    - upload_object_name: str,          追加するオブジェクト名称
    - upload_object_type: str,          追加するオブジェクトのタイプ(file/folder)
    - full_path: str,                   追加するオブジェクトのフルパス
    - task_id: int,                     オブジェクトを追加したタスクのタスクID
    - user_id: int,                     オブジェクトを追加したユーザのユーザID

    Returns
    -----------------
    - df_object: pd.DataFrame,          DBにINSERTしたオブジェクト情報からなるDataFrame

    """
    # INSERTするデータを作成
    object = TUploadObject(
        upload_object_name=upload_object_name,
        upload_object_type=upload_object_type,
        full_path=full_path,
        task_id=task_id,
        user_id=user_id,
    )

    ## DB処理
    try:
        # INSERT処理実行
        db.add(object)
        # 問題なければコミット
        db.commit()
        # 自動採番された値を反映
        db.refresh(object)
    except Exception as e:
        # エラーが発生した場合はロールバック
        db.rollback()
        raise e
    finally:
        # セッションを閉じる
        db.close()

    # INSERTしたオブジェクト情報をDataFrameに成形
    df_object = pd.DataFrame(
        [
            {
                "upload_object_id": object.upload_object_id,
                "upload_object_name": object.upload_object_name,
                "upload_object_type": object.upload_object_type,
                "full_path": object.full_path,
                "task_id": object.task_id,
                "user_id": object.user_id,
            }
        ]
    )

    return df_object


def insert_upload_objects(object_info_list: list[dict[str, int | str]], task_id: int, user_id: int) -> pd.DataFrame:
    """
    t_upload_objectテーブルに複数のオブジェクトを一括で追加する
    ※ object_info_listの要素にはfile_sizeも存在するがここでは使用しない

    Args
    -----------------
    - object_info_list: list[dict],         追加するオブジェクト情報のリスト ex) [{"upload_object_name": "sample.py", "upload_object_type": "file, "full_path": "src/sample.py"}, ...]
    - task_id: int,                         オブジェクトを追加したタスクのタスクID
    - user_id: int,                         オブジェクトを追加したユーザのユーザID

    Returns
    -----------------
    - df_objects: pd.DataFrame,             DBにINSERTしたオブジェクト情報からなるDataFrame

    """
    # INSERTするデータのリストを作成
    objects = [
        TUploadObject(
            upload_object_name=object_info["upload_object_name"],
            upload_object_type=object_info["upload_object_type"],
            full_path=object_info["full_path"],
            task_id=task_id,
            user_id=user_id,
        )
        for object_info in object_info_list
    ]

    ## DB処理
    try:
        # 一括INSERT処理実行
        db.add_all(objects)
        # 問題なければコミット
        db.commit()
        # 自動採番された値を反映
        for object in objects:
            db.refresh(object)
    except Exception as e:
        # エラーが発生した場合はロールバック
        db.rollback()
        raise e
    finally:
        # セッションを閉じる
        db.close()

    # INSERTしたオブジェクト情報をDataFrameに成形
    df_objects = pd.DataFrame(
        [
            {
                "upload_object_id": object.upload_object_id,
                "upload_object_name": object.upload_object_name,
                "upload_object_type": object.upload_object_type,
                "full_path": object.full_path,
                "task_id": object.task_id,
                "user_id": object.user_id,
            }
            for object in objects
        ]
    )

    return df_objects


def delete_upload_object(task_id: int) -> pd.DataFrame:
    """
    t_upload_objectテーブルに存在するタスクIDに紐づくデータを削除する

    Args
    -----------------
    - task_id: int,                         削除するアップロードオブジェクトのタスクID

    Returns
    -----------------
    - df_upload_object: pd.DataFrame,       DELETEしたアップロードオブジェクト情報からなるDataFrame

    """
    ## DB処理
    try:
        # Query作成
        stmt = (
            delete(TUploadObject)
            .where(TUploadObject.task_id == task_id)
            .returning(
                TUploadObject.upload_object_id,
                TUploadObject.upload_object_name,
                TUploadObject.upload_object_type,
                TUploadObject.full_path,
                TUploadObject.task_id,
                TUploadObject.user_id,
            )
        )
        # Query実行
        result = db.execute(stmt)
        # DELETEした情報を取得
        deleted_rows = result.fetchall()
        # 問題なければコミット
        db.commit()
    except Exception as e:
        # エラーが発生した場合はロールバック
        db.rollback()
        raise e
    finally:
        # セッションを閉じる
        db.close()

    # DELETEしたアップロードオブジェクト情報をDataFrameに成形
    df_upload_object = pd.DataFrame(
        deleted_rows,
        columns=["upload_object_id", "upload_object_name", "upload_object_type", "full_path", "task_id", "user_id"]
    )

    return df_upload_object


############################################################
## t_result_fileテーブル
############################################################
def select_result_file_by_task_id(task_id: int) -> pd.DataFrame:
    """
    t_result_fileテーブルから該当するタスクIDを持つ変換結果ファイルの情報を取得する

    Args
    -----------------
    - task_id: int,                 タスクID

    Returns
    -----------------
    - df: pd.DataFrame,             取得した変換結果ファイル情報

    """
    # SQLQueryの実行
    df = pd.read_sql(text("SELECT * FROM [dbo].[t_result_file] WHERE task_id = :task_id"), con=engine, params={"task_id": task_id})

    return df


def insert_result_file(result_file_name: str, original_file_id: int, task_id: int, user_id: int) -> pd.DataFrame:
    """
    t_result_fileテーブルに新しいファイルを追加する

    Args
    -----------------
    - result_file_name: str,            追加するファイル名称
    - original_file_id: str,            追加するファイルの変換元ファイルのID
    - task_id: int,                     オブジェクトを追加したタスクのタスクID
    - user_id: int,                     オブジェクトを追加したユーザのユーザID

    Returns
    -----------------
    - df_file: pd.DataFrame,            DBにINSERTしたファイル情報からなるDataFrame

    """
    # INSERTするデータを作成
    file = TResultFile(
        result_file_name=result_file_name,
        original_file_id=original_file_id,
        task_id=task_id,
        user_id=user_id,
    )

    ## DB処理
    try:
        # INSERT処理実行
        db.add(file)
        # 問題なければコミット
        db.commit()
        # 自動採番された値を反映
        db.refresh(file)
    except Exception as e:
        # エラーが発生した場合はロールバック
        db.rollback()
        raise e
    finally:
        # セッションを閉じる
        db.close()

    # INSERTしたファイル情報をDataFrameに成形
    df_file = pd.DataFrame(
        [
            {
                "result_file_name": file.result_file_name,
                "original_file_id": file.original_file_id,
                "task_id": file.task_id,
                "user_id": file.user_id,
            }
        ]
    )

    return df_file


def insert_result_files(file_info_list: list[dict[str, int | str]], task_id: int, user_id: int) -> pd.DataFrame:
    """
    t_result_fileテーブルに複数のファイルを一括で追加する

    Args
    -----------------
    - file_info_list: list[dict],       追加するファイル情報のリスト ex) [{"result_file_name": "1095.md", "original_file_id": 1095}, ...]
    - task_id: int,                     オブジェクトを追加したタスクのタスクID
    - user_id: int,                     オブジェクトを追加したユーザのユーザID

    Returns
    -----------------
    - df_files: pd.DataFrame,           DBにINSERTしたファイル情報からなるDataFrame

    """
    # INSERTするデータのリストを作成
    files = [
        TResultFile(
            result_file_name=file_info["result_file_name"],
            original_file_id=file_info["original_file_id"],
            task_id=task_id,
            user_id=user_id,
        )
        for file_info in file_info_list
    ]

    ## DB処理
    try:
        # 一括INSERT処理実行
        db.add_all(files)
        # 問題なければコミット
        db.commit()
        # 自動採番された値を反映
        for file in files:
            db.refresh(file)
    except Exception as e:
        # エラーが発生した場合はロールバック
        db.rollback()
        raise e
    finally:
        # セッションを閉じる
        db.close()

    # INSERTしたファイル情報をDataFrameに成形
    df_files = pd.DataFrame(
        [
            {
                "result_file_id": file.result_file_id,
                "result_file_name": file.result_file_name,
                "original_file_id": file.original_file_id,
                "task_id": file.task_id,
                "user_id": file.user_id,
            }
            for file in files
        ]
    )

    return df_files


def delete_result_file(task_id: int) -> pd.DataFrame:
    """
    t_result_fileテーブルに存在するタスクIDに紐づくデータを削除する

    Args
    -----------------
    - task_id: int,                     削除する変換結果ファイルのタスクID

    Returns
    -----------------
    - df_result_file: pd.DataFrame,     DELETEした変換結果ファイル情報からなるDataFrame

    """
    ## DB処理
    try:
        # Query作成
        stmt = (
            delete(TResultFile)
            .where(TResultFile.task_id == task_id)
            .returning(
                TResultFile.result_file_id,
                TResultFile.result_file_name,
                TResultFile.original_file_id,
                TResultFile.task_id,
                TResultFile.user_id,
            )
        )
        # Query実行
        result = db.execute(stmt)
        # DELETEした情報を取得
        deleted_rows = result.fetchall()
        # 問題なければコミット
        db.commit()
    except Exception as e:
        # エラーが発生した場合はロールバック
        db.rollback()
        raise e
    finally:
        # セッションを閉じる
        db.close()

    # DELETEした変換結果ファイル情報をDataFrameに成形
    df_result_file = pd.DataFrame(
        deleted_rows,
        columns=["result_file_id", "result_file_name", "original_file_id", "task_id", "user_id"]
    )

    return df_result_file
