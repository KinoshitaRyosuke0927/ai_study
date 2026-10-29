"""講座の画像ファイルの保存先を扱うモジュール。

画像の一覧(ファイル名・形式・サイズ)は DB の course_images に、画像の中身はこの保存先に置く。
保存先は ImageStore の型だけに依存させ、設定(IMAGE_STORE)で切り替える。
- local      : ローカルのフォルダに保存する(LocalImageStore。ローカル開発用)
- azure_blob : Azure Blob Storage のコンテナに保存する(AzureBlobImageStore。Azure 上で使う)

保存先のキーは「講座 ID/ファイル名」(例: 12/hist.png)。講座を削除するときは「講座 ID/」でまとめて消す。
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol

from app.config.settings import get_settings


class ImageStore(Protocol):
    """画像の保存先の型。"""

    def put(self, key: str, data: bytes) -> None:
        """画像を保存する(同じキーは上書き)"""
        ...

    def get(self, key: str) -> bytes | None:
        """画像を読み込む(無ければ None)"""
        ...

    def delete(self, key: str) -> None:
        """画像を削除する(無ければ何もしない)"""
        ...

    def delete_prefix(self, prefix: str) -> None:
        """キーが prefix で始まる画像をまとめて削除する"""
        ...


class LocalImageStore:
    """ローカルのフォルダに保存する画像の保存先(ローカル開発用)。"""

    def __init__(self, root: str | Path) -> None:
        """
        保存先を用意する

        Args
        -----------------
        - root: str | Path,                 保存先のフォルダ

        """
        # 保存先のフォルダを絶対パスで保持
        self._root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        """
        キーから保存先のパスを求める(保存先フォルダの外を指すキーは受け付けない)

        Args
        -----------------
        - key: str,                         キー(講座 ID/ファイル名)

        Returns
        -----------------
        - path: Path,                       保存先のパス

        """
        # 保存先フォルダの中に収まることを確認して返却
        path = (self._root / key).resolve()
        if self._root not in path.parents:
            raise ValueError(f"画像のキーが正しくありません: {key}")
        return path

    def put(self, key: str, data: bytes) -> None:
        """
        画像を保存する(同じキーは上書き)

        Args
        -----------------
        - key: str,                         キー
        - data: bytes,                      画像の中身

        """
        # フォルダを作ってから書き込む
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes | None:
        """
        画像を読み込む

        Args
        -----------------
        - key: str,                         キー

        Returns
        -----------------
        - data: bytes | None,               画像の中身(無ければ None)

        """
        # ファイルがあれば読み込んで返却
        path = self._path(key)
        return path.read_bytes() if path.is_file() else None

    def delete(self, key: str) -> None:
        """
        画像を削除する(無ければ何もしない)

        Args
        -----------------
        - key: str,                         キー

        """
        # ファイルがあれば削除
        self._path(key).unlink(missing_ok=True)

    def delete_prefix(self, prefix: str) -> None:
        """
        キーが prefix で始まる画像をまとめて削除する(prefix は「講座 ID/」)

        Args
        -----------------
        - prefix: str,                      キーの先頭(フォルダ)

        """
        # フォルダごと削除
        folder = self._path(prefix.rstrip("/"))
        if folder.is_dir():
            shutil.rmtree(folder)


class AzureBlobImageStore:
    """Azure Blob Storage のコンテナに保存する画像の保存先(Azure 上で使う)。

    コンテナは非公開(匿名アクセスなし)とし、画像はアプリ経由で配信する。
    認証は接続文字列があればそれを、無ければ DefaultAzureCredential(Azure 上はマネージド ID、ローカルは az login)を使う。
    """

    def __init__(self, account_url: str, container: str, connection_string: str = "") -> None:
        """
        保存先のコンテナに接続する

        Args
        -----------------
        - account_url: str,                 ストレージアカウントの URL(https://<アカウント名>.blob.core.windows.net)
        - container: str,                   コンテナ名
        - connection_string: str,           接続文字列(指定した場合は account_url より優先)

        """
        # SDK はこの保存先を使うときだけ読み込む(ローカル開発では不要)
        from azure.storage.blob import BlobServiceClient

        # 接続文字列があればそれで、無ければマネージド ID などの資格情報で接続する
        if connection_string:
            service = BlobServiceClient.from_connection_string(connection_string)
        else:
            if not account_url:
                raise RuntimeError("IMAGE_STORE=azure_blob では AZURE_STORAGE_ACCOUNT_URL を設定してください")
            from azure.identity import DefaultAzureCredential

            service = BlobServiceClient(account_url, credential=DefaultAzureCredential())
        self._container = service.get_container_client(container)

    @staticmethod
    def _check(key: str) -> str:
        """
        キーが「講座 ID/ファイル名」の形であることを確認する

        Args
        -----------------
        - key: str,                         キー

        Returns
        -----------------
        - key: str,                         確認したキー

        """
        # 空の要素や上位フォルダを指す要素を含むキーは受け付けない
        parts = key.split("/")
        if not key or any(p in ("", ".", "..") for p in parts) or "\\" in key:
            raise ValueError(f"画像のキーが正しくありません: {key}")
        return key

    def put(self, key: str, data: bytes) -> None:
        """
        画像を保存する(同じキーは上書き)

        Args
        -----------------
        - key: str,                         キー
        - data: bytes,                      画像の中身

        """
        # BLOB として書き込む(既存は上書き)
        self._container.upload_blob(self._check(key), data, overwrite=True)

    def get(self, key: str) -> bytes | None:
        """
        画像を読み込む

        Args
        -----------------
        - key: str,                         キー

        Returns
        -----------------
        - data: bytes | None,               画像の中身(無ければ None)

        """
        from azure.core.exceptions import ResourceNotFoundError

        # BLOB を読み込んで返却(無ければ None)
        try:
            return self._container.download_blob(self._check(key)).readall()
        except ResourceNotFoundError:
            return None

    def delete(self, key: str) -> None:
        """
        画像を削除する(無ければ何もしない)

        Args
        -----------------
        - key: str,                         キー

        """
        from azure.core.exceptions import ResourceNotFoundError

        # BLOB を削除(無ければ何もしない)
        try:
            self._container.delete_blob(self._check(key))
        except ResourceNotFoundError:
            pass

    def delete_prefix(self, prefix: str) -> None:
        """
        キーが prefix で始まる画像をまとめて削除する(prefix は「講座 ID/」)

        Args
        -----------------
        - prefix: str,                      キーの先頭(フォルダ)

        """
        # 「講座 ID/」の形に整えてから、該当する BLOB を1つずつ削除
        folder = self._check(prefix.rstrip("/")) + "/"
        for name in list(self._container.list_blob_names(name_starts_with=folder)):
            self.delete(name)


# テストなどで差し替えた保存先(None なら設定から生成する)
_override: ImageStore | None = None
# 設定から生成した Blob Storage の保存先(接続を使い回すために保持する)
_blob_store: AzureBlobImageStore | None = None


def set_image_store(store: ImageStore | None) -> None:
    """
    使用する画像の保存先を差し替える(テスト用)

    Args
    -----------------
    - store: ImageStore | None,         差し替える保存先(None で元に戻す)

    """
    global _override
    # 差し替え先を保存
    _override = store


def get_image_store() -> ImageStore:
    """
    使用する画像の保存先を返す

    Returns
    -----------------
    - store: ImageStore,                画像の保存先

    """
    # 差し替えられていればそれを使う
    if _override is not None:
        return _override
    # 設定に従って保存先を生成して返却
    settings = get_settings()
    if settings.image_store == "local":
        return LocalImageStore(settings.image_local_dir)
    if settings.image_store == "azure_blob":
        global _blob_store
        # Blob Storage への接続は使い回す(リクエストごとに作り直さない)
        if _blob_store is None:
            _blob_store = AzureBlobImageStore(
                settings.azure_storage_account_url,
                settings.azure_storage_container,
                settings.azure_storage_connection_string,
            )
        return _blob_store
    raise RuntimeError(f"IMAGE_STORE '{settings.image_store}' には対応していません(local / azure_blob)")
