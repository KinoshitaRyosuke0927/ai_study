"""「コード情報取得」画面用: 設定「GitHub リポジトリ名称」のリポジトリ全体から
ソースコードを取得する。

分析パイプラインとは独立しており、DB へは保存しない(結果は画面側でメモリ保持)。
GitHub リポジトリの既定ブランチから、ソース拡張子のファイルのみを、
ベンダーディレクトリ・生成物・ロックファイルなどを除外して取得する。
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

MAX_FILES = 400                       # 取得するファイル数の上限
MAX_CONTENT_BYTES = 128 * 1024        # 1 ファイルの内容の上限(超過分は打ち切り)
MAX_TOTAL_BYTES = 6 * 1024 * 1024     # 取得内容の合計の上限(超過後はメタのみ)

# 取得対象とするソース拡張子
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".vue", ".mjs", ".cjs",
    ".go", ".rb", ".java", ".cs", ".php", ".rs", ".kt", ".swift", ".scala",
    ".sql", ".html", ".htm", ".css", ".scss", ".sh",
}
# 拡張子に依らず取得したい設定・ビルドファイル名(小文字で比較)
CONFIG_FILENAMES = {
    "dockerfile", "requirements.txt", "pyproject.toml", "package.json",
    "schema.sql", "docker-compose.yml", "docker-compose.yaml",
}
# パス中にこのディレクトリ名を含むファイルは除外する
EXCLUDE_DIRS = {
    "node_modules", ".venv", "venv", "env", ".git", "__pycache__",
    "dist", "build", "out", "vendor", ".next", ".nuxt", "coverage",
    ".pytest_cache", "site-packages", "migrations", ".mypy_cache", ".idea",
}
# この接尾辞・ファイル名は除外する
EXCLUDE_SUFFIXES = (".min.js", ".min.css", ".map", ".lock", ".snap")
EXCLUDE_FILENAMES = {
    "package-lock.json", "poetry.lock", "yarn.lock", "pnpm-lock.yaml",
}


class CodeViewError(Exception):
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


def _want_file(path: str) -> bool:
    """このパスのファイルを取得対象にするか判定する。"""
    parts = path.split("/")
    # 除外ディレクトリを含むパスは対象外
    if any(seg in EXCLUDE_DIRS for seg in parts[:-1]):
        return False
    low = parts[-1].lower()
    if low in EXCLUDE_FILENAMES or low.endswith(EXCLUDE_SUFFIXES):
        return False
    if low in CONFIG_FILENAMES:
        return True
    ext = low[low.rfind("."):] if "." in low else ""
    return ext in CODE_EXTENSIONS


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


def fetch_code_files(settings: Settings, configured_repo: str) -> dict[str, Any]:
    """リポジトリ全体のソースコードをファイルごとに返す。

    Raises:
        CodeViewError: リポジトリ未設定、アクセス不可、ファイル無しの場合。
    """
    if not settings.github_token or settings.github_token == "changeme":
        raise CodeViewError("GitHub トークンが未設定です(.env の GITHUB_TOKEN)")
    repo = _resolve_repo(settings, configured_repo)
    if not repo or "/" not in repo:
        raise CodeViewError("設定画面で「GitHub リポジトリ名称」を owner/repo 形式で設定してください")

    api = _GitHubClient(settings)

    # 既定ブランチ
    try:
        repo_info = api.get(f"/repos/{repo}")
    except Exception as exc:
        logger.error("GitHub リポジトリ取得失敗 repo=%s: %s", repo, exc)
        raise CodeViewError(
            f"リポジトリ '{repo}' にアクセスできません(名称/権限/トークンを確認してください): {exc}"
        ) from exc
    branch = repo_info.get("default_branch") or "main"

    # 再帰ツリーで全 blob を列挙
    try:
        tree = api.get(f"/repos/{repo}/git/trees/{branch}", params={"recursive": "1"})
    except Exception as exc:
        logger.error("GitHub ツリー取得失敗 repo=%s branch=%s: %s", repo, branch, exc)
        raise CodeViewError(f"リポジトリのファイル一覧を取得できませんでした: {exc}") from exc

    blobs = [
        e
        for e in tree.get("tree", [])
        if e.get("type") == "blob" and _want_file(e.get("path", ""))
    ]
    if not blobs:
        raise CodeViewError("対象のソースファイルが見つかりませんでした")

    blobs.sort(key=lambda e: e.get("path", ""))
    truncated_list = len(blobs) > MAX_FILES or bool(tree.get("truncated"))
    blobs = blobs[:MAX_FILES]

    files_out: list[dict[str, Any]] = []
    total_bytes = 0
    for e in blobs:
        path = e.get("path", "")
        entry: dict[str, Any] = {
            "path": path,
            "name": path,  # リポジトリルートからの相対パスをそのまま名前に使う
            "size": e.get("size", 0),
            "url": f"https://github.com/{repo}/blob/{branch}/{path}",
            "content": "",
            "binary": False,
            "truncated": False,
        }
        # 合計上限を超えたら以降はメタ情報のみ(内容は取得しない)
        if total_bytes >= MAX_TOTAL_BYTES:
            entry["binary"] = True
            entry["truncated"] = True
            files_out.append(entry)
            continue
        try:
            blob = api.get(f"/repos/{repo}/git/blobs/{e.get('sha')}")
            text, is_binary, is_trunc = _decode_blob(blob.get("content", ""))
            entry["content"] = text
            entry["binary"] = is_binary
            entry["truncated"] = is_trunc
            total_bytes += len(text)
        except Exception as exc:  # 1 ファイルの失敗で全体を止めない
            logger.warning("GitHub blob 取得失敗 repo=%s path=%s: %s", repo, path, exc)
            entry["binary"] = True
        files_out.append(entry)

    return {
        "repo": repo,
        "branch": branch,
        "tree_sha": tree.get("sha"),
        "path": "(リポジトリ全体)",
        "file_count": len(files_out),
        "truncated": truncated_list,
        "files": files_out,
    }
