"""設定画面のアクセス確認(GitHub リポジトリ / GROWI パス)のテスト。"""

from __future__ import annotations

import responses

from viewers.options import check_github_path, check_github_repo, check_growi_path
from config.settings import Settings


def _settings(**over) -> Settings:
    base = dict(
        GITHUB_TOKEN="tok-gh",
        GROWI_URL="https://growi.internal.test",
        GROWI_API_TOKEN="tok-growi",
    )
    base.update(over)
    return Settings(_env_file=None, **base)


# ----------------------------------------------------------------------
# GitHub
# ----------------------------------------------------------------------
@responses.activate
def test_check_github_repo_owner_slash_ok():
    responses.add(
        responses.GET, "https://api.github.com/repos/acme/app",
        json={"full_name": "acme/app"}, status=200,
    )
    full, err = check_github_repo(_settings(), "acme/app")
    assert err is None
    assert full == "acme/app"
    assert responses.calls[0].request.headers["Authorization"] == "Bearer tok-gh"


@responses.activate
def test_check_github_repo_not_found():
    responses.add(
        responses.GET, "https://api.github.com/repos/acme/missing", status=404,
        json={"message": "Not Found"},
    )
    full, err = check_github_repo(_settings(), "acme/missing")
    assert full is None
    assert "見つかりません" in err


@responses.activate
def test_check_github_repo_bad_credentials():
    responses.add(
        responses.GET, "https://api.github.com/repos/acme/app", status=401,
        json={"message": "Bad credentials"},
    )
    full, err = check_github_repo(_settings(), "acme/app")
    assert full is None
    assert "トークン" in err  # トークンが無効/期限切れ の案内


@responses.activate
def test_check_github_repo_bare_name_resolved():
    responses.add(
        responses.GET, "https://api.github.com/user/repos",
        json=[{"name": "other", "full_name": "me/other"}, {"name": "app", "full_name": "me/app"}],
        status=200,
    )
    full, err = check_github_repo(_settings(), "app")
    assert err is None
    assert full == "me/app"


@responses.activate
def test_check_github_repo_bare_name_not_found():
    responses.add(
        responses.GET, "https://api.github.com/user/repos",
        json=[{"name": "other", "full_name": "me/other"}], status=200,
    )
    full, err = check_github_repo(_settings(), "app")
    assert full is None
    assert "見つかりません" in err


def test_check_github_repo_no_token():
    full, err = check_github_repo(_settings(GITHUB_TOKEN=""), "acme/app")
    assert full is None
    assert "トークンが未設定" in err


@responses.activate
def test_check_github_path_ok_directory():
    responses.add(
        responses.GET, "https://api.github.com/repos/acme/app/contents/docs/design",
        json=[{"name": "a.md", "type": "file"}], status=200,
    )
    assert check_github_path(_settings(), "acme/app", "docs/design") is None


@responses.activate
def test_check_github_path_is_a_file():
    responses.add(
        responses.GET, "https://api.github.com/repos/acme/app/contents/docs/readme.md",
        json={"name": "readme.md", "type": "file"}, status=200,
    )
    err = check_github_path(_settings(), "acme/app", "docs/readme.md")
    assert "フォルダではなくファイル" in err


@responses.activate
def test_check_github_path_not_found():
    responses.add(
        responses.GET, "https://api.github.com/repos/acme/app/contents/nope",
        status=404, json={"message": "Not Found"},
    )
    err = check_github_path(_settings(), "acme/app", "nope")
    assert "見つかりません" in err


def test_check_github_path_empty_is_ok():
    assert check_github_path(_settings(), "acme/app", "") is None
    assert check_github_path(_settings(), "acme/app", "   ") is None


# ----------------------------------------------------------------------
# GROWI
# ----------------------------------------------------------------------
@responses.activate
def test_check_growi_path_ok():
    responses.add(
        responses.GET, "https://growi.internal.test/_api/v3/pages/list",
        json={"pages": [{"_id": "p1", "path": "/projects/foo/x"}]}, status=200,
    )
    count, err = check_growi_path(_settings(), "/projects/foo")
    assert err is None
    assert count == 1
    from urllib.parse import parse_qs, urlparse

    q = parse_qs(urlparse(responses.calls[0].request.url).query)
    assert q["access_token"] == ["tok-growi"]
    assert q["path"] == ["/projects/foo"]


@responses.activate
def test_check_growi_path_empty_result():
    responses.add(
        responses.GET, "https://growi.internal.test/_api/v3/pages/list",
        json={"pages": []}, status=200,
    )
    count, err = check_growi_path(_settings(), "/projects/none")
    assert count is None
    assert "見つかりません" in err


@responses.activate
def test_check_growi_path_http_error():
    responses.add(
        responses.GET, "https://growi.internal.test/_api/v3/pages/list", status=403,
    )
    count, err = check_growi_path(_settings(), "/secret")
    assert count is None
    assert "トークンが無効" in err
