"""Mattermost 情報取得・分析(投稿の取得、アカウント横断のAI分析)。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from config.runtime import load_runtime_config
from config.settings import get_settings
from routers.common import DESIGN_DETAIL_MAX_PARALLEL

logger = logging.getLogger("frontier.routers.mattermost")

router = APIRouter()


class MattermostFetchBody(BaseModel):
    """/api/mattermost/fetch のリクエストボディ。"""

    mode: str  # "current"(取得開始日〜最新日)/ "range"(開始日〜終了日)
    latest_date: str | None = None  # mode=current の最新日 "YYYY-MM-DD"
    start_date: str | None = None   # mode=range の開始日
    end_date: str | None = None     # mode=range の終了日


def _resolve_mm_window(
    mode: str, latest_date: str | None, start_date: str | None, end_date: str | None, rc: Any
):
    """Mattermost 取得/分析の対象期間 [start_d, end_d] を確定する。"""
    from datetime import date as _date

    def _parse(label: str, value: str | None) -> _date:
        if not value:
            raise HTTPException(status_code=422, detail=f"{label} を指定してください")
        try:
            return _date.fromisoformat(value)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"{label} は YYYY-MM-DD 形式で指定してください")

    if mode == "current":
        if rc.since_date is None:
            raise HTTPException(
                status_code=422, detail="設定画面で「データ取得開始日時」を設定してください"
            )
        return rc.since_date, _parse("最新日", latest_date)
    if mode == "range":
        return _parse("開始日", start_date), _parse("終了日", end_date)
    raise HTTPException(status_code=422, detail="mode は current / range のいずれか")


@router.post("/api/mattermost/fetch")
def api_mattermost_fetch(body: MattermostFetchBody) -> dict[str, Any]:
    """設定チャンネルの投稿を、指定期間ぶんチャンネル別・スレッド構造で返す。"""
    from viewers import mattermost as mattermost_view

    settings = get_settings()
    rc = load_runtime_config()
    start_d, end_d = _resolve_mm_window(
        body.mode, body.latest_date, body.start_date, body.end_date, rc
    )

    try:
        result = mattermost_view.fetch_posts(
            settings, rc.mattermost_channel_ids, start_d, end_d
        )
    except mattermost_view.MattermostViewError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    result["mode"] = body.mode
    return result


class MattermostAnalyzeBody(BaseModel):
    """/api/mattermost/analyze のリクエストボディ(fetch と同じ期間指定)。"""

    mode: str = "current"
    latest_date: str | None = None
    start_date: str | None = None
    end_date: str | None = None


def _mm_analysis_response(analysis: dict[str, Any], *, cached: bool) -> dict[str, Any]:
    """保存済みのアカウント横断分析を、画面が期待するレスポンス形へ整える。"""
    stats = analysis.get("stats") or {}
    return {
        "analysis_id": analysis["id"],
        "cached": cached,
        "saved_at": analysis.get("created_at"),
        "window": {"start": analysis.get("window_start"), "end": analysis.get("window_end")},
        "channel_ids": analysis.get("channel_ids") or [],
        "topics": analysis.get("topics") or [],
        "account_count": len(analysis.get("accounts") or []),
        "accounts": analysis.get("accounts") or [],
        **stats,
    }


@router.post("/api/mattermost/analyze")
async def api_mattermost_analyze(
    body: MattermostAnalyzeBody, force: bool = Query(default=False)
) -> dict[str, Any]:
    """「現在情報取得」で得られる投稿をチャンネル/アカウント別に DB へ蓄積し、
    アカウントごとにチャンネル横断の発言・活動を AI で分析して返す。

    - mm_posts へ post_id で冪等に蓄積(期間が重複しても増えない)。
    - 会話はスレッド単位でチャンク化し、embeddings へ source='mattermost' で埋め込み
      (既存 /api/search の RAG がそのまま Mattermost も検索対象にする)。
    - 同一入力(content_hash)の成功済み分析があれば再利用(force=true で無視)。
    """
    from viewers import mattermost as mattermost_view
    from pipeline import mm_analysis, mm_ingest, mm_store

    settings = get_settings()
    rc = load_runtime_config()
    start_d, end_d = _resolve_mm_window(
        body.mode, body.latest_date, body.start_date, body.end_date, rc
    )
    channel_ids = list(rc.mattermost_channel_ids or [])

    # --- 取得 ---
    try:
        fetched = await asyncio.to_thread(
            mattermost_view.fetch_posts, settings, channel_ids, start_d, end_d
        )
    except mattermost_view.MattermostViewError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    posts = mm_ingest.flatten_posts(fetched)
    if not posts:
        raise HTTPException(status_code=422, detail="対象期間に分析できる投稿がありませんでした")

    # --- 同一入力の成功済み分析があれば再利用 ---
    content_hash = mm_ingest.compute_content_hash(
        channel_ids, start_d.isoformat(), end_d.isoformat(), posts
    )
    if not force:
        cached = await asyncio.to_thread(mm_store.find_cached_account_analysis, content_hash)
        if cached:
            return _mm_analysis_response(cached, cached=True)

    # --- 蓄積(mm_channels / mm_users / mm_posts) ---
    ing = await asyncio.to_thread(
        mm_store.ingest_posts,
        mode=body.mode,
        channel_ids=channel_ids,
        window_start=start_d,
        window_end=end_d,
        posts=posts,
        content_hash=content_hash,
    )

    # --- チャンク化 + 埋め込み(RAG 用。失敗しても分析は継続) ---
    try:
        emb = await asyncio.to_thread(
            mm_store.store_chunks_and_embed, mm_ingest.build_chunks(posts)
        )
    except Exception:
        logger.exception("Mattermost チャンク/埋め込みに失敗(分析は継続)")
        emb = {"chunk_count": 0, "embedded_chunks": 0, "embedding_model": None}

    # --- アカウントごとのコンテキスト(決定的) ---
    contexts = mm_ingest.build_account_contexts(posts)

    # --- 1 段目: チーム内トピック(失敗時は空) ---
    topics = await asyncio.to_thread(mm_analysis.list_team_topics, settings, contexts)

    # --- 2 段目: アカウントごとに並列分析(010_ai_reviewer の並列処理を参考) ---
    sem = asyncio.Semaphore(DESIGN_DETAIL_MAX_PARALLEL)

    async def _one(acc: dict[str, Any]) -> dict[str, Any]:
        async with sem:
            return await asyncio.to_thread(mm_analysis.analyze_account, settings, acc, topics)

    results = await asyncio.gather(*(_one(c) for c in contexts), return_exceptions=True)

    accounts_out: list[dict[str, Any]] = []
    for acc, res in zip(contexts, results):
        base = {
            "user_id": acc["user_id"],
            "username": acc["username"],
            "stats": acc["stats"],
            "ref_posts": acc["ref_posts"],
        }
        if isinstance(res, Exception):
            logger.error("Mattermost アカウント分析に失敗 user=%s: %s", acc["username"], res)
            accounts_out.append({**base, "overview": "", "sections": [], "error": "このアカウントの分析に失敗しました"})
        else:
            accounts_out.append({**base, "overview": res["overview"], "sections": res["sections"]})

    # --- 保存して、保存後の分析を返す ---
    saved = await asyncio.to_thread(
        mm_store.save_account_analysis,
        ingest_run_id=ing["ingest_run_id"],
        window_start=start_d,
        window_end=end_d,
        channel_ids=channel_ids,
        content_hash=content_hash,
        model=mm_analysis.MODEL_NAME,
        topics=topics,
        stats={
            "mode": body.mode,
            "post_count": ing["post_count"],
            "channel_count": ing["channel_count"],
            "account_count": len(contexts),
            "chunk_count": emb["chunk_count"],
            "embedded_chunks": emb["embedded_chunks"],
        },
        accounts=accounts_out,
    )
    return _mm_analysis_response(saved, cached=False)


@router.get("/api/mattermost/analysis/latest")
def api_mm_analysis_latest() -> dict[str, Any]:
    """保存済みの最新のアカウント横断分析。無ければ analysis_id=null。"""
    from pipeline import mm_store

    a = mm_store.get_latest_account_analysis()
    if a is None:
        return {"analysis_id": None, "account_count": 0, "accounts": []}
    return _mm_analysis_response(a, cached=True)


@router.get("/api/mattermost/analysis/runs")
def api_mm_analysis_runs(limit: int = Query(default=30, le=200)) -> list[dict[str, Any]]:
    """アカウント横断分析の一覧(新しい順)。"""
    from pipeline import mm_store

    return mm_store.list_account_analyses(limit=limit)


@router.get("/api/mattermost/analysis/runs/{analysis_id}")
def api_mm_analysis_run(analysis_id: int) -> dict[str, Any]:
    """保存済みのアカウント横断分析 1 件を、分析画面のレスポンス形で返す。"""
    from pipeline import mm_store

    a = mm_store.get_account_analysis(analysis_id)
    if not a:
        raise HTTPException(status_code=404, detail="分析結果が見つかりません")
    return _mm_analysis_response(a, cached=True)
