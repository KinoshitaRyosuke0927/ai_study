"""GitHub Webhook 連携アプリの FastAPI エントリポイント(ローカル動作確認用)。
指定ブランチへのPRマージを検知し、差分をAIで要約してMattermostへ通知する。
本番(Azure Functions)向けの処理本体は webhook_handler.py に共通化している。
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Header, HTTPException, Request

from app.webhook_handler import WebhookError, process_github_webhook

logger = logging.getLogger("uvicorn.error")

# アプリケーション実行
app = FastAPI(title="Git マージ通知連携", version="1.0.0")


@app.get("/api/health")
def health() -> dict:
    """
    ヘルスチェックエンドポイント
    """
    return {"status": "ok"}


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
) -> dict:
    """
    GitHubからのWebhookを受信し、監視対象ブランチへのPRマージを検知したらAI要約をMattermostへ通知する
    """
    # 署名検証のため、JSONパース前に生のリクエストボディを取得する
    body = await request.body()

    try:
        return process_github_webhook(body, x_hub_signature_256, x_github_event)
    except WebhookError as exc:
        logger.exception("マージ通知処理に失敗しました")
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


# サーバ起動用
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8001)
