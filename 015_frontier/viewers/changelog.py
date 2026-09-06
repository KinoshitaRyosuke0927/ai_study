"""「変更履歴取得」画面用: 設定「GitHub リポジトリ名称」のリポジトリの
既定ブランチについて、コミット履歴をファイル単位・ユーザ単位で取得する。

コードは情報量が多いため、生 patch はそのまま扱わない:
- ソース拡張子のファイルのみ対象(viewers.code のフィルタを流用)。
- patch からは「ハンク見出し」(@@ 行 = どの関数/領域が変わったか)を抽出する。
- patch 本体は先頭を打ち切った抜粋(patch_excerpt)だけを保持する。
- 取得範囲は since_date(設定「データ取得開始日時」)で区切り、件数上限を設ける。
- 2 回目以降は前回の HEAD SHA から今回までの増分だけを取得する。
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, time, timezone
from typing import Any

from collectors.base import HttpClient
from config.settings import Settings
from viewers.code import _want_file

logger = logging.getLogger(__name__)

API_ROOT = "https://api.github.com"
_LINK_NEXT_RE = re.compile(r'<([^>]+)>;\s*rel="next"')
_HUNK_RE = re.compile(r"^@@ .* @@.*$", re.MULTILINE)

MAX_COMMITS = 2000               # 1 回で一覧する最大コミット数
MAX_DETAIL_COMMITS = 400         # 1 回でファイル変更まで取得する最大コミット数
MAX_HUNK_HEADERS = 25            # 1 ファイルあたりのハンク見出し上限
PATCH_EXCERPT_LINES = 60         # patch 抜粋の行数上限
PATCH_EXCERPT_CHARS = 4000       # patch 抜粋の文字数上限
MAX_CHANGES_FOR_PATCH = 2000     # これを超える変更量のファイルは抜粋を保存しない


class ChangelogViewError(Exception):
    """取得条件が不正、または GitHub にアクセスできない場合。"""


class _GitHubClient:
    def __init__(self, settings: Settings) -> None:
        self._http = HttpClient(
            {
                "Authorization": f"Bearer {settings.github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    def get_json(self, path_or_url: str, params: dict | None = None) -> Any:
        url = path_or_url if path_or_url.startswith("http") else f"{API_ROOT}{path_or_url}"
        return self._http.get_json(url, params=params)

    def get_paged(self, path: str, params: dict, cap: int) -> list[dict]:
        """Link ヘッダの rel="next" をたどって最大 cap 件まで取得する。"""
        out: list[dict] = []
        resp = self._http.get(f"{API_ROOT}{path}", params=params)
        while True:
            out.extend(resp.json() or [])
            if len(out) >= cap:
                return out[:cap]
            m = _LINK_NEXT_RE.search(resp.headers.get("Link", "") or "")
            if not m:
                return out
            resp = self._http.get(m.group(1))


def _resolve_repo(settings: Settings, configured: str) -> str:
    repo = (configured or "").strip().strip("/")
    if not repo:
        repos = settings.github_repo_list
        repo = repos[0] if repos else ""
    return repo


def _since_iso(d: date | None) -> str | None:
    if not d:
        return None
    return datetime.combine(d, time.min, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hunk_headers(patch: str | None) -> list[str]:
    if not patch:
        return []
    return [h.strip() for h in _HUNK_RE.findall(patch)][:MAX_HUNK_HEADERS]


def _patch_excerpt(patch: str | None, changes: int) -> tuple[str | None, bool]:
    """patch の先頭抜粋を返す。(excerpt, truncated)。対象外は (None, False)。"""
    if not patch or changes > MAX_CHANGES_FOR_PATCH:
        return None, False
    lines = patch.splitlines()
    truncated = len(lines) > PATCH_EXCERPT_LINES or len(patch) > PATCH_EXCERPT_CHARS
    text = "\n".join(lines[:PATCH_EXCERPT_LINES])[:PATCH_EXCERPT_CHARS]
    return text, truncated


def _commit_files(api: _GitHubClient, repo: str, sha: str) -> tuple[list[dict], int, int]:
    """1 コミットのファイル変更一覧を返す。(files, additions, deletions)。"""
    detail = api.get_json(f"/repos/{repo}/commits/{sha}")
    files_out: list[dict[str, Any]] = []
    add_total = det_total = 0
    for f in detail.get("files", []) or []:
        path = f.get("filename", "")
        add_total += int(f.get("additions", 0) or 0)
        det_total += int(f.get("deletions", 0) or 0)
        is_source = _want_file(path)
        patch = f.get("patch") if is_source else None
        excerpt, trunc = _patch_excerpt(patch, int(f.get("changes", 0) or 0))
        files_out.append({
            "path": path,
            "previous_path": f.get("previous_filename"),
            "status": f.get("status", ""),
            "additions": int(f.get("additions", 0) or 0),
            "deletions": int(f.get("deletions", 0) or 0),
            "hunk_headers": _hunk_headers(patch),
            "patch_excerpt": excerpt,
            "binary": bool(not f.get("patch") and f.get("changes", 0)),
            "truncated": trunc,
            "is_source": is_source,
        })
    return files_out, add_total, det_total


def fetch_change_history(
    settings: Settings,
    configured_repo: str,
    since_date: date | None = None,
    base_sha: str | None = None,
) -> dict[str, Any]:
    """既定ブランチのコミット履歴を、ファイル変更込みで返す。

    Raises:
        ChangelogViewError: リポジトリ未設定 / アクセス不可の場合。
    """
    if not settings.github_token or settings.github_token == "changeme":
        raise ChangelogViewError("GitHub トークンが未設定です(.env の GITHUB_TOKEN)")
    repo = _resolve_repo(settings, configured_repo)
    if not repo or "/" not in repo:
        raise ChangelogViewError("設定画面で「GitHub リポジトリ名称」を owner/repo 形式で設定してください")

    api = _GitHubClient(settings)
    try:
        repo_info = api.get_json(f"/repos/{repo}")
    except Exception as exc:
        logger.error("GitHub リポジトリ取得失敗 repo=%s: %s", repo, exc)
        raise ChangelogViewError(
            f"リポジトリ '{repo}' にアクセスできません(名称/権限/トークンを確認してください): {exc}"
        ) from exc
    branch = repo_info.get("default_branch") or "main"

    # --- コミット一覧(軽量。since / 上限 / 前回 HEAD で区切る)---
    params: dict[str, Any] = {"sha": branch, "per_page": 100}
    since_iso = _since_iso(since_date)
    if since_iso:
        params["since"] = since_iso
    try:
        raw_commits = api.get_paged(f"/repos/{repo}/commits", params, MAX_COMMITS)
    except Exception as exc:
        logger.error("GitHub コミット一覧取得失敗 repo=%s: %s", repo, exc)
        raise ChangelogViewError(f"コミット一覧を取得できませんでした: {exc}") from exc

    if not raw_commits:
        return {
            "repo": repo, "branch": branch, "head_sha": None, "base_sha": base_sha,
            "since_date": since_date.isoformat() if since_date else None,
            "commit_count": 0, "detail_count": 0, "truncated": False, "commits": [],
        }

    head_sha = raw_commits[0].get("sha")

    # 前回 HEAD 以降の新規コミットだけに絞る(増分)
    new_commits: list[dict] = []
    for c in raw_commits:
        if base_sha and c.get("sha") == base_sha:
            break
        new_commits.append(c)

    truncated = len(new_commits) > MAX_DETAIL_COMMITS
    detail_targets = new_commits[:MAX_DETAIL_COMMITS]

    commits_out: list[dict[str, Any]] = []
    for c in detail_targets:
        sha = c.get("sha", "")
        commit = c.get("commit", {}) or {}
        gh_author = c.get("author") or {}
        cauthor = commit.get("author", {}) or {}
        try:
            files, adds, dels = _commit_files(api, repo, sha)
        except Exception as exc:  # 1 コミットの失敗で全体を止めない
            logger.warning("GitHub コミット詳細取得失敗 repo=%s sha=%s: %s", repo, sha, exc)
            files, adds, dels = [], 0, 0
        commits_out.append({
            "sha": sha,
            "author_login": gh_author.get("login") or "",
            "author_name": cauthor.get("name") or "",
            "author_email": cauthor.get("email") or "",
            "committed_at": cauthor.get("date") or commit.get("committer", {}).get("date"),
            "message": commit.get("message", "") or "",
            "is_merge": len(c.get("parents", []) or []) > 1,
            "additions": adds,
            "deletions": dels,
            "files_changed": len(files),
            "files": files,
        })

    return {
        "repo": repo,
        "branch": branch,
        "head_sha": head_sha,
        "base_sha": base_sha,
        "since_date": since_date.isoformat() if since_date else None,
        "commit_count": len(new_commits),
        "detail_count": len(commits_out),
        "truncated": truncated,
        "commits": commits_out,
    }
