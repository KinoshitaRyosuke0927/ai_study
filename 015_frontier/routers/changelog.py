"""変更履歴取得(コミット履歴をファイル単位・ユーザ単位で蓄積 → 分析 / RAG)。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from config.runtime import load_runtime_config
from config.settings import get_settings
from routers.common import DESIGN_DETAIL_MAX_PARALLEL

logger = logging.getLogger("frontier.routers.changelog")

router = APIRouter()


def _changelog_analysis_response(analysis: dict[str, Any], *, cached: bool) -> dict[str, Any]:
    stats = analysis.get("stats") or {}
    return {
        "analysis_id": analysis["id"],
        "cached": cached,
        "saved_at": analysis.get("created_at"),
        "repo": analysis.get("repo"),
        "themes": analysis.get("themes") or [],
        "account_count": len(analysis.get("accounts") or []),
        "accounts": analysis.get("accounts") or [],
        **stats,
    }


@router.post("/api/changelog/fetch")
async def api_changelog_fetch(
    force: bool = Query(default=False), full: bool = Query(default=False)
) -> dict[str, Any]:
    """既定ブランチのコミット履歴をファイル単位・ユーザ単位で蓄積し、
    ユーザごと / ファイルごとの集計を返す。会話ログと同様に RAG 用チャンクも蓄積する。

    - since_date(設定「データ取得開始日時」)で範囲を区切る(full=true で全期間)。
    - 2 回目以降は前回の HEAD SHA からの増分のみ(force=true で無視して取り直す)。
    - patch 本体は保存せず、ハンク見出し + 打ち切り抜粋のみ保持。
    """
    from viewers import changelog as cl_view
    from pipeline import changelog_ingest as ci, changelog_store as cstore

    settings = get_settings()
    rc = load_runtime_config()
    repo_cfg = (rc.github_repo or "").strip()
    since_date = None if full else rc.since_date

    repo_resolved = cl_view._resolve_repo(settings, repo_cfg)
    base_sha = None if (full or force) else cstore.get_latest_head_sha(repo_resolved)

    try:
        fetched = await asyncio.to_thread(
            cl_view.fetch_change_history, settings, repo_cfg, since_date, base_sha
        )
    except cl_view.ChangelogViewError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    repo = fetched["repo"]
    commits = fetched["commits"]
    content_hash = ci.compute_content_hash(
        repo, fetched["branch"], fetched["head_sha"], fetched.get("since_date")
    )

    chunk_stat = {"chunk_count": 0, "embedded_chunks": 0}
    ing = {"file_change_count": 0}
    if commits:
        ing = await asyncio.to_thread(
            cstore.ingest_commits,
            repo=repo, branch=fetched["branch"], head_sha=fetched["head_sha"],
            base_sha=base_sha, since_date=since_date, commits=commits, content_hash=content_hash,
        )

        def _chunks_and_embed() -> dict[str, Any]:
            all_commits = cstore.load_commits(repo)
            chunks = (
                ci.build_commit_chunks(commits, repo)
                + ci.build_file_rollup_chunks(all_commits, repo)
            )
            return cstore.store_change_chunks_and_embed(chunks)

        try:
            chunk_stat = await asyncio.to_thread(_chunks_and_embed)
        except Exception:
            logger.exception("変更履歴チャンク/埋め込みに失敗(取得は継続)")

    summary = await asyncio.to_thread(cstore.get_summary, repo) or {}
    return {
        "repo": repo,
        "branch": fetched["branch"],
        "head_sha": fetched["head_sha"],
        "since_date": fetched.get("since_date"),
        "new_commits": fetched["commit_count"],
        "detail_commits": fetched["detail_count"],
        "truncated": fetched["truncated"],
        "ingested_file_changes": ing["file_change_count"],
        "chunk_count": chunk_stat["chunk_count"],
        "embedded_chunks": chunk_stat["embedded_chunks"],
        **summary,
    }


@router.get("/api/changelog/summary")
def api_changelog_summary() -> dict[str, Any]:
    """保存済みのユーザごと / ファイルごとの集計(タブを開いたときの復元用)。"""
    from viewers import changelog as cl_view
    from pipeline import changelog_store as cstore

    settings = get_settings()
    rc = load_runtime_config()
    repo = cl_view._resolve_repo(settings, (rc.github_repo or "").strip())
    return cstore.get_summary(repo) or {"repo": repo, "commit_count": 0, "users": [], "files": []}


@router.post("/api/changelog/analyze")
async def api_changelog_analyze(force: bool = Query(default=False)) -> dict[str, Any]:
    """蓄積済みのコミット履歴をもとに、アカウント(コミット作者)ごとに
    「どの領域を変更しているか / 変更の傾向 / 粒度 / co-change」を AI で分析する。
    先に「取得」で履歴を蓄積しておく必要がある。
    """
    from viewers import changelog as cl_view
    from pipeline import changelog_analysis as ca, changelog_ingest as ci, changelog_store as cstore

    settings = get_settings()
    rc = load_runtime_config()
    repo = cl_view._resolve_repo(settings, (rc.github_repo or "").strip())

    commits = await asyncio.to_thread(cstore.load_commits, repo)
    if not commits:
        raise HTTPException(status_code=422, detail="先に「取得」で変更履歴を蓄積してください")

    head = commits[-1]["sha"]  # load_commits は committed_at 昇順 → 末尾が最新
    content_hash = ci.compute_content_hash(repo, "changelog-analyze", head, str(len(commits)))
    if not force:
        cached = await asyncio.to_thread(cstore.find_cached_author_analysis, content_hash)
        if cached:
            return _changelog_analysis_response(cached, cached=True)

    contexts = ci.build_author_contexts(commits)
    themes = await asyncio.to_thread(ca.list_repo_themes, settings, commits)

    sem = asyncio.Semaphore(DESIGN_DETAIL_MAX_PARALLEL)

    async def _one(acc: dict[str, Any]) -> dict[str, Any]:
        async with sem:
            return await asyncio.to_thread(ca.analyze_author, settings, acc, themes)

    results = await asyncio.gather(*(_one(c) for c in contexts), return_exceptions=True)

    accounts_out: list[dict[str, Any]] = []
    for acc, res in zip(contexts, results):
        base = {
            "author": acc["author"], "author_name": acc.get("author_name", ""),
            "stats": acc["stats"], "refs": acc["refs"],
        }
        if isinstance(res, Exception):
            logger.error("変更履歴 アカウント分析に失敗 user=%s: %s", acc["author"], res)
            accounts_out.append({**base, "overview": "", "sections": [], "error": "このアカウントの分析に失敗しました"})
        else:
            accounts_out.append({**base, "overview": res["overview"], "sections": res["sections"]})

    run_id = await asyncio.to_thread(cstore.latest_ingest_run_id, repo)
    saved = await asyncio.to_thread(
        cstore.save_author_analysis,
        ingest_run_id=run_id or 0,
        repo=repo,
        head_sha=head,
        content_hash=content_hash,
        model=ca.MODEL_NAME,
        themes=themes,
        stats={"commit_count": len(commits), "account_count": len(contexts)},
        accounts=accounts_out,
    )
    return _changelog_analysis_response(saved, cached=False)


@router.get("/api/changelog/analysis/latest")
def api_changelog_analysis_latest() -> dict[str, Any]:
    from pipeline import changelog_store as cstore

    a = cstore.get_latest_author_analysis()
    if a is None:
        return {"analysis_id": None, "account_count": 0, "accounts": []}
    return _changelog_analysis_response(a, cached=True)


@router.get("/api/changelog/analysis/runs")
def api_changelog_analysis_runs(limit: int = Query(default=30, le=200)) -> list[dict[str, Any]]:
    from pipeline import changelog_store as cstore

    return cstore.list_author_analyses(limit=limit)


@router.get("/api/changelog/analysis/runs/{analysis_id}")
def api_changelog_analysis_run(analysis_id: int) -> dict[str, Any]:
    from pipeline import changelog_store as cstore

    a = cstore.get_author_analysis(analysis_id)
    if not a:
        raise HTTPException(status_code=404, detail="分析結果が見つかりません")
    return _changelog_analysis_response(a, cached=True)
