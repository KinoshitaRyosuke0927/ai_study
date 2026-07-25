"""GitHub Webhook の署名検証、および GitHub API 経由でのPR差分取得を行う。"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path

from dotenv import load_dotenv
import requests

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_WEBHOOK_SECRET = os.environ["GITHUB_WEBHOOK_SECRET"]
GITHUB_OWNER = os.environ["GITHUB_OWNER"]
GITHUB_REPO = os.environ["GITHUB_REPO"]
TARGET_BRANCH = os.environ["TARGET_BRANCH"]

API_BASE = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
DIFF_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3.diff",
}
JSON_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}

# AIに渡すdiffの最大文字数（大きすぎるPRでトークン超過を防ぐ）
MAX_DIFF_CHARS = 12000


def verify_signature(payload_body: bytes, signature_header: str | None) -> bool:
    """X-Hub-Signature-256 ヘッダを検証し、正規のGitHub Webhookリクエストか確認する。"""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(), payload_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def is_target_merge_event(payload: dict) -> bool:
    """監視対象リポジトリ・監視対象ブランチへのPRマージイベントかどうか判定する。"""
    if payload.get("action") != "closed":
        return False

    pr = payload.get("pull_request", {})
    if not pr.get("merged"):
        return False

    repo = payload.get("repository", {})
    if repo.get("name") != GITHUB_REPO or repo.get("owner", {}).get("login") != GITHUB_OWNER:
        return False

    return pr.get("base", {}).get("ref") == TARGET_BRANCH


def get_pr_diff(pr_number: int) -> str:
    """PR番号から差分(unified diff)を取得する。長すぎる場合は先頭で切り詰める。"""
    res = requests.get(f"{API_BASE}/pulls/{pr_number}", headers=DIFF_HEADERS, timeout=15)
    res.raise_for_status()
    diff_text = res.text
    if len(diff_text) > MAX_DIFF_CHARS:
        diff_text = diff_text[:MAX_DIFF_CHARS] + "\n...(差分が大きいため以降省略)"
    return diff_text


def get_pr_files_summary(pr_number: int) -> list[dict]:
    """PRに含まれる変更ファイルの一覧(追加/削除行数付き)を取得する。"""
    res = requests.get(f"{API_BASE}/pulls/{pr_number}/files", headers=JSON_HEADERS, timeout=15)
    res.raise_for_status()
    return [
        {
            "filename": f["filename"],
            "status": f["status"],
            "additions": f["additions"],
            "deletions": f["deletions"],
        }
        for f in res.json()
    ]
