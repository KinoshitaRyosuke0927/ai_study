"""「設計書情報取得」画面用: 設定「設計書パス」フォルダ配下のファイル内容を取得する。

分析パイプラインとは独立しており、DB へは保存しない(結果は画面側でメモリ保持)。
GitHub リポジトリ(設定「GitHub リポジトリ名称」)の既定ブランチから、
設定「設計書パス」配下の全ファイルを取得する。
"""

from __future__ import annotations

import base64
import binascii
import logging
from typing import Any

from collectors.base import HttpClient
from config.settings import Settings

logger = logging.getLogger(__name__)

API_ROOT = "https://api.github.com"

MAX_FILES = 200                 # 取得するファイル数の上限
MAX_CONTENT_BYTES = 512 * 1024  # 表示するファイル内容の上限(超過分は打ち切り)


class DesignViewError(Exception):
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

    def get(self, path: str, params: dict | None = None) -> Any:
        return self._http.get_json(f"{API_ROOT}{path}", params=params)


def _resolve_repo(settings: Settings, configured: str) -> str:
    """設定のリポジトリ名(空なら .env の 1 つ目)を owner/repo で返す。"""
    repo = (configured or "").strip().strip("/")
    if not repo:
        repos = settings.github_repo_list
        repo = repos[0] if repos else ""
    return repo


def _decode_blob(content_b64: str) -> tuple[str, bool, bool]:
    """base64 のファイル内容を復号する。

    Returns:
        (text, is_binary, is_truncated)
    """
    try:
        raw = base64.b64decode(content_b64 or "")
    except (binascii.Error, ValueError):
        return "", True, False
    truncated = False
    if len(raw) > MAX_CONTENT_BYTES:
        raw = raw[:MAX_CONTENT_BYTES]
        truncated = True
    if b"\x00" in raw:
        return "", True, truncated
    try:
        return raw.decode("utf-8"), False, truncated
    except UnicodeDecodeError:
        return "", True, truncated


def fetch_design_files(
    settings: Settings, configured_repo: str, design_path: str
) -> dict[str, Any]:
    """設計書パス配下の全ファイル内容を返す。

    Raises:
        DesignViewError: リポジトリ / パス未設定、アクセス不可、ファイル無しの場合。
    """
    if not settings.github_token or settings.github_token == "changeme":
        raise DesignViewError("GitHub トークンが未設定です(.env の GITHUB_TOKEN)")
    repo = _resolve_repo(settings, configured_repo)
    if not repo or "/" not in repo:
        raise DesignViewError("設定画面で「GitHub リポジトリ名称」を owner/repo 形式で設定してください")
    design_path = (design_path or "").strip().strip("/")
    if not design_path:
        raise DesignViewError("設定画面で「設計書パス」を設定してください")

    api = _GitHubClient(settings)

    # 既定ブランチ
    try:
        repo_info = api.get(f"/repos/{repo}")
    except Exception as exc:
        logger.error("GitHub リポジトリ取得失敗 repo=%s: %s", repo, exc)
        raise DesignViewError(
            f"リポジトリ '{repo}' にアクセスできません(名称/権限/トークンを確認してください): {exc}"
        ) from exc
    branch = repo_info.get("default_branch") or "main"

    # 再帰ツリーで design_path 配下の blob を列挙
    try:
        tree = api.get(f"/repos/{repo}/git/trees/{branch}", params={"recursive": "1"})
    except Exception as exc:
        logger.error("GitHub ツリー取得失敗 repo=%s branch=%s: %s", repo, branch, exc)
        raise DesignViewError(f"リポジトリのファイル一覧を取得できませんでした: {exc}") from exc

    prefix = design_path + "/"
    blobs = [
        e
        for e in tree.get("tree", [])
        if e.get("type") == "blob"
        and (e.get("path", "") == design_path or e.get("path", "").startswith(prefix))
    ]
    if not blobs:
        raise DesignViewError(f"設計書パス '{design_path}' 配下にファイルが見つかりません")

    blobs.sort(key=lambda e: e.get("path", ""))
    truncated_list = len(blobs) > MAX_FILES
    blobs = blobs[:MAX_FILES]

    files_out: list[dict[str, Any]] = []
    for e in blobs:
        path = e.get("path", "")
        rel = path[len(prefix):] if path.startswith(prefix) else path
        entry: dict[str, Any] = {
            "path": path,
            "name": rel,
            "size": e.get("size", 0),
            "url": f"https://github.com/{repo}/blob/{branch}/{path}",
            "content": "",
            "binary": False,
            "truncated": False,
        }
        try:
            blob = api.get(f"/repos/{repo}/git/blobs/{e.get('sha')}")
            text, is_binary, is_trunc = _decode_blob(blob.get("content", ""))
            entry["content"] = text
            entry["binary"] = is_binary
            entry["truncated"] = is_trunc
        except Exception as exc:  # 1 ファイルの失敗で全体を止めない
            logger.warning("GitHub blob 取得失敗 repo=%s path=%s: %s", repo, path, exc)
            entry["binary"] = True
        files_out.append(entry)

    return {
        "repo": repo,
        "branch": branch,
        "path": design_path,
        "file_count": len(files_out),
        "truncated": truncated_list,
        "files": files_out,
    }
