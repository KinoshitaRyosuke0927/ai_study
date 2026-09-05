"""「設計書情報取得」画面用のファイル取得ロジックのテスト。"""

from __future__ import annotations

import base64

import pytest
import responses

from viewers.design import DesignViewError, fetch_design_files
from config.settings import Settings

REPO = "acme/app"
BASE = f"https://api.github.com/repos/{REPO}"


def _settings(**over) -> Settings:
    base = dict(GITHUB_TOKEN="tok-gh", APP_TZ="Asia/Tokyo")
    base.update(over)
    return Settings(_env_file=None, **base)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


@responses.activate
def test_fetch_design_files_full():
    responses.add(responses.GET, BASE, json={"default_branch": "main"})
    responses.add(
        responses.GET, f"{BASE}/git/trees/main",
        json={"tree": [
            {"path": "docs/design/b.md", "type": "blob", "sha": "s2", "size": 20},
            {"path": "docs/design/a.md", "type": "blob", "sha": "s1", "size": 12},
            {"path": "docs/design/img/logo.png", "type": "blob", "sha": "s3", "size": 40},
            {"path": "docs/design/sub", "type": "tree", "sha": "t1"},
            {"path": "README.md", "type": "blob", "sha": "s9", "size": 5},  # 対象外
        ]},
    )
    responses.add(responses.GET, f"{BASE}/git/blobs/s1", json={"content": _b64("# A\n本文".encode())})
    responses.add(responses.GET, f"{BASE}/git/blobs/s2", json={"content": _b64(b"plain b")})
    responses.add(responses.GET, f"{BASE}/git/blobs/s3", json={"content": _b64(b"\x00\x01PNGbinary")})

    out = fetch_design_files(_settings(), REPO, "docs/design")

    assert out["repo"] == REPO and out["branch"] == "main" and out["path"] == "docs/design"
    # README.md は対象外、ディレクトリエントリも除外。path 昇順。
    assert [f["name"] for f in out["files"]] == ["a.md", "b.md", "img/logo.png"]
    assert out["file_count"] == 3

    a, b, png = out["files"]
    assert a["content"] == "# A\n本文" and a["binary"] is False
    assert b["content"] == "plain b"
    assert png["binary"] is True and png["content"] == ""     # NUL バイト → バイナリ扱い
    assert a["path"] == "docs/design/a.md"
    assert a["url"] == "https://github.com/acme/app/blob/main/docs/design/a.md"


@responses.activate
def test_fetch_design_files_slash_in_config_is_trimmed():
    responses.add(responses.GET, BASE, json={"default_branch": "dev"})
    responses.add(
        responses.GET, f"{BASE}/git/trees/dev",
        json={"tree": [{"path": "spec/x.md", "type": "blob", "sha": "s1", "size": 3}]},
    )
    responses.add(responses.GET, f"{BASE}/git/blobs/s1", json={"content": _b64(b"xxx")})
    out = fetch_design_files(_settings(), REPO, "/spec/")
    assert out["path"] == "spec" and out["files"][0]["name"] == "x.md"


@responses.activate
def test_fetch_design_files_no_match():
    responses.add(responses.GET, BASE, json={"default_branch": "main"})
    responses.add(
        responses.GET, f"{BASE}/git/trees/main",
        json={"tree": [{"path": "other/x.md", "type": "blob", "sha": "s1", "size": 3}]},
    )
    with pytest.raises(DesignViewError):
        fetch_design_files(_settings(), REPO, "docs/design")


@responses.activate
def test_fetch_design_files_repo_not_accessible():
    responses.add(responses.GET, BASE, status=404, json={"message": "Not Found"})
    with pytest.raises(DesignViewError):
        fetch_design_files(_settings(), REPO, "docs")


def test_fetch_design_files_validation():
    with pytest.raises(DesignViewError):
        fetch_design_files(_settings(GITHUB_TOKEN=""), REPO, "docs")     # トークン無し
    with pytest.raises(DesignViewError):
        fetch_design_files(_settings(), "", "docs")                     # リポジトリ未設定
    with pytest.raises(DesignViewError):
        fetch_design_files(_settings(), REPO, "")                       # 設計書パス未設定
