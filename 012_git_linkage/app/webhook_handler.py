"""GitHub Webhook 受信後の共通処理。
FastAPI(main.py)・Azure Functions(function_app.py)の両方から呼び出される。
"""

from __future__ import annotations

import json

import requests

from app import github_service as gh
from app import mattermost_service as mm
from app.azure_ai_service import call_summarize_diff


class WebhookError(Exception):
    """Webhook処理中に発生したエラー。呼び出し側でHTTPステータスに変換する。"""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def process_github_webhook(body: bytes, signature: str | None, event: str | None) -> dict:
    """
    GitHub Webhookのリクエスト内容を検証し、対象のPRマージであればAI要約をMattermostへ通知する

    Args
    -----------------
    - body: bytes,              リクエストボディの生バイト列(署名検証に使用)
    - signature: str | None,    X-Hub-Signature-256 ヘッダの値
    - event: str | None,        X-GitHub-Event ヘッダの値

    Returns
    -----------------
    - result: dict,             処理結果("ignored"または"notified")

    Raises
    -----------------
    - WebhookError,              署名検証失敗、または通知処理中にエラーが発生した場合

    """
    # 正規のGitHubからのリクエストか署名を検証する
    if not gh.verify_signature(body, signature):
        raise WebhookError(401, "署名の検証に失敗しました")

    # pull_request イベント以外（push等）は対象外
    if event != "pull_request":
        return {"result": "ignored", "reason": f"unsupported event: {event}"}

    payload = json.loads(body)

    # 監視対象リポジトリ・監視対象ブランチへのマージでなければ何もしない
    if not gh.is_target_merge_event(payload):
        return {"result": "ignored", "reason": "not a target merge event"}

    pr = payload["pull_request"]
    pr_number = pr["number"]

    try:
        # Step1: GitHub APIからPRの差分と変更ファイル一覧を取得
        diff_text = gh.get_pr_diff(pr_number)
        files_summary = gh.get_pr_files_summary(pr_number)
        # Step2: AIで変更内容を要約
        summary = call_summarize_diff(
            diff_text=diff_text,
            files_summary=files_summary,
            pr_number=pr_number,
            pr_title=pr["title"],
            author=pr["user"]["login"],
            base_branch=pr["base"]["ref"],
            head_branch=pr["head"]["ref"],
        )
        # Step3: 要約メッセージをMattermostへ投稿(DEBUG_FLAGに応じてDM/チャンネルを切り替え)
        mm.post_to_target(summary)
    except requests.HTTPError as exc:
        raise WebhookError(502, f"外部APIエラー: {exc}") from exc
    except Exception as exc:
        raise WebhookError(500, f"通知処理に失敗しました: {exc}") from exc

    return {"result": "notified", "pr_number": pr_number}
