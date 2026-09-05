"""「GitHub 情報取得」画面用: 指定リポジトリのブランチ活動と PR を取得する。

分析パイプラインとは独立しており、DB へは保存しない(結果は画面側でメモリ保持)。

GitHub の制約について:
- 汎用リポジトリ向けの「ブランチ操作ログ」API は存在しない(監査ログは
  GitHub Enterprise の Organization 限定)。そのため各ブランチの「いつ・だれが・
  どのような操作」は **そのブランチへのコミット履歴**(日時・作者・メッセージ)で表す。
- ブランチの作成/削除の記録は確実には取得できない(Events API は約 90 日・件数上限)。
- PR のマージ実行者・コメントは PR ごとの個別 API 呼び出しが必要なため、直近
  PR_DETAIL_COUNT 件のみ詳細を取得する。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from collectors.base import HttpClient
from config.settings import Settings

logger = logging.getLogger(__name__)

API_ROOT = "https://api.github.com"
_LINK_NEXT_RE = re.compile(r'<([^>]+)>;\s*rel="next"')

BRANCH_LIST_CAP = 200        # 一覧に載せるブランチ数の上限
BRANCH_COMMITS = 15          # ブランチごとに取得するコミット数
PR_LIST_CAP = 200            # 一覧に載せる PR 数の上限
PR_DETAIL_COUNT = 30         # コメント / マージ実行者まで取得する直近 PR 数

_REVIEW_LABEL = {
    "APPROVED": "承認",
    "CHANGES_REQUESTED": "変更要求",
    "COMMENTED": "レビューコメント",
    "DISMISSED": "レビュー無効化",
}


class GitHubViewError(Exception):
    """取得条件が不正、または GitHub にアクセスできない場合。"""


def _tz(settings: Settings):
    if ZoneInfo is not None:
        try:
            return ZoneInfo(settings.app_tz)
        except Exception:  # pragma: no cover
            pass
    return timezone.utc


def _fmt(value: str | None, tzinfo) -> str | None:
    """ISO8601(UTC)を "YYYY-MM-DD HH:MM"(アプリTZ)へ。None はそのまま。"""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tzinfo).strftime("%Y-%m-%d %H:%M")


def _first_line(text: str, limit: int = 120) -> str:
    line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    return line[:limit]


class _GitHubApi:
    def __init__(self, settings: Settings) -> None:
        self._http = HttpClient(
            {
                "Authorization": f"Bearer {settings.github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    def get(self, url: str, params: dict | None = None) -> Any:
        return self._http.get_json(url if url.startswith("http") else f"{API_ROOT}{url}", params=params)

    def paginate(self, path: str, params: dict, cap: int) -> list:
        """Link ヘッダを辿って最大 cap 件まで取得する。"""
        results: list = []
        url: str | None = f"{API_ROOT}{path}"
        next_params: dict | None = dict(params)
        while url and len(results) < cap:
            resp = self._http.get(url, params=next_params)
            page = resp.json()
            if not isinstance(page, list):
                break
            results.extend(page)
            match = _LINK_NEXT_RE.search(resp.headers.get("Link", ""))
            url = match.group(1) if match else None
            next_params = None
        return results[:cap]

    def first_page(self, path: str, params: dict) -> list:
        """1 ページ目だけ取得する。"""
        data = self.get(path, params=params)
        return data if isinstance(data, list) else []


def _resolve_repo(settings: Settings, configured: str) -> str:
    """設定画面のリポジトリ名(空なら .env の 1 つ目)を owner/repo で返す。"""
    repo = (configured or "").strip().strip("/")
    if not repo:
        repos = settings.github_repo_list
        repo = repos[0] if repos else ""
    return repo


def fetch_repo_activity(settings: Settings, configured_repo: str) -> dict[str, Any]:
    """リポジトリのブランチ活動と PR を返す。

    Raises:
        GitHubViewError: リポジトリ未設定 / トークン未設定 / アクセス不可の場合。
    """
    if not settings.github_token or settings.github_token == "changeme":
        raise GitHubViewError("GitHub トークンが未設定です(.env の GITHUB_TOKEN)")
    repo = _resolve_repo(settings, configured_repo)
    if not repo:
        raise GitHubViewError("設定画面で「GitHub リポジトリ名称」を設定してください")
    if "/" not in repo:
        raise GitHubViewError(f"リポジトリ名は 'owner/repo' 形式が必要です: {repo}")

    tzinfo = _tz(settings)
    api = _GitHubApi(settings)

    # 存在確認を兼ねてリポジトリ情報を取得
    try:
        api.get(f"/repos/{repo}")
    except Exception as exc:
        logger.error("GitHub リポジトリ取得失敗 repo=%s: %s", repo, exc)
        raise GitHubViewError(
            f"リポジトリ '{repo}' にアクセスできません(名称/権限/トークンを確認してください): {exc}"
        ) from exc

    branches_out = _fetch_branches(api, repo, tzinfo)
    prs_out, pr_detail_count = _fetch_pull_requests(api, repo, tzinfo)

    return {
        "repo": repo,
        "branch_count": len(branches_out),
        "branches_truncated": len(branches_out) >= BRANCH_LIST_CAP,
        "branches": branches_out,
        "pr_count": len(prs_out),
        "prs_truncated": len(prs_out) >= PR_LIST_CAP,
        "pr_detail_count": pr_detail_count,
        "pull_requests": prs_out,
    }


def _fetch_branches(api: _GitHubApi, repo: str, tzinfo) -> list[dict]:
    """全ブランチと、各ブランチの直近コミット(いつ/だれが/何を)を返す。"""
    branches = api.paginate(f"/repos/{repo}/branches", {"per_page": 100}, BRANCH_LIST_CAP)
    out: list[dict] = []
    for b in branches:
        name = b.get("name", "")
        commits_out: list[dict] = []
        try:
            commits = api.first_page(
                f"/repos/{repo}/commits", {"sha": name, "per_page": BRANCH_COMMITS}
            )
        except Exception as exc:  # 1 ブランチの失敗で全体を止めない
            logger.warning("GitHub コミット取得失敗 repo=%s branch=%s: %s", repo, name, exc)
            commits = []
        for c in commits:
            info = c.get("commit", {})
            author = (c.get("author") or {}).get("login") or info.get("author", {}).get("name", "unknown")
            commits_out.append(
                {
                    "sha": (c.get("sha") or "")[:7],
                    "author": author,
                    "date": _fmt(info.get("author", {}).get("date"), tzinfo),
                    "message": _first_line(info.get("message", "")),
                    "url": c.get("html_url", ""),
                }
            )
        last = commits_out[0] if commits_out else None
        out.append(
            {
                "name": name,
                "protected": bool(b.get("protected")),
                "last_activity": last["date"] if last else None,
                "last_author": last["author"] if last else None,
                "commit_count": len(commits_out),
                "commits": commits_out,
            }
        )
    # 直近アクティビティが新しい順
    out.sort(key=lambda x: x["last_activity"] or "", reverse=True)
    return out


def _fetch_pull_requests(api: _GitHubApi, repo: str, tzinfo) -> tuple[list[dict], int]:
    """PR 一覧と、直近 PR_DETAIL_COUNT 件の詳細(マージ実行者/コメント)を返す。"""
    prs = api.paginate(
        f"/repos/{repo}/pulls",
        {"state": "all", "sort": "updated", "direction": "desc", "per_page": 100},
        PR_LIST_CAP,
    )
    out: list[dict] = []
    detail_done = 0
    for idx, pr in enumerate(prs):
        num = pr.get("number")
        merged = bool(pr.get("merged_at"))
        entry: dict[str, Any] = {
            "number": num,
            "title": pr.get("title", ""),
            "state": pr.get("state", ""),          # open / closed
            "merged": merged,
            "author": (pr.get("user") or {}).get("login"),
            "created": _fmt(pr.get("created_at"), tzinfo),
            "closed": _fmt(pr.get("closed_at"), tzinfo),
            "merged_at": _fmt(pr.get("merged_at"), tzinfo),
            "merged_by": None,
            "url": pr.get("html_url", ""),
            "detail_loaded": False,
            "comments": [],
        }
        if idx < PR_DETAIL_COUNT:
            _load_pr_detail(api, repo, num, merged, entry, tzinfo)
            detail_done += 1
        out.append(entry)
    return out, detail_done


def _load_pr_detail(api: _GitHubApi, repo: str, num: int, merged: bool, entry: dict, tzinfo) -> None:
    """1 PR の マージ実行者 + コメント(会話 + レビュー)を entry に追加する。"""
    try:
        if merged:
            detail = api.get(f"/repos/{repo}/pulls/{num}")
            entry["merged_by"] = (detail.get("merged_by") or {}).get("login")

        comments: list[dict] = []
        for c in api.paginate(f"/repos/{repo}/issues/{num}/comments", {"per_page": 100}, 300):
            comments.append(
                {
                    "kind": "comment",
                    "author": (c.get("user") or {}).get("login"),
                    "date": _fmt(c.get("created_at"), tzinfo),
                    "text": c.get("body", "") or "",
                }
            )
        for r in api.paginate(f"/repos/{repo}/pulls/{num}/reviews", {"per_page": 100}, 300):
            state = r.get("state")
            if state in (None, "PENDING"):
                continue
            label = _REVIEW_LABEL.get(state, state)
            body = (r.get("body") or "").strip()
            comments.append(
                {
                    "kind": "review",
                    "author": (r.get("user") or {}).get("login"),
                    "date": _fmt(r.get("submitted_at"), tzinfo),
                    "text": f"[{label}] {body}".strip(),
                }
            )
        comments.sort(key=lambda x: x["date"] or "")
        entry["comments"] = comments
        entry["detail_loaded"] = True
    except Exception as exc:  # 1 PR の失敗で全体を止めない
        logger.warning("GitHub PR 詳細取得失敗 repo=%s pr=%s: %s", repo, num, exc)
