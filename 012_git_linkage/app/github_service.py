"""GitHub Webhook の署名検証、および GitHub API 経由でのPR差分取得を行う。"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path

from dotenv import load_dotenv
import requests

# 環境変数(.env)を読み込む
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

## GitHub 連携に必要な情報を環境変数から取得
# GitHub API呼び出し用のPersonal Access Token
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
# GitHub WebhookのSecret（署名検証に使用）
GITHUB_WEBHOOK_SECRET = os.environ["GITHUB_WEBHOOK_SECRET"]
# 監視対象リポジトリのオーナー名
GITHUB_OWNER = os.environ["GITHUB_OWNER"]
# 監視対象リポジトリ名
GITHUB_REPO = os.environ["GITHUB_REPO"]
# マージ検知の対象とするブランチ名
TARGET_BRANCH = os.environ["TARGET_BRANCH"]

# GitHub REST APIのベースURL（対象リポジトリ固定）
API_BASE = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
# diff形式で取得する際のヘッダー
DIFF_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3.diff",
}
# JSON形式で取得する際のヘッダー
JSON_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}

# AIに渡すdiffの最大文字数（大きすぎるPRでトークン超過を防ぐ）
MAX_DIFF_CHARS = 12000


def verify_signature(payload_body: bytes, signature_header: str | None) -> bool:
    """
    X-Hub-Signature-256 ヘッダを検証し、正規のGitHub Webhookリクエストか確認する

    Args
    -----------------
    - payload_body: bytes,               リクエストボディの生バイト列
    - signature_header: str | None,      X-Hub-Signature-256 ヘッダの値

    Returns
    -----------------
    - is_valid: bool,                    署名が正しければTrue

    """
    # ヘッダが無い、または形式が不正な場合は即座に不正と判定
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    # Secretを使ってリクエストボディからHMAC-SHA256署名を計算
    expected = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(), payload_body, hashlib.sha256
    ).hexdigest()
    # タイミング攻撃を避けるため定時間比較を行う
    return hmac.compare_digest(expected, signature_header)


def is_target_merge_event(payload: dict) -> bool:
    """
    監視対象リポジトリ・監視対象ブランチへのPRマージイベントかどうか判定する

    Args
    -----------------
    - payload: dict,   GitHub Webhookから受信したペイロード（pull_requestイベント）

    Returns
    -----------------
    - is_target: bool, 通知対象のマージイベントであればTrue

    """
    # closeイベント以外（オープン・レビュー等）は対象外
    if payload.get("action") != "closed":
        return False

    pr = payload.get("pull_request", {})
    # closeされていてもマージされていない（クローズのみ）場合は対象外
    if not pr.get("merged"):
        return False

    # 監視対象外のリポジトリからの通知は無視する
    repo = payload.get("repository", {})
    if repo.get("name") != GITHUB_REPO or repo.get("owner", {}).get("login") != GITHUB_OWNER:
        return False

    # マージ先ブランチが監視対象ブランチと一致するかを確認
    return pr.get("base", {}).get("ref") == TARGET_BRANCH


def get_pr_diff(pr_number: int) -> str:
    """
    PR番号から差分(unified diff)を取得する。長すぎる場合は先頭で切り詰める

    Args
    -----------------
    - pr_number: int,   対象PRの番号

    Returns
    -----------------
    - diff_text: str,   PRの差分テキスト（MAX_DIFF_CHARSを超える場合は末尾を省略）

    """
    res = requests.get(f"{API_BASE}/pulls/{pr_number}", headers=DIFF_HEADERS, timeout=15)
    res.raise_for_status()
    diff_text = res.text
    # AIへの入力トークン数が膨らみすぎないよう、大きすぎるdiffは切り詰める
    if len(diff_text) > MAX_DIFF_CHARS:
        diff_text = diff_text[:MAX_DIFF_CHARS] + "\n...(差分が大きいため以降省略)"
    return diff_text


def get_pr_files_summary(pr_number: int) -> list[dict]:
    """
    PRに含まれる変更ファイルの一覧(追加/削除行数付き)を取得する

    Args
    -----------------
    - pr_number: int,       対象PRの番号

    Returns
    -----------------
    - files: list[dict],    変更ファイルごとの情報（filename, status, additions, deletions）のリスト

    """
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
