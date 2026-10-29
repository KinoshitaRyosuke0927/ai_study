"""Blob Storage 版の画像の保存先(AzureBlobImageStore)のテスト。

実際の Blob Storage には接続せず、コンテナの操作をメモリ上の偽物に差し替えて確かめる。
"""

import pytest
from azure.core.exceptions import ResourceNotFoundError

from app.infra.image_store import AzureBlobImageStore


class _Downloaded:
    """download_blob の戻り値の偽物。"""

    def __init__(self, data: bytes):
        self._data = data

    def readall(self) -> bytes:
        return self._data


class FakeContainer:
    """Blob コンテナの偽物(BLOB 名 → 中身 をメモリに持つ)。"""

    def __init__(self):
        self.blobs: dict[str, bytes] = {}

    def upload_blob(self, name: str, data: bytes, overwrite: bool = False):
        assert overwrite
        self.blobs[name] = data

    def download_blob(self, name: str):
        if name not in self.blobs:
            raise ResourceNotFoundError("not found")
        return _Downloaded(self.blobs[name])

    def delete_blob(self, name: str):
        if name not in self.blobs:
            raise ResourceNotFoundError("not found")
        del self.blobs[name]

    def list_blob_names(self, name_starts_with: str):
        return [n for n in self.blobs if n.startswith(name_starts_with)]


@pytest.fixture()
def store():
    """コンテナを偽物に差し替えた保存先。"""
    s = AzureBlobImageStore.__new__(AzureBlobImageStore)
    s._container = FakeContainer()
    return s


def test_put_get_delete(store):
    store.put("12/hist.png", b"png")
    assert store.get("12/hist.png") == b"png"
    # 同じキーは上書き
    store.put("12/hist.png", b"png2")
    assert store.get("12/hist.png") == b"png2"
    # 無いキーは None、削除は無くてもエラーにしない
    assert store.get("12/none.png") is None
    store.delete("12/hist.png")
    store.delete("12/hist.png")
    assert store.get("12/hist.png") is None


def test_delete_prefix_only_that_course(store):
    store.put("1/a.png", b"a")
    store.put("1/b.png", b"b")
    store.put("12/c.png", b"c")
    # 「1/」は「12/」を含まない
    store.delete_prefix("1/")
    assert store._container.blobs == {"12/c.png": b"c"}


@pytest.mark.parametrize("key", ["", "../x.png", "1/../x.png", "1//x.png", "1\\x.png", "/1/x.png"])
def test_rejects_bad_keys(store, key):
    with pytest.raises(ValueError):
        store.put(key, b"x")


def test_requires_account_url():
    with pytest.raises(RuntimeError):
        AzureBlobImageStore("", "course-images")
