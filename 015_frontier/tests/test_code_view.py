"""「コード情報取得」画面用のファイル取得ロジックのテスト。"""

from __future__ import annotations

import base64

import pytest
import responses

from viewers.code import CodeViewError, _want_file, fetch_code_files
from config.settings import Settings

REPO = "acme/app"
BASE = f"https://api.github.com/repos/{REPO}"


def _settings(**over) -> Settings:
    base = dict(GITHUB_TOKEN="tok-gh", APP_TZ="Asia/Tokyo")
    base.update(over)
    return Settings(_env_file=None, **base)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def test_want_file_filters():
    assert _want_file("app/main.py") is True
    assert _want_file("web/index.html") is True
    assert _want_file("Dockerfile") is True
    assert _want_file("requirements.txt") is True
    # 除外ディレクトリ
    assert _want_file("node_modules/lib/index.js") is False
    assert _want_file("app/.venv/x.py") is False
    assert _want_file("app/__pycache__/x.py") is False
    # 除外ファイル・接尾辞
    assert _want_file("static/app.min.js") is False
    assert _want_file("package-lock.json") is False
    # 対象外拡張子
    assert _want_file("docs/readme.md") is False
    assert _want_file("assets/logo.png") is False


@responses.activate
def test_fetch_code_files_full():
    responses.add(responses.GET, BASE, json={"default_branch": "main"})
    responses.add(
        responses.GET, f"{BASE}/git/trees/main",
        json={"tree": [
            {"path": "app/main.py", "type": "blob", "sha": "s1", "size": 30},
            {"path": "app/util.js", "type": "blob", "sha": "s2", "size": 10},
            {"path": "node_modules/x/i.js", "type": "blob", "sha": "s3", "size": 9},  # 除外
            {"path": "README.md", "type": "blob", "sha": "s4", "size": 5},            # 除外
            {"path": "app/sub", "type": "tree", "sha": "t1"},                          # 除外
        ]},
    )
    responses.add(responses.GET, f"{BASE}/git/blobs/s1", json={"content": _b64("print('hi')\n".encode())})
    responses.add(responses.GET, f"{BASE}/git/blobs/s2", json={"content": _b64(b"export function f(){}")})

    out = fetch_code_files(_settings(), REPO)

    assert out["repo"] == REPO and out["branch"] == "main"
    assert out["path"] == "(リポジトリ全体)"
    # 対象拡張子のみ・パス昇順・name はリポジトリ相対パスそのまま
    assert [f["name"] for f in out["files"]] == ["app/main.py", "app/util.js"]
    assert out["file_count"] == 2
    assert out["files"][0]["content"] == "print('hi')\n"
    assert out["files"][0]["url"] == "https://github.com/acme/app/blob/main/app/main.py"


@responses.activate
def test_fetch_code_files_no_source():
    responses.add(responses.GET, BASE, json={"default_branch": "main"})
    responses.add(
        responses.GET, f"{BASE}/git/trees/main",
        json={"tree": [{"path": "README.md", "type": "blob", "sha": "s1", "size": 3}]},
    )
    with pytest.raises(CodeViewError):
        fetch_code_files(_settings(), REPO)


def test_fetch_code_files_validation():
    with pytest.raises(CodeViewError):
        fetch_code_files(_settings(GITHUB_TOKEN=""), REPO)      # トークン無し
    with pytest.raises(CodeViewError):
        fetch_code_files(_settings(), "invalid-repo")           # owner/repo 形式でない
