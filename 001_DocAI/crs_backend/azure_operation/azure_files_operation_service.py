from azure.core.exceptions import ResourceExistsError
from azure.storage.fileshare import ShareServiceClient
from concurrent.futures import ThreadPoolExecutor, as_completed

from azure_operation.azure_constant import AZURE_STORAGE_ACCOUNT_KEY, AZURE_STORAGE_ACCOUNT_NAME, TENANT_NAME
from common.constant import FileShareName, MAX_FILE_UPLOAD_NUM


def upload_multiple_files(file_data_list: list[dict[int, str]], user_id: int, task_id: int, target_share_name: str = FileShareName.RESULT.value):
    """
    入力された文字列をファイル形式に変換してAzure Filesにアップロードする処理の並列化関数

    Args
    -----------------
    - file_data_list: list[dict],       Azure Filesにアップロードするファイルの中身からなる配列 ex) [{"object_id": 1, "text": "# テスト \n ## 項目 ... \n"}, ...]
    - user_id: int,                     アップロードするユーザのユーザID
    - task_id: int,                     アップロード対象のファイルが属するタスクID
    - target_share_name: str,           アップロードする対象のファイル共有名称

    """
    # 複数ファイルを同時にアップロード
    with ThreadPoolExecutor(max_workers=MAX_FILE_UPLOAD_NUM) as executor:
        # 入れ物用意
        futures = []
        # アップロード対象のファイルごとに処理
        for file_data in file_data_list:
            # アップロード処理呼び出し
            future = executor.submit(
                upload_file,
                file_data["text"],
                user_id,
                task_id,
                file_data["object_id"],
                target_share_name
            )
            futures.append(future)

        # すべてのアップロード処理が完了していることを確認
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"ファイル共有への並列アップロード処理中にエラーになりました。ユーザID : {user_id}, タスクID : {task_id}, エラー : {str(e)}")


def upload_file(upload_file_text: str, user_id: int, task_id: int, object_id: int, target_share_name: str=FileShareName.RESULT.value):
    """
    入力された文字列をファイル形式に変換してAzure Filesにアップロードする

    Args
    -----------------
    - upload_file_text: str,        Azure Filesにアップロードするファイルの中身
    - user_id: int,                 アップロードするユーザのユーザID
    - task_id: int,                 アップロード対象のファイルが属するタスクID
    - object_id: int,               アップロード対象のファイルのアップロードオブジェクトID
    - target_share_name: str,       アップロードする対象のファイル共有名称

    """
    ## Azure Filesへの接続
    # Azure Filesの接続情報作成
    account_url = f"https://{AZURE_STORAGE_ACCOUNT_NAME}.file.core.windows.net"
    # 接続作成
    service = ShareServiceClient(account_url=account_url, credential=AZURE_STORAGE_ACCOUNT_KEY)
    # ファイル共有のクライアント作成
    share = service.get_share_client(TENANT_NAME)

    ## Directory作成
    # ユーザディレクトリのクライアント作成
    user_dir_client = share.get_directory_client(str(user_id))
    # 対象のディレクトリが存在しない場合は作成
    try:
        user_dir_client.create_directory()
    except ResourceExistsError:
        # 対象のディレクトリがすでに存在する場合は何もしない
        pass
    # アップロード対象のディレクトリのクライアント作成
    upload_dir_client = user_dir_client.get_subdirectory_client(target_share_name)
    # 対象のディレクトリが存在しない場合は作成
    try:
        upload_dir_client.create_directory()
    except ResourceExistsError:
        # 対象のディレクトリがすでに存在する場合は何もしない
        pass
    # タスクディレクトリのクライアント作成
    task_dir_client = upload_dir_client.get_subdirectory_client(str(task_id))
    # 対象のディレクトリが存在しない場合は作成
    try:
        task_dir_client.create_directory()
    except ResourceExistsError:
        # 対象のディレクトリがすでに存在する場合は何もしない
        pass

    ## ファイルアップロード
    # 文字コードを変更
    data = upload_file_text.encode("utf-8")
    # アップロードするファイルの名称設定
    upload_file_name = str(object_id) + ".md" if target_share_name == FileShareName.RESULT.value else str(object_id) + ".py"
    # アップロード対象のファイルのクライアント作成
    file_client = task_dir_client.get_file_client(upload_file_name)
    # ファイル共有上の領域確保
    try:
        file_client.create_file(size=len(data))
    except ResourceExistsError:
        # 同名ファイルがすでに存在する場合は上書きする
        file_client.delete_file()
        file_client.create_file(size=len(data))
    # ファイルをアップロード
    file_client.upload_file(data)


