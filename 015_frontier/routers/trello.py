"""Trello 情報取得・分析(ボードの取得、アカウント横断のAI分析)。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from config.runtime import load_runtime_config
from config.settings import get_settings
from routers.common import DESIGN_DETAIL_MAX_PARALLEL

logger = logging.getLogger("frontier.routers.trello")

router = APIRouter()


class TrelloFetchBody(BaseModel):
    """/api/trello/fetch のリクエストボディ。"""

    board_id: str


@router.get("/api/trello/boards")
def api_trello_boards() -> dict[str, Any]:
    """取得対象ボード設定のプルダウン用: 設定済みボードを名前付きで返す。"""
    from viewers import trello as trello_view

    settings = get_settings()
    rc = load_runtime_config()
    boards, err = trello_view.list_configured_boards(settings, rc.trello_board_ids)
    return {"boards": boards, "error": err}


@router.post("/api/trello/fetch")
def api_trello_fetch(body: TrelloFetchBody) -> dict[str, Any]:
    """指定ボードの現在の状況(リスト / カード / 詳細 / 活動)を返す。"""
    from viewers import trello as trello_view

    settings = get_settings()
    try:
        return trello_view.fetch_board(settings, body.board_id.strip())
    except trello_view.TrelloViewError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


def _trello_analysis_response(analysis: dict[str, Any], *, cached: bool) -> dict[str, Any]:
    """保存済みの Trello アカウント横断分析を、画面が期待するレスポンス形へ整える。"""
    stats = analysis.get("stats") or {}
    return {
        "analysis_id": analysis["id"],
        "cached": cached,
        "saved_at": analysis.get("created_at"),
        "board_ids": analysis.get("board_ids") or [],
        "themes": analysis.get("themes") or [],
        "account_count": len(analysis.get("accounts") or []),
        "accounts": analysis.get("accounts") or [],
        **stats,
    }


@router.post("/api/trello/analyze")
async def api_trello_analyze(force: bool = Query(default=False)) -> dict[str, Any]:
    """設定「Trello 取得ボード」のボードを DB へ蓄積し、アカウントごとにボード横断の
    活動(担当・コメント・操作)を AI で分析して返す。

    - tr_cards は card_id、tr_activity は action id で冪等に蓄積。
    - カード 1 枚 = 1 チャンクで embeddings へ source='trello' で埋め込み(既存 RAG が拾う)。
    - 同一入力(content_hash)の成功済み分析があれば再利用(force=true で無視)。
    """
    from viewers import trello as trello_view
    from pipeline import trello_analysis as ta, trello_ingest as ti, trello_store as tstore

    settings = get_settings()
    rc = load_runtime_config()
    board_ids = list(rc.trello_board_ids or [])
    if not board_ids:
        raise HTTPException(status_code=422, detail="設定画面で「Trello 取得ボード」を選択してください")

    # --- 各ボードを並列取得 ---
    async def _fetch(bid: str) -> dict[str, Any]:
        return await asyncio.to_thread(trello_view.fetch_board, settings, bid)

    try:
        fetched = await asyncio.gather(*(_fetch(b) for b in board_ids))
    except trello_view.TrelloViewError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    flat = ti.flatten_boards(list(fetched))
    if not flat["cards"]:
        raise HTTPException(status_code=422, detail="分析できるカードがありませんでした")

    # --- 同一入力の成功済み分析があれば再利用 ---
    content_hash = ti.compute_content_hash(board_ids, flat["cards"], flat["activities"])
    if not force:
        cached = await asyncio.to_thread(tstore.find_cached_account_analysis, content_hash)
        if cached:
            return _trello_analysis_response(cached, cached=True)

    # --- 蓄積 ---
    ing = await asyncio.to_thread(
        tstore.ingest_boards, board_ids=board_ids, flat=flat, content_hash=content_hash
    )

    # --- チャンク化 + 埋め込み(RAG 用。失敗しても分析は継続) ---
    try:
        emb = await asyncio.to_thread(
            tstore.store_card_chunks_and_embed,
            ti.build_card_chunks(flat["cards"], flat["activities"]),
        )
    except Exception:
        logger.exception("Trello チャンク/埋め込みに失敗(分析は継続)")
        emb = {"chunk_count": 0, "embedded_chunks": 0, "embedding_model": None}

    # --- アカウントごとのコンテキスト(決定的) ---
    contexts = ti.build_account_contexts(flat["cards"], flat["activities"])

    # --- 1 段目: 作業テーマ(失敗時は空) ---
    themes = await asyncio.to_thread(ta.list_team_themes, settings, flat["cards"])

    # --- 2 段目: アカウントごとに並列分析 ---
    sem = asyncio.Semaphore(DESIGN_DETAIL_MAX_PARALLEL)

    async def _one(acc: dict[str, Any]) -> dict[str, Any]:
        async with sem:
            return await asyncio.to_thread(ta.analyze_account, settings, acc, themes)

    results = await asyncio.gather(*(_one(c) for c in contexts), return_exceptions=True)

    accounts_out: list[dict[str, Any]] = []
    for acc, res in zip(contexts, results):
        base = {
            "username": acc["username"],
            "full_name": acc.get("full_name", ""),
            "stats": acc["stats"],
            "refs": acc["refs"],
        }
        if isinstance(res, Exception):
            logger.error("Trello アカウント分析に失敗 user=%s: %s", acc["username"], res)
            accounts_out.append({**base, "overview": "", "sections": [], "error": "このアカウントの分析に失敗しました"})
        else:
            accounts_out.append({**base, "overview": res["overview"], "sections": res["sections"]})

    # --- 保存 ---
    saved = await asyncio.to_thread(
        tstore.save_account_analysis,
        ingest_run_id=ing["ingest_run_id"],
        board_ids=board_ids,
        content_hash=content_hash,
        model=ta.MODEL_NAME,
        themes=themes,
        stats={
            "board_count": ing["board_count"],
            "card_count": ing["card_count"],
            "activity_count": ing["activity_count"],
            "account_count": len(contexts),
            "chunk_count": emb["chunk_count"],
            "embedded_chunks": emb["embedded_chunks"],
        },
        accounts=accounts_out,
    )
    return _trello_analysis_response(saved, cached=False)


@router.get("/api/trello/analysis/latest")
def api_trello_analysis_latest() -> dict[str, Any]:
    """保存済みの最新の Trello アカウント横断分析。無ければ analysis_id=null。"""
    from pipeline import trello_store as tstore

    a = tstore.get_latest_account_analysis()
    if a is None:
        return {"analysis_id": None, "account_count": 0, "accounts": []}
    return _trello_analysis_response(a, cached=True)


@router.get("/api/trello/analysis/runs")
def api_trello_analysis_runs(limit: int = Query(default=30, le=200)) -> list[dict[str, Any]]:
    """Trello アカウント横断分析の一覧(新しい順)。"""
    from pipeline import trello_store as tstore

    return tstore.list_account_analyses(limit=limit)


@router.get("/api/trello/analysis/runs/{analysis_id}")
def api_trello_analysis_run(analysis_id: int) -> dict[str, Any]:
    """保存済みの Trello アカウント横断分析 1 件を、分析画面のレスポンス形で返す。"""
    from pipeline import trello_store as tstore

    a = tstore.get_account_analysis(analysis_id)
    if not a:
        raise HTTPException(status_code=404, detail="分析結果が見つかりません")
    return _trello_analysis_response(a, cached=True)
