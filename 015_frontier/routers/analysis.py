"""保存済みの分析結果(設計書分析 / コード分析)の取得。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from routers.common import analysis_run_response

router = APIRouter()


@router.get("/api/analysis/runs")
def api_analysis_runs(
    kind: str | None = None, limit: int = Query(default=30, le=200)
) -> list[dict[str, Any]]:
    """保存済みの分析実行の一覧(新しい順)。kind=design|code で絞り込み。"""
    from pipeline import analysis_store

    return analysis_store.list_runs(kind=kind, limit=limit)


@router.get("/api/analysis/runs/{run_id}")
def api_analysis_run(run_id: int) -> dict[str, Any]:
    """保存済みの分析実行 1 件(機能・トレーサビリティ込み)を分析画面のレスポンス形で返す。"""
    from pipeline import analysis_store

    run = analysis_store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="分析結果が見つかりません")
    return analysis_run_response(run, cached=True)
