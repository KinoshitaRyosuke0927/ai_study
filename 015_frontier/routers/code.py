"""コード情報取得・機能分析(リポジトリ全体のソース取得、AI による2段階の機能分析)。"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from config.runtime import load_runtime_config
from config.settings import get_settings
from routers.common import analysis_run_response, run_feature_details

router = APIRouter()


@router.post("/api/code/fetch")
async def api_code_fetch() -> dict[str, Any]:
    """設定「GitHub リポジトリ名称」のリポジトリ全体のソースコードを返す。"""
    from viewers import code as code_view

    settings = get_settings()
    rc = load_runtime_config()
    try:
        return await asyncio.to_thread(
            code_view.fetch_code_files, settings, rc.github_repo
        )
    except code_view.CodeViewError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/api/code/analyze")
async def api_code_analyze(force: bool = Query(default=False)) -> dict[str, Any]:
    """リポジトリ全体のソースコードを AI で 2 段階に分析し、機能ごとの詳細分析を返す。

    1. コードアウトライン(パス + シンボル)を渡してアプリの機能を洗い出し、
       機能ごとに該当ファイル・関数/クラスを特定する(1 回)。
    2. 洗い出した機能ごとに、該当する関数/クラスの全文 + コアファイルだけを渡して
       詳細分析を行う(並列)。抜粋が薄すぎる機能は entrypoint 群へフォールバックする。

    結果は analysis_runs / analysis_features / analysis_feature_refs に保存する。
    同一入力(content_hash)の成功済み結果があれば再利用する(force=true で無視して再分析)。
    """
    from viewers import code as code_view
    from pipeline import code_features as cf
    from pipeline import analysis_store

    settings = get_settings()
    rc = load_runtime_config()

    # --- ソースコードを取得する(/api/code/fetch と同じ経路)---
    try:
        fetched = await asyncio.to_thread(
            code_view.fetch_code_files, settings, rc.github_repo
        )
    except code_view.CodeViewError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # --- テキストのソースのみを分析対象にする(バイナリ・空ファイルは除外)---
    target_files = [
        {"name": f["name"], "content": f["content"]}
        for f in fetched["files"]
        if not f["binary"] and (f["content"] or "").strip()
    ]
    if not target_files:
        raise HTTPException(status_code=422, detail="分析できるソースコードがありません")

    # --- 同一入力の成功済み結果があれば再利用する ---
    content_hash = analysis_store.compute_content_hash(target_files)
    if not force:
        cached = await asyncio.to_thread(
            analysis_store.find_cached_run, "code", content_hash
        )
        if cached:
            return analysis_run_response(cached, cached=True)

    # --- 1 回目: 機能の洗い出し + 該当ファイル/シンボル特定 + 2 回目用コンテキストの組み立て ---
    try:
        plan = await asyncio.to_thread(cf.plan_analysis, settings, target_files)
    except cf.CodeAnalysisError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # --- 2 回目: 機能ごとに詳細分析を並列で行う(010_ai_reviewer の並列処理を参考)---
    details = await run_feature_details(
        settings, plan["features"], cf.analyze_feature_detail, "コード機能詳細の分析に失敗"
    )

    # --- 保存して、保存後の run を返す ---
    saved = await asyncio.to_thread(
        analysis_store.save_analysis,
        kind="code",
        repo=fetched["repo"],
        branch=fetched["branch"],
        tree_sha=fetched.get("tree_sha"),
        content_hash=content_hash,
        model=cf.MODEL_NAME,
        params={
            "max_context_chars": cf.MAX_CONTEXT_CHARS,
            "max_symbol_source_chars": cf.MAX_SYMBOL_SOURCE_CHARS,
            "max_file_head_chars": cf.MAX_FILE_HEAD_CHARS,
            "fallback_min_chars": cf.FALLBACK_MIN_CHARS,
        },
        stats={
            "path": fetched["path"],
            "analyzed_file_count": len(target_files),
            "file_count": fetched["file_count"],
            "symbol_count": plan["symbol_count"],
            "core_file_count": len(plan["core_paths"]),
        },
        features=details,
    )
    return analysis_run_response(saved, cached=False)
