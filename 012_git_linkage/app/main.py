"""GitHub Webhook 連携アプリの FastAPI エントリポイント。
指定ブランチへのPRマージを検知し、差分をAIで要約してMattermostへ通知する。
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Header, HTTPException, Request
import requests

from app import github_service as gh
from app import mattermost_service as mm
from app.azure_ai_service import call_summarize_diff

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="Git マージ通知連携", version="1.0.0")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
) -> dict:
    body = await request.body()

    if not gh.verify_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="署名の検証に失敗しました")

    if x_github_event != "pull_request":
        return {"result": "ignored", "reason": f"unsupported event: {x_github_event}"}

    payload = await request.json()

    if not gh.is_target_merge_event(payload):
        return {"result": "ignored", "reason": "not a target merge event"}

    pr = payload["pull_request"]
    pr_number = pr["number"]

    try:
        diff_text = gh.get_pr_diff(pr_number)
        files_summary = gh.get_pr_files_summary(pr_number)
        summary = call_summarize_diff(
            diff_text=diff_text,
            files_summary=files_summary,
            pr_number=pr_number,
            pr_title=pr["title"],
            author=pr["user"]["login"],
            base_branch=pr["base"]["ref"],
            head_branch=pr["head"]["ref"],
        )
        mm.post_dm_to_target(summary)
    except requests.HTTPError as exc:
        logger.exception("外部API呼び出しに失敗しました")
        raise HTTPException(status_code=502, detail=f"外部APIエラー: {exc}") from exc
    except Exception as exc:
        logger.exception("マージ通知処理に失敗しました")
        raise HTTPException(status_code=500, detail=f"通知処理に失敗しました: {exc}") from exc

    return {"result": "notified", "pr_number": pr_number}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8001)
