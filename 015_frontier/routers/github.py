"""GitHub 情報取得・DB登録(ブランチ活動 + PR + コメント/レビュー)。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from config.runtime import load_runtime_config
from config.settings import get_settings

logger = logging.getLogger("frontier.routers.github")

router = APIRouter()


@router.post("/api/github/fetch")
def api_github_fetch() -> dict[str, Any]:
    """設定リポジトリのブランチ活動と PR(作成者・マージ実行者・コメント)を返す。"""
    from viewers import github as github_view

    settings = get_settings()
    rc = load_runtime_config()
    try:
        return github_view.fetch_repo_activity(settings, rc.github_repo)
    except github_view.GitHubViewError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/api/github/ingest")
async def api_github_ingest(force: bool = Query(default=False)) -> dict[str, Any]:
    """「GitHub 情報取得」の結果(ブランチ活動 + PR + コメント/レビュー)を DB へ登録する。

    「誰が・いつ・どのような操作/コメントをしたか」を gh_activity に記録し、
    PR / ブランチ単位でチャンク化して embeddings へ source='github_activity' で埋め込む
    (既存 /api/search の RAG がそのまま Github 活動も検索対象にする)。分析は行わない。
    """
    from viewers import github as github_view
    from pipeline import github_activity_ingest as gai, github_activity_store as gastore

    settings = get_settings()
    rc = load_runtime_config()

    try:
        fetched = await asyncio.to_thread(
            github_view.fetch_repo_activity, settings, rc.github_repo
        )
    except github_view.GitHubViewError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    flat = gai.flatten_activity(fetched)
    repo = flat["repo"]
    content_hash = gai.compute_content_hash(flat)

    ingested = False
    if force or gastore.latest_content_hash(repo) != content_hash:
        await asyncio.to_thread(
            gastore.ingest_activity, repo=repo, flat=flat, content_hash=content_hash
        )

        def _chunks_and_embed() -> dict[str, Any]:
            chunks = (
                gai.build_pr_chunks(flat["pull_requests"], flat["activities"], repo)
                + gai.build_branch_chunks(flat["branches"], fetched, repo)
            )
            return gastore.store_activity_chunks_and_embed(chunks)

        try:
            emb = await asyncio.to_thread(_chunks_and_embed)
        except Exception:
            logger.exception("GitHub 活動チャンク/埋め込みに失敗(登録は継続)")
            emb = {"chunk_count": 0, "embedded_chunks": 0}
        ingested = True
    else:
        emb = {"chunk_count": 0, "embedded_chunks": 0}

    summary = await asyncio.to_thread(gastore.get_activity_summary, repo) or {}
    return {
        "repo": repo,
        "ingested": ingested,
        "cached": not ingested,
        "chunk_count": emb["chunk_count"],
        "embedded_chunks": emb["embedded_chunks"],
        **summary,
    }


@router.get("/api/github/activity/summary")
def api_github_activity_summary() -> dict[str, Any]:
    """登録済みの GitHub 活動サマリ(タブを開いたときの復元用)。"""
    from viewers import github as github_view
    from pipeline import github_activity_store as gastore

    settings = get_settings()
    rc = load_runtime_config()
    repo = github_view._resolve_repo(settings, (rc.github_repo or "").strip())
    return gastore.get_activity_summary(repo) or {"repo": repo, "activity_total": 0, "activities": [], "by_actor": []}
