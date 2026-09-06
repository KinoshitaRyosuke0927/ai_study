"""実装差分解析(設計書分析 と コード分析 の突き合わせ)。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from config.runtime import load_runtime_config
from config.settings import get_settings
from routers.common import DESIGN_DETAIL_MAX_PARALLEL

logger = logging.getLogger("frontier.routers.spec_diff")

router = APIRouter()


def _spec_diff_response(diff: dict[str, Any]) -> dict[str, Any]:
    """保存済み diff を、画面が期待するレスポンス形へ整える。"""
    stats = diff.get("stats") or {}
    items = diff.get("items") or []
    # 重大度別の件数(ダッシュボードのカード表示に使う)
    severity_counts = {"high": 0, "mid": 0, "low": 0}
    for it in items:
        sev = it.get("severity")
        if sev in severity_counts:
            severity_counts[sev] += 1
    return {
        "diff_id": diff["id"],
        "repo": diff["repo"],
        "design_run_id": diff["design_run_id"],
        "code_run_id": diff["code_run_id"],
        "diff_count": diff["diff_count"],
        "severity_counts": severity_counts,
        "created_at": diff.get("created_at"),
        "items": items,
        **stats,
    }


@router.post("/api/spec-diff/analyze")
async def api_spec_diff_analyze() -> dict[str, Any]:
    """DB の最新のコード分析結果と設計書分析結果を機能ごとに AI で突き合わせ、
    相違点を抽出して spec_code_diffs / spec_code_diff_items へ保存する。
    """
    from pipeline import analysis_store
    from pipeline import spec_code_diff as scd

    settings = get_settings()
    rc = load_runtime_config()
    repo = (rc.github_repo or "").strip()

    # --- 突き合わせる設計書分析 / コード分析の最新 run を取得(repo 一致を優先、無ければ全体の最新)---
    design_run = await asyncio.to_thread(analysis_store.get_latest_run, "design", repo or None)
    code_run = await asyncio.to_thread(analysis_store.get_latest_run, "code", repo or None)
    if design_run is None:
        design_run = await asyncio.to_thread(analysis_store.get_latest_run, "design", None)
    if code_run is None:
        code_run = await asyncio.to_thread(analysis_store.get_latest_run, "code", None)
    if design_run is None or code_run is None:
        raise HTTPException(
            status_code=422,
            detail="先に「設計書情報取得」と「コード情報取得」で機能分析を実行してください",
        )

    # --- 1 段目: 機能の対応付け ---
    try:
        paired = await asyncio.to_thread(
            scd.prepare_pairs, settings, design_run, code_run
        )
    except scd.SpecCodeDiffError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    pairs = paired["pairs"]

    # --- 2 段目: ペアごとに相違点を並列抽出(010_ai_reviewer の並列処理を参考)---
    sem = asyncio.Semaphore(DESIGN_DETAIL_MAX_PARALLEL)

    async def _diff(pair: tuple[dict[str, Any], dict[str, Any]]) -> list[dict[str, Any]]:
        d_feat, c_feat = pair
        async with sem:
            return await asyncio.to_thread(scd.diff_pair, settings, d_feat, c_feat)

    results = await asyncio.gather(*(_diff(p) for p in pairs), return_exceptions=True)

    items: list[dict[str, Any]] = []
    for pair, res in zip(pairs, results):
        if isinstance(res, Exception):
            logger.error("実装差分解析 比較に失敗 feature=%s: %s", pair[0].get("name"), res)
            continue
        items.extend(res)

    # --- 未対応の機能もそれ自体が差分(未実装 / 設計書に無い)---
    for feat in paired["design_only"]:
        items.append(scd.unmatched_item(feat, "design_only"))
    for feat in paired["code_only"]:
        items.append(scd.unmatched_item(feat, "code_only"))

    # --- 保存 ---
    saved = await asyncio.to_thread(
        analysis_store.save_diff,
        repo=design_run.get("repo") or code_run.get("repo") or repo,
        design_run_id=design_run["id"],
        code_run_id=code_run["id"],
        model=scd.MODEL_NAME,
        stats={
            "design_feature_count": len(design_run.get("features") or []),
            "code_feature_count": len(code_run.get("features") or []),
            "pair_count": len(pairs),
            "design_only_count": len(paired["design_only"]),
            "code_only_count": len(paired["code_only"]),
        },
        items=items,
    )
    return _spec_diff_response(saved)


@router.get("/api/spec-diff/latest")
def api_spec_diff_latest() -> dict[str, Any]:
    """成功済みの最新の差分解析(相違点込み)。無ければ diff_id=null で返す。"""
    from pipeline import analysis_store

    diff = analysis_store.get_latest_diff()
    if diff is None:
        return {"diff_id": None, "diff_count": 0, "items": []}
    return _spec_diff_response(diff)


@router.get("/api/spec-diff/runs")
def api_spec_diff_runs(limit: int = Query(default=30, le=200)) -> list[dict[str, Any]]:
    """差分解析の一覧(新しい順)。"""
    from pipeline import analysis_store

    return analysis_store.list_diffs(limit=limit)
