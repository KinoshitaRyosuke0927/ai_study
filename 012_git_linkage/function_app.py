"""GitHub Webhook 連携アプリの Azure Functions エントリポイント(本番運用用)。
処理本体は app/webhook_handler.py に共通化しており、ローカル動作確認用の app/main.py(FastAPI)と同じロジックを使用する。
"""

from __future__ import annotations

import json
import logging

import azure.functions as func

from app.webhook_handler import WebhookError, process_github_webhook

app = func.FunctionApp()


@app.route(route="webhook/github", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def github_webhook(req: func.HttpRequest) -> func.HttpResponse:
    """
    GitHubからのWebhookを受信し、監視対象ブランチへのPRマージを検知したらAI要約をMattermostへ通知する
    """
    body = req.get_body()
    signature = req.headers.get("X-Hub-Signature-256")
    event = req.headers.get("X-GitHub-Event")

    try:
        result = process_github_webhook(body, signature, event)
    except WebhookError as exc:
        logging.exception("マージ通知処理に失敗しました")
        return func.HttpResponse(exc.detail, status_code=exc.status_code)

    return func.HttpResponse(
        json.dumps(result, ensure_ascii=False),
        status_code=200,
        mimetype="application/json",
    )
