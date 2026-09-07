"""Q&A画面のチャットAPI。

このプロジェクトで蓄積された分析結果・元データを Tool Calling 経由で検索して回答する
(実処理は pipeline/qa_chat.py・qa_tools.py に委譲)。回答本文に加えて、根拠にした
ファイル/分析結果(citations)も返し、画面の右エリアに表示できるようにする。
会話履歴はサーバー側で保持しない(画面が毎回全履歴を送る、ステートレスな設計)。
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class QaMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class QaChatBody(BaseModel):
    """/api/qa/chat のリクエストボディ(画面側が保持する会話履歴をそのまま送る)。"""

    history: list[QaMessage]


@router.post("/api/qa/chat")
async def api_qa_chat(body: QaChatBody) -> dict[str, Any]:
    """会話履歴に対する応答を返す。"""
    from config.settings import get_settings
    from pipeline import qa_chat

    if not body.history:
        raise HTTPException(status_code=422, detail="history が空です")

    settings = get_settings()
    history = [m.model_dump() for m in body.history]
    try:
        result = await asyncio.to_thread(qa_chat.call_chat, settings, history)
    except qa_chat.QaChatError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return result