def download_file(user_id: int, task_id: int, object_id: int, target_share_name: str=FileShareName.RESULT.value) -> str:
    """
    Azure Files上のファイルを取得して文字列として返却する
    ※ 取得対象のリソースが存在しない場合はResourceNotFoundErrorになるので呼び出しもとでハンドリングする

    Args
    -----------------
    - user_id: int,                 ダウンロードするユーザのユーザID
    - task_id: int,                 ダウンロード対象のファイルが属するタスクID
    - object_id: int,               ダウンロード対象のファイルのアップロードオブジェクトID
    - target_share_name: str,       ダウンロードする対象のファイル共有名称

    """
    ## Azure Filesへの接続
    # Azure Filesの接続情報作成
    account_url = f"https://{AZURE_STORAGE_ACCOUNT_NAME}.file.core.windows.net"
    # 接続作成
    service = ShareServiceClient(account_url=account_url, credential=AZURE_STORAGE_ACCOUNT_KEY)
    # ファイル共有のクライアント作成
    share = service.get_share_client(TENANT_NAME)

    ## ディレクトリパスの構築
    # ユーザディレクトリのクライアント作成
    user_dir_client = share.get_directory_client(str(user_id))
    # アップロード対象のディレクトリのクライアント作成
    download_dir_client = user_dir_client.get_subdirectory_client(target_share_name)
    # タスクディレクトリのクライアント作成
    task_dir_client = download_dir_client.get_subdirectory_client(str(task_id))

    ## ファイルダウンロード
    # ダウンロードするファイルの名称設定
    download_file_name = str(object_id) + ".md"
    # ダウンロード対象のファイルのクライアント作成
    file_client = task_dir_client.get_file_client(download_file_name)
    # ファイルをダウンロード
    download = file_client.download_file()
    # ファイルの中身を取得
    file_content = download.readall()
    # UTF-8でデコードして返却
    return file_content.decode("utf-8")


def delete_task_directory(user_id: int, task_id: int, target_share_name: str=FileShareName.RESULT.value):
    """
    Azure Files上の指定したタスクディレクトリ配下のデータをすべて削除する
    ※ 削除対象のリソースが存在しない場合はResourceNotFoundErrorになるので呼び出しもとでハンドリングする

    Args
    -----------------
    - user_id: int,                 削除対象のユーザID
    - task_id: int,                 削除対象のタスクID
    - target_share_name: str,       削除対象のファイル共有名称

    """
    ## Azure Filesへの接続
    # Azure Filesの接続情報作成
    account_url = f"https://{AZURE_STORAGE_ACCOUNT_NAME}.file.core.windows.net"
    # 接続作成
    service = ShareServiceClient(account_url=account_url, credential=AZURE_STORAGE_ACCOUNT_KEY)
    # ファイル共有のクライアント作成
    share = service.get_share_client(TENANT_NAME)

    ## ディレクトリパスの構築
    # ユーザディレクトリのクライアント作成
    user_dir_client = share.get_directory_client(str(user_id))
    # 削除対象のディレクトリのクライアント作成
    delete_dir_client = user_dir_client.get_subdirectory_client(target_share_name)
    # タスクディレクトリのクライアント作成
    task_dir_client = delete_dir_client.get_subdirectory_client(str(task_id))

    ## ディレクトリ内のファイルをすべて削除
    # ディレクトリ内のファイル or サブディレクトリのリストを取得
    items = task_dir_client.list_directories_and_files()
    # 各アイテムを削除
    for item in items:
        if item.get("is_directory"):
            # サブディレクトリの場合は再帰的に削除
            subdir_client = task_dir_client.get_subdirectory_client(item["name"])
            subdir_client.delete_directory()
        else:
            # ファイルの場合は削除
            file_client = task_dir_client.get_file_client(item["name"])
            file_client.delete_file()

    ## タスクディレクトリ自体を削除
    task_dir_client.delete_directory()
