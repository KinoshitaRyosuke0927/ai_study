"""設計書情報取得・機能分析(設計書ファイルの取得、AI による2段階の機能分析)。"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from config.runtime import load_runtime_config
from config.settings import get_settings
from routers.common import analysis_run_response, run_feature_details

router = APIRouter()


@router.post("/api/design/fetch")
def api_design_fetch() -> dict[str, Any]:
    """設定「設計書パス」配下の全ファイル内容をファイルごとに返す。"""
    from viewers import design as design_view

    settings = get_settings()
    rc = load_runtime_config()
    try:
        return design_view.fetch_design_files(settings, rc.github_repo, rc.github_design_path)
    except design_view.DesignViewError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/api/design/analyze")
async def api_design_analyze(force: bool = Query(default=False)) -> dict[str, Any]:
    """設計書パス配下のファイルを AI で 2 段階に分析し、機能ごとの詳細仕様を返す。

    1. 設計書全体を渡してアプリの機能を洗い出し、機能ごとに該当セクションを特定する(1 回)。
    2. 洗い出した機能ごとに、該当セクション + 共通ドキュメントだけを渡して詳細仕様を
       読み取る(並列)。抜粋が薄すぎる機能は設計書全文へフォールバックする。

    結果は analysis_runs / analysis_features / analysis_feature_refs に保存する。
    同一入力(content_hash)の成功済み結果があれば再利用する(force=true で無視して再分析)。
    """
    from viewers import design as design_view
    from pipeline import design_features as df
    from pipeline import analysis_store

    settings = get_settings()
    rc = load_runtime_config()

    # --- 設計書ファイルを取得する(/api/design/fetch と同じ経路)---
    try:
        fetched = await asyncio.to_thread(
            design_view.fetch_design_files,
            settings,
            rc.github_repo,
            rc.github_design_path,
        )
    except design_view.DesignViewError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # --- テキストの設計書のみを分析対象にする(バイナリ・空ファイルは除外)---
    target_files = [
        {"name": f["name"], "content": f["content"]}
        for f in fetched["files"]
        if not f["binary"] and (f["content"] or "").strip()
    ]
    if not target_files:
        raise HTTPException(status_code=422, detail="分析できるテキストの設計書がありません")

    # --- 同一入力の成功済み結果があれば再利用する ---
    content_hash = analysis_store.compute_content_hash(target_files)
    if not force:
        cached = await asyncio.to_thread(
            analysis_store.find_cached_run, "design", content_hash
        )
        if cached:
            return analysis_run_response(cached, cached=True)

    # --- 1 回目: 機能の洗い出し + 該当セクション特定 + 2 回目用コンテキストの組み立て ---
    try:
        plan = await asyncio.to_thread(df.plan_analysis, settings, target_files)
    except df.DesignFeatureAnalysisError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # --- 2 回目: 機能ごとに詳細仕様を並列で読み取る(010_ai_reviewer の並列処理を参考)---
    details = await run_feature_details(
        settings, plan["features"], df.analyze_feature_detail, "機能詳細の分析に失敗"
    )

    # --- 保存して、保存後の run を返す ---
    saved = await asyncio.to_thread(
        analysis_store.save_analysis,
        kind="design",
        repo=fetched["repo"],
        branch=fetched["branch"],
        tree_sha=fetched.get("tree_sha"),
        content_hash=content_hash,
        model=df.MODEL_NAME,
        params={
            "max_context_chars": df.MAX_CONTEXT_CHARS,
            "fallback_min_chars": df.FALLBACK_MIN_CHARS,
            "common_file_max_chars": df.COMMON_FILE_MAX_CHARS,
        },
        stats={
            "path": fetched["path"],
            "analyzed_file_count": len(target_files),
            "section_count": plan["sections_total"],
            "common_section_count": len(plan["common_section_ids"]),
        },
        features=details,
    )
    return analysis_run_response(saved, cached=False)
