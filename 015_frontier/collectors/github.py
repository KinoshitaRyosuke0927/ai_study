"""GitHub コレクタ。

複数リポジトリのコミット / PR / issue を差分取得し正規化する。
API(認証: Authorization: Bearer <token>):
  GET /repos/{owner}/{repo}/commits?since=<ISO8601>
  GET /repos/{owner}/{repo}/pulls?state=all&sort=updated&direction=desc
  GET /repos/{owner}/{repo}/issues?state=all&sort=updated&direction=desc
ページングは Link ヘッダの rel="next" を辿る。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from config.settings import Settings

from .base import Event, HttpClient, ItemRecord

logger = logging.getLogger(__name__)

API_ROOT = "https://api.github.com"
PER_PAGE = 100
_LINK_NEXT_RE = re.compile(r'<([^>]+)>;\s*rel="next"')


def _parse_iso(value: str | None) -> datetime | None:
    """ISO8601 文字列を UTC naive datetime へ。None はそのまま。"""
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class GitHubCollector:
    """GitHub コミット / PR / issue コレクタ。"""

    source = "github"

    def __init__(
        self,
        settings: Settings,
        http: HttpClient | None = None,
        repos: list[str] | None = None,
    ) -> None:
        # 取得対象リポジトリ。指定が無ければ .env の GITHUB_REPOS を使う
        self._repos = repos if repos is not None else settings.github_repo_list
        self._http = http or HttpClient(
            {
                "Authorization": f"Bearer {settings.github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    # ------------------------------------------------------------------
    # ページング
    # ------------------------------------------------------------------
    def _paginate(self, url: str, params: dict) -> list:
        """Link ヘッダを辿って全ページの JSON 配列を連結して返す。"""
        results: list = []
        next_url: str | None = url
        next_params: dict | None = dict(params)
        while next_url:
            resp = self._http.get(next_url, params=next_params)
            page = resp.json()
            if isinstance(page, list):
                results.extend(page)
            else:
                results.append(page)
            # 2 ページ目以降は Link ヘッダの URL に全パラメータが含まれる
            link = resp.headers.get("Link", "")
            match = _LINK_NEXT_RE.search(link)
            next_url = match.group(1) if match else None
            next_params = None
        return results

    # ------------------------------------------------------------------
    # Collector インターフェース
    # ------------------------------------------------------------------
    def fetch_since(self, since: datetime) -> list[Event]:
        """全リポジトリの since 以降のイベントを返す。"""
        events: list[Event] = []
        for repo in self._repos:
            try:
                events.extend(self._fetch_repo(repo, since))
            except Exception as exc:  # 1 リポジトリの失敗で全体を止めない
                logger.error("GitHub リポジトリ取得失敗 repo=%s: %s", repo, exc)
        events.sort(key=lambda e: e.ts)
        return events

    def fetch_items(self) -> list[ItemRecord]:
        """全リポジトリの PR / issue の現在状態を返す。"""
        items: list[ItemRecord] = []
        for repo in self._repos:
            try:
                items.extend(self._fetch_repo_items(repo))
            except Exception as exc:
                logger.error("GitHub アイテム取得失敗 repo=%s: %s", repo, exc)
        return items

    # ------------------------------------------------------------------
    # リポジトリ単位の取得
    # ------------------------------------------------------------------
    def _fetch_repo(self, repo: str, since: datetime) -> list[Event]:
        """1 リポジトリのコミット / PR / issue を Event 化する。"""
        since_iso = since.replace(microsecond=0).isoformat() + "Z"
        events: list[Event] = []

        # --- コミット ---
        commits = self._paginate(
            f"{API_ROOT}/repos/{repo}/commits",
            {"since": since_iso, "per_page": PER_PAGE},
        )
        for c in commits:
            commit_info = c.get("commit", {})
            author = (c.get("author") or {}).get("login") or commit_info.get(
                "author", {}
            ).get("name", "unknown")
            ts = _parse_iso(commit_info.get("author", {}).get("date"))
            if ts is None:
                continue
            events.append(
                Event(
                    source=self.source,
                    type="commit",
                    actor=author,
                    ts=ts,
                    ref=c.get("sha", ""),
                    payload={
                        "message": commit_info.get("message", ""),
                        "sha": c.get("sha", ""),
                        "url": c.get("html_url", ""),
                        "repo": repo,
                        "origin": "github",
                    },
                )
            )

        # --- PR(updated 降順。since より古くなったら打ち切り)---
        prs = self._paginate_until_old(
            f"{API_ROOT}/repos/{repo}/pulls",
            {"state": "all", "sort": "updated", "direction": "desc", "per_page": PER_PAGE},
            since,
        )
        for pr in prs:
            number = pr.get("number")
            item_key = f"github:pr:{number}"
            title = pr.get("title", "")
            url = pr.get("html_url", "")
            assignee = (pr.get("assignee") or {}).get("login")
            labels = [lbl.get("name") for lbl in pr.get("labels", [])]
            created = _parse_iso(pr.get("created_at"))
            merged = _parse_iso(pr.get("merged_at"))
            base_payload = {
                "item_key": item_key,
                "title": title,
                "number": number,
                "url": url,
                "assignee": assignee,
                "labels": labels,
                "created_at": pr.get("created_at"),
                "repo": repo,
                "origin": "github",
            }
            if created is not None and created >= since:
                events.append(
                    Event(self.source, "pr_opened", assignee or "unknown", created, f"pr-{number}", base_payload)
                )
            if merged is not None and merged >= since:
                events.append(
                    Event(self.source, "pr_merged", assignee or "unknown", merged, f"pr-{number}", base_payload)
                )

        # --- issue(pull_request キーを持つものは PR なので除外)---
        issues = self._paginate_until_old(
            f"{API_ROOT}/repos/{repo}/issues",
            {"state": "all", "sort": "updated", "direction": "desc", "per_page": PER_PAGE},
            since,
        )
        for issue in issues:
            if "pull_request" in issue:
                continue
            number = issue.get("number")
            item_key = f"github:issue:{number}"
            title = issue.get("title", "")
            url = issue.get("html_url", "")
            assignee = (issue.get("assignee") or {}).get("login")
            labels = [lbl.get("name") for lbl in issue.get("labels", [])]
            created = _parse_iso(issue.get("created_at"))
            closed = _parse_iso(issue.get("closed_at"))
            updated = _parse_iso(issue.get("updated_at"))
            state_reason = issue.get("state_reason")
            base_payload = {
                "item_key": item_key,
                "title": title,
                "number": number,
                "url": url,
                "assignee": assignee,
                "labels": labels,
                "repo": repo,
                "origin": "github",
            }
            if created is not None and created >= since:
                events.append(
                    Event(self.source, "issue_opened", assignee or "unknown", created, f"issue-{number}", base_payload)
                )
            if closed is not None and closed >= since:
                events.append(
                    Event(self.source, "issue_closed", assignee or "unknown", closed, f"issue-{number}-closed", base_payload)
                )
            if (
                issue.get("state") == "open"
                and state_reason == "reopened"
                and updated is not None
                and updated >= since
            ):
                events.append(
                    Event(self.source, "issue_reopened", assignee or "unknown", updated, f"issue-{number}-reopened", base_payload)
                )
        return events

    def _paginate_until_old(self, url: str, params: dict, since: datetime) -> list:
        """updated 降順のリストを、updated_at < since に達するまで取得する。"""
        results: list = []
        next_url: str | None = url
        next_params: dict | None = dict(params)
        while next_url:
            resp = self._http.get(next_url, params=next_params)
            page = resp.json()
            if not isinstance(page, list) or not page:
                break
            results.extend(page)
            oldest = _parse_iso(page[-1].get("updated_at"))
            if oldest is not None and oldest < since:
                break
            link = resp.headers.get("Link", "")
            match = _LINK_NEXT_RE.search(link)
            next_url = match.group(1) if match else None
            next_params = None
        return results

    def _fetch_repo_items(self, repo: str) -> list[ItemRecord]:
        """1 リポジトリの PR / issue の現在状態を ItemRecord 化する。"""
        items: list[ItemRecord] = []
        prs = self._paginate(
            f"{API_ROOT}/repos/{repo}/pulls",
            {"state": "all", "sort": "updated", "direction": "desc", "per_page": PER_PAGE},
        )
        for pr in prs:
            number = pr.get("number")
            if pr.get("merged_at"):
                status = "merged"
            elif pr.get("state") == "closed":
                status = "closed"
            else:
                status = "open"
            items.append(
                ItemRecord(
                    item_key=f"github:pr:{number}",
                    source=self.source,
                    type="pr",
                    title=pr.get("title", ""),
                    status=status,
                    assignee=(pr.get("assignee") or {}).get("login"),
                    payload={"number": number, "created_at": pr.get("created_at"), "repo": repo},
                )
            )
        issues = self._paginate(
            f"{API_ROOT}/repos/{repo}/issues",
            {"state": "all", "sort": "updated", "direction": "desc", "per_page": PER_PAGE},
        )
        for issue in issues:
            if "pull_request" in issue:
                continue
            number = issue.get("number")
            items.append(
                ItemRecord(
                    item_key=f"github:issue:{number}",
                    source=self.source,
                    type="issue",
                    title=issue.get("title", ""),
                    status="closed" if issue.get("state") == "closed" else "open",
                    assignee=(issue.get("assignee") or {}).get("login"),
                    payload={"number": number, "repo": repo},
                )
            )
        return items
