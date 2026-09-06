"""KPT分析(Mattermost / Trello / GitHub / 変更履歴 / 実装差分 の分析結果を
プロジェクト全体で束ね、Keep / Problem / Try を AI で導出する)。"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from config.runtime import load_runtime_config
from config.settings import get_settings

router = APIRouter()


class KptItemBody(BaseModel):
    """画面で編集した KPT カード 1 枚ぶん。"""

    kind: str
    title: str = ""
    detail: str = ""
    evidence: str = ""
    sources: list[str] = []
    importance: int = 0


class KptSaveBody(BaseModel):
    """KPT分析画面の保存リクエスト(カードを表示順で渡す)。"""

    items: list[KptItemBody] = []


def _kpt_response(a: dict[str, Any], *, cached: bool) -> dict[str, Any]:
    """保存済みの KPT分析を、画面が期待するレスポンス形へ整える。"""
    return {
        "analysis_id": a["id"],
        "cached": cached,
        "saved_at": a.get("created_at"),
        "model": a.get("model"),
        "source_ids": a.get("source_ids") or {},
        "stats": a.get("stats") or {},
        "keep": a.get("keep") or [],
        "problem": a.get("problem") or [],
        "try": a.get("try") or [],
    }


@router.post("/api/kpt/analyze")
async def api_kpt_analyze(force: bool = Query(default=False)) -> dict[str, Any]:
    """Mattermost / Trello / 変更履歴 / GitHub / 実装差分 / アクティビティ分析 を
    プロジェクト全体で 1 つに束ね、KPT法で Keep / Problem / Try を AI 分析する。
    """
    from pipeline import (
        analysis_store,
        changelog_store,
        github_activity_store,
        kpt_analysis as kpta,
        kpt_store,
        mm_store,
        project_config,
        trello_store,
        user_activity_store as uastore,
    )
    from viewers import github as github_view

    settings = get_settings()
    rc = load_runtime_config()
    repo = github_view._resolve_repo(settings, (rc.github_repo or "").strip())
    proj = project_config.load_project_config()

    # --- 6 ソースの最新結果を取得(直列 I/O を並列化)---
    mm = await asyncio.to_thread(mm_store.get_latest_account_analysis)
    tr = await asyncio.to_thread(trello_store.get_latest_account_analysis)
    cl = await asyncio.to_thread(changelog_store.get_latest_author_analysis)
    gh = await asyncio.to_thread(github_activity_store.get_activity_summary, repo)
    gh_hash = await asyncio.to_thread(github_activity_store.latest_content_hash, repo)
    sd = await asyncio.to_thread(analysis_store.get_latest_diff)
    ua = await asyncio.to_thread(uastore.get_latest_analysis)

    if not (mm or tr or cl or (gh and gh.get("activity_total")) or (sd and sd.get("items")) or (ua and ua.get("items"))):
        raise HTTPException(
            status_code=422,
            detail="先に「Mattermost/Trello/変更履歴/実装差分/アクティビティ」の分析、または「GitHub情報取得」の DB登録を実行してください",
        )

    # --- キャッシュキー: 各ソースの分析ID + settings.ini のハッシュ ---
    content_hash = hashlib.sha256(
        "|".join([
            str(mm["id"]) if mm else "-",
            str(tr["id"]) if tr else "-",
            str(cl["id"]) if cl else "-",
            gh_hash or "-",
            str(sd["id"]) if sd and sd.get("id") else "-",
            str(ua["id"]) if ua and ua.get("id") else "-",
            proj["raw_hash"] or "-",
        ]).encode("utf-8")
    ).hexdigest()
    if not force:
        cached = await asyncio.to_thread(kpt_store.find_cached_analysis, content_hash)
        if cached:
            return _kpt_response(cached, cached=True)

    bundle = kpta.build_bundle(mm, tr, cl, gh, sd, ua, proj.get("tool_context") or {})
    try:
        result = await asyncio.to_thread(kpta.analyze_kpt, settings, bundle)
    except kpta.KptAnalysisError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    items = [
        {"kind": kind, **it}
        for kind in ("keep", "problem", "try")
        for it in result.get(kind, [])
    ]
    saved = await asyncio.to_thread(
        kpt_store.save_analysis,
        content_hash=content_hash,
        model=kpta.MODEL_NAME,
        source_ids={
            "mattermost": mm["id"] if mm else None,
            "trello": tr["id"] if tr else None,
            "changelog": cl["id"] if cl else None,
            "github_content_hash": gh_hash,
            "spec_diff": sd["id"] if sd and sd.get("id") else None,
            "user_activity": ua["id"] if ua and ua.get("id") else None,
        },
        stats={
            "keep_count": len(result.get("keep", [])),
            "problem_count": len(result.get("problem", [])),
            "try_count": len(result.get("try", [])),
            "available_sources": bundle.get("available", []),
        },
        items=items,
    )
    return _kpt_response(saved, cached=False)


@router.get("/api/kpt/latest")
def api_kpt_latest() -> dict[str, Any]:
    """保存済みの最新の KPT分析。無ければ analysis_id=null。"""
    from pipeline import kpt_store

    a = kpt_store.get_latest_analysis()
    if a is None:
        return {"analysis_id": None, "keep": [], "problem": [], "try": []}
    return _kpt_response(a, cached=True)


@router.get("/api/kpt/runs")
def api_kpt_runs(limit: int = Query(default=30, le=200)) -> list[dict[str, Any]]:
    from pipeline import kpt_store

    return kpt_store.list_analyses(limit=limit)


@router.get("/api/kpt/runs/{analysis_id}")
def api_kpt_run(analysis_id: int) -> dict[str, Any]:
    from pipeline import kpt_store

    a = kpt_store.get_analysis(analysis_id)
    if not a:
        raise HTTPException(status_code=404, detail="分析結果が見つかりません")
    return _kpt_response(a, cached=True)


@router.put("/api/kpt/runs/{analysis_id}")
async def api_kpt_save(analysis_id: int, body: KptSaveBody) -> dict[str, Any]:
    """KPT分析画面で編集したカードの状態(列・並び順・重要度)を DB に保存する。"""
    from pipeline import kpt_analysis as kpta, kpt_store

    items: list[dict[str, Any]] = []
    for it in body.items:
        if it.kind not in ("keep", "problem", "try"):
            continue
        items.append({
            "kind": it.kind,
            "title": it.title,
            "detail": it.detail,
            "evidence": it.evidence,
            "sources": [s for s in it.sources if s in kpta.SOURCE_KEYS],
            "importance": max(0, min(5, it.importance)),
        })

    updated = await asyncio.to_thread(kpt_store.replace_items, analysis_id, items)
    if updated is None:
        raise HTTPException(status_code=404, detail="分析結果が見つかりません")
    return _kpt_response(updated, cached=True)
