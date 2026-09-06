"""FastAPI アプリ本体。

- 起動時に schema.sql を適用する。
- ダッシュボード(static/index.html)と JSON API を提供する。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from infra.db import apply_schema, ping
from viewers.options import (
    check_github_path,
    check_github_repo,
    check_growi_path,
    list_mattermost_channels,
    list_trello_boards,
)
from config.runtime import (
    RuntimeConfig,
    load_runtime_config,
    save_runtime_config,
)
from config.settings import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("frontier.app")

STATIC_DIR = "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """起動時: スキーマ適用。"""
    settings = get_settings()
    apply_schema(settings)
    logger.info("起動: run_mode=%s ai_enabled=%s", settings.app_run_mode, settings.ai_enabled)
    yield


app = FastAPI(title="Frontier", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ----------------------------------------------------------------------
# エンドポイント
# ----------------------------------------------------------------------
@app.get("/")
def index() -> FileResponse:
    """ダッシュボード HTML を配信する。"""
    return FileResponse(f"{STATIC_DIR}/index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    """DB 接続と実行モードを返す。"""
    settings = get_settings()
    return {
        "status": "ok" if ping(settings) else "db_error",
        "run_mode": settings.app_run_mode,
        "ai_enabled": settings.ai_enabled,
    }


# ----------------------------------------------------------------------
# 設定(データ取得に関する実行時設定 / acquisition_settings.json)
# ----------------------------------------------------------------------
class SettingsBody(BaseModel):
    """/api/settings (POST) のリクエストボディ。"""

    since_date: str | None = None  # "YYYY-MM-DD" または null
    mattermost_channel_ids: list[str] = []
    trello_board_ids: list[str] = []
    github_repo: str = ""          # "owner/repo" またはリポジトリ名。空可
    github_design_path: str = ""   # リポジトリからの相対パス(設計書フォルダ)。空可
    growi_page_path: str = ""      # "/projects/foo"。空可


@app.get("/api/settings")
def api_get_settings() -> dict[str, Any]:
    """現在の実行時設定 + 選択肢(Mattermost チャンネル / Trello ボード)を返す。

    選択肢は設定画面の表示時に `.env` のトークンで都度取得する。
    """
    settings = get_settings()
    rc = load_runtime_config()
    channels, mm_err = list_mattermost_channels(settings)
    boards, trello_err = list_trello_boards(settings)
    return {
        "config": rc.to_api_dict(),
        "options": {
            "mattermost": {"channels": channels, "error": mm_err},
            "trello": {"boards": boards, "error": trello_err},
        },
    }


@app.post("/api/settings")
def api_save_settings(body: SettingsBody) -> dict[str, Any]:
    """実行時設定を acquisition_settings.json へ保存する。

    GitHub のリポジトリ名称 / 設計書パス、参照する Wiki のページは、保存時に
    `.env` の Git アカウント情報・GROWI トークンで実際にアクセスできるか確認する。
    確認に失敗した場合はエラーを返し、保存しない(422)。
    """
    from datetime import date as _date

    settings = get_settings()

    since_date = None
    if body.since_date:
        try:
            since_date = _date.fromisoformat(body.since_date)
        except ValueError:
            raise HTTPException(status_code=422, detail="since_date は YYYY-MM-DD 形式")

    # --- アクセス確認(GitHub リポジトリ / 設計書パス / GROWI パス)---
    field_errors: dict[str, str] = {}
    github_repo = body.github_repo.strip()
    github_design_path = body.github_design_path.strip().strip("/")
    growi_page_path = body.growi_page_path.strip()

    if github_repo:
        resolved, err = check_github_repo(settings, github_repo)
        if err:
            field_errors["github_repo"] = err
        else:
            github_repo = resolved  # 解決した owner/repo を保存する

    # 設計書パスはリポジトリが有効なときだけ、その配下に存在するか確認する
    if github_design_path and "github_repo" not in field_errors:
        err = check_github_path(settings, github_repo, github_design_path)
        if err:
            field_errors["github_design_path"] = err

    if growi_page_path:
        _count, err = check_growi_path(settings, growi_page_path)
        if err:
            field_errors["growi_page_path"] = err

    if field_errors:
        # 保存は行わず、どの項目でアクセスできなかったかを返す
        raise HTTPException(
            status_code=422,
            detail={"message": "アクセス確認に失敗したため保存しませんでした", "errors": field_errors},
        )

    rc = RuntimeConfig(
        since_date=since_date,
        mattermost_channel_ids=[c for c in body.mattermost_channel_ids if c],
        trello_board_ids=[b for b in body.trello_board_ids if b],
        github_repo=github_repo,
        github_design_path=github_design_path,
        growi_page_path=growi_page_path,
    )
    save_runtime_config(rc)
    return {"status": "saved", "config": rc.to_api_dict()}


# ----------------------------------------------------------------------
# Mattermost 情報取得(画面表示用。DB へは保存しない)
# ----------------------------------------------------------------------
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


@app.post("/api/mattermost/fetch")
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


@app.post("/api/mattermost/analyze")
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


@app.get("/api/mattermost/analysis/latest")
def api_mm_analysis_latest() -> dict[str, Any]:
    """保存済みの最新のアカウント横断分析。無ければ analysis_id=null。"""
    from pipeline import mm_store

    a = mm_store.get_latest_account_analysis()
    if a is None:
        return {"analysis_id": None, "account_count": 0, "accounts": []}
    return _mm_analysis_response(a, cached=True)


@app.get("/api/mattermost/analysis/runs")
def api_mm_analysis_runs(limit: int = Query(default=30, le=200)) -> list[dict[str, Any]]:
    """アカウント横断分析の一覧(新しい順)。"""
    from pipeline import mm_store

    return mm_store.list_account_analyses(limit=limit)


@app.get("/api/mattermost/analysis/runs/{analysis_id}")
def api_mm_analysis_run(analysis_id: int) -> dict[str, Any]:
    """保存済みのアカウント横断分析 1 件を、分析画面のレスポンス形で返す。"""
    from pipeline import mm_store

    a = mm_store.get_account_analysis(analysis_id)
    if not a:
        raise HTTPException(status_code=404, detail="分析結果が見つかりません")
    return _mm_analysis_response(a, cached=True)


# ----------------------------------------------------------------------
# Trello 情報取得(画面表示用。DB へは保存しない)
# ----------------------------------------------------------------------
class TrelloFetchBody(BaseModel):
    """/api/trello/fetch のリクエストボディ。"""

    board_id: str


@app.get("/api/trello/boards")
def api_trello_boards() -> dict[str, Any]:
    """取得対象ボード設定のプルダウン用: 設定済みボードを名前付きで返す。"""
    from viewers import trello as trello_view

    settings = get_settings()
    rc = load_runtime_config()
    boards, err = trello_view.list_configured_boards(settings, rc.trello_board_ids)
    return {"boards": boards, "error": err}


@app.post("/api/trello/fetch")
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


@app.post("/api/trello/analyze")
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


@app.get("/api/trello/analysis/latest")
def api_trello_analysis_latest() -> dict[str, Any]:
    """保存済みの最新の Trello アカウント横断分析。無ければ analysis_id=null。"""
    from pipeline import trello_store as tstore

    a = tstore.get_latest_account_analysis()
    if a is None:
        return {"analysis_id": None, "account_count": 0, "accounts": []}
    return _trello_analysis_response(a, cached=True)


@app.get("/api/trello/analysis/runs")
def api_trello_analysis_runs(limit: int = Query(default=30, le=200)) -> list[dict[str, Any]]:
    """Trello アカウント横断分析の一覧(新しい順)。"""
    from pipeline import trello_store as tstore

    return tstore.list_account_analyses(limit=limit)


@app.get("/api/trello/analysis/runs/{analysis_id}")
def api_trello_analysis_run(analysis_id: int) -> dict[str, Any]:
    """保存済みの Trello アカウント横断分析 1 件を、分析画面のレスポンス形で返す。"""
    from pipeline import trello_store as tstore

    a = tstore.get_account_analysis(analysis_id)
    if not a:
        raise HTTPException(status_code=404, detail="分析結果が見つかりません")
    return _trello_analysis_response(a, cached=True)


# ----------------------------------------------------------------------
# 変更履歴取得(コミット履歴をファイル単位・ユーザ単位で蓄積 → 分析 / RAG)
# ----------------------------------------------------------------------
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


@app.post("/api/changelog/fetch")
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


@app.get("/api/changelog/summary")
def api_changelog_summary() -> dict[str, Any]:
    """保存済みのユーザごと / ファイルごとの集計(タブを開いたときの復元用)。"""
    from viewers import changelog as cl_view
    from pipeline import changelog_store as cstore

    settings = get_settings()
    rc = load_runtime_config()
    repo = cl_view._resolve_repo(settings, (rc.github_repo or "").strip())
    return cstore.get_summary(repo) or {"repo": repo, "commit_count": 0, "users": [], "files": []}


@app.post("/api/changelog/analyze")
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


@app.get("/api/changelog/analysis/latest")
def api_changelog_analysis_latest() -> dict[str, Any]:
    from pipeline import changelog_store as cstore

    a = cstore.get_latest_author_analysis()
    if a is None:
        return {"analysis_id": None, "account_count": 0, "accounts": []}
    return _changelog_analysis_response(a, cached=True)


@app.get("/api/changelog/analysis/runs")
def api_changelog_analysis_runs(limit: int = Query(default=30, le=200)) -> list[dict[str, Any]]:
    from pipeline import changelog_store as cstore

    return cstore.list_author_analyses(limit=limit)


@app.get("/api/changelog/analysis/runs/{analysis_id}")
def api_changelog_analysis_run(analysis_id: int) -> dict[str, Any]:
    from pipeline import changelog_store as cstore

    a = cstore.get_author_analysis(analysis_id)
    if not a:
        raise HTTPException(status_code=404, detail="分析結果が見つかりません")
    return _changelog_analysis_response(a, cached=True)


# ----------------------------------------------------------------------
# wiki(GROWI)情報取得(画面表示用。DB へは保存しない)
# ----------------------------------------------------------------------
class GrowiFetchBody(BaseModel):
    """/api/growi/fetch のリクエストボディ。"""

    page_id: str


@app.get("/api/growi/pages")
def api_growi_pages() -> dict[str, Any]:
    """設定の「参照する Wiki のページ」配下のページ一覧(プルダウン用)。"""
    from viewers import growi as growi_view

    settings = get_settings()
    rc = load_runtime_config()
    try:
        return growi_view.list_pages(settings, rc.growi_page_path)
    except growi_view.GrowiViewError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/growi/fetch")
def api_growi_fetch(body: GrowiFetchBody) -> dict[str, Any]:
    """選択ページの記事内容・更新履歴・コメントを返す。"""
    from viewers import growi as growi_view

    settings = get_settings()
    try:
        return growi_view.fetch_page(settings, body.page_id.strip())
    except growi_view.GrowiViewError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ----------------------------------------------------------------------
# GitHub 情報取得(画面表示用。DB へは保存しない)
# ----------------------------------------------------------------------
@app.post("/api/github/fetch")
def api_github_fetch() -> dict[str, Any]:
    """設定リポジトリのブランチ活動と PR(作成者・マージ実行者・コメント)を返す。"""
    from viewers import github as github_view

    settings = get_settings()
    rc = load_runtime_config()
    try:
        return github_view.fetch_repo_activity(settings, rc.github_repo)
    except github_view.GitHubViewError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/github/ingest")
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


@app.get("/api/github/activity/summary")
def api_github_activity_summary() -> dict[str, Any]:
    """登録済みの GitHub 活動サマリ(タブを開いたときの復元用)。"""
    from viewers import github as github_view
    from pipeline import github_activity_store as gastore

    settings = get_settings()
    rc = load_runtime_config()
    repo = github_view._resolve_repo(settings, (rc.github_repo or "").strip())
    return gastore.get_activity_summary(repo) or {"repo": repo, "activity_total": 0, "activities": [], "by_actor": []}


# ----------------------------------------------------------------------
# 設計書情報取得(画面表示用。DB へは保存しない)
# ----------------------------------------------------------------------
@app.post("/api/design/fetch")
def api_design_fetch() -> dict[str, Any]:
    """設定「設計書パス」配下の全ファイル内容をファイルごとに返す。"""
    from viewers import design as design_view

    settings = get_settings()
    rc = load_runtime_config()
    try:
        return design_view.fetch_design_files(settings, rc.github_repo, rc.github_design_path)
    except design_view.DesignViewError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# 2 回目(機能ごとの詳細仕様)の AI 呼び出しを並列実行する際の最大同時数
# (Azure OpenAI のレート制限に配慮して上限を設ける)
DESIGN_DETAIL_MAX_PARALLEL = 5


def _analysis_run_response(run: dict[str, Any], *, cached: bool) -> dict[str, Any]:
    """保存済み run(analysis_store の形)を、分析画面が期待するレスポンス形へ変換する。

    stats に入れた集計値(ファイル数・セクション数など)をトップレベルへ展開するので、
    「その場で分析」「キャッシュ再利用」「保存済みを取得」で同じ形になる。
    """
    stats = run.get("stats") or {}
    return {
        "run_id": run["id"],
        "kind": run["kind"],
        "cached": cached,
        "saved_at": run.get("created_at"),
        "repo": run["repo"],
        "branch": run["branch"],
        "tree_sha": run.get("tree_sha"),
        "content_hash": run.get("content_hash"),
        "feature_count": len(run.get("features") or []),
        "features": run.get("features") or [],
        **stats,
    }


async def _run_feature_details(
    settings: Any, plan_features: list[dict[str, Any]], analyze_fn: Any, log_label: str
) -> list[dict[str, Any]]:
    """2 回目(機能ごとの詳細分析)を並列実行し、保存用の機能一覧へ畳み込む。

    失敗した機能もエラー付きで残し、絞り込み状況・トレーサビリティ(refs)を meta として持たせる。
    """
    sem = asyncio.Semaphore(DESIGN_DETAIL_MAX_PARALLEL)

    async def _detail(feature: dict[str, Any]) -> dict[str, Any]:
        async with sem:
            return await asyncio.to_thread(analyze_fn, settings, feature)

    results = await asyncio.gather(
        *(_detail(f) for f in plan_features), return_exceptions=True
    )

    details: list[dict[str, Any]] = []
    for feature, res in zip(plan_features, results):
        meta = {
            "context_mode": feature["context_mode"],
            "context_char_len": feature["context_char_len"],
            "refs": feature.get("refs", []),
        }
        for key in ("selected_section_ids", "selected_symbols", "selected_paths"):
            if key in feature:
                meta[key] = feature[key]
        if isinstance(res, Exception):
            logger.error("%s feature=%s: %s", log_label, feature.get("name"), res)
            details.append({
                "name": feature.get("name", "(名称なし)"),
                "overview": feature.get("summary", ""),
                "sections": [],
                "error": "この機能の詳細分析に失敗しました",
                **meta,
            })
        else:
            details.append({**res, **meta})
    return details


@app.post("/api/design/analyze")
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
            return _analysis_run_response(cached, cached=True)

    # --- 1 回目: 機能の洗い出し + 該当セクション特定 + 2 回目用コンテキストの組み立て ---
    try:
        plan = await asyncio.to_thread(df.plan_analysis, settings, target_files)
    except df.DesignFeatureAnalysisError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # --- 2 回目: 機能ごとに詳細仕様を並列で読み取る(010_ai_reviewer の並列処理を参考)---
    details = await _run_feature_details(
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
    return _analysis_run_response(saved, cached=False)


# ----------------------------------------------------------------------
# コード情報取得(画面表示用。DB へは保存しない)
# ----------------------------------------------------------------------
@app.post("/api/code/fetch")
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


@app.post("/api/code/analyze")
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
            return _analysis_run_response(cached, cached=True)

    # --- 1 回目: 機能の洗い出し + 該当ファイル/シンボル特定 + 2 回目用コンテキストの組み立て ---
    try:
        plan = await asyncio.to_thread(cf.plan_analysis, settings, target_files)
    except cf.CodeAnalysisError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # --- 2 回目: 機能ごとに詳細分析を並列で行う(010_ai_reviewer の並列処理を参考)---
    details = await _run_feature_details(
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
    return _analysis_run_response(saved, cached=False)


# ----------------------------------------------------------------------
# 分析結果(保存済み)の取得
# ----------------------------------------------------------------------
@app.get("/api/analysis/runs")
def api_analysis_runs(
    kind: str | None = None, limit: int = Query(default=30, le=200)
) -> list[dict[str, Any]]:
    """保存済みの分析実行の一覧(新しい順)。kind=design|code で絞り込み。"""
    from pipeline import analysis_store

    return analysis_store.list_runs(kind=kind, limit=limit)


@app.get("/api/analysis/runs/{run_id}")
def api_analysis_run(run_id: int) -> dict[str, Any]:
    """保存済みの分析実行 1 件(機能・トレーサビリティ込み)を分析画面のレスポンス形で返す。"""
    from pipeline import analysis_store

    run = analysis_store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="分析結果が見つかりません")
    return _analysis_run_response(run, cached=True)


# ----------------------------------------------------------------------
# 実装差分解析(設計書分析 と コード分析 の突き合わせ)
# ----------------------------------------------------------------------
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


@app.post("/api/spec-diff/analyze")
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


@app.get("/api/spec-diff/latest")
def api_spec_diff_latest() -> dict[str, Any]:
    """成功済みの最新の差分解析(相違点込み)。無ければ diff_id=null で返す。"""
    from pipeline import analysis_store

    diff = analysis_store.get_latest_diff()
    if diff is None:
        return {"diff_id": None, "diff_count": 0, "items": []}
    return _spec_diff_response(diff)


@app.get("/api/spec-diff/runs")
def api_spec_diff_runs(limit: int = Query(default=30, le=200)) -> list[dict[str, Any]]:
    """差分解析の一覧(新しい順)。"""
    from pipeline import analysis_store

    return analysis_store.list_diffs(limit=limit)


# ----------------------------------------------------------------------
# アクティビティ分析(各ツールのアカウント別分析を settings.ini の
# [USER_ID] でユーザ単位に束ねる)
# ----------------------------------------------------------------------
def _user_activity_response(analysis: dict[str, Any], *, cached: bool) -> dict[str, Any]:
    stats = analysis.get("stats") or {}
    items = analysis.get("items") or []
    return {
        "analysis_id": analysis["id"],
        "cached": cached,
        "saved_at": analysis.get("created_at"),
        "source_ids": analysis.get("source_ids") or {},
        "members": [it for it in items if it.get("is_member")],
        "others": [it for it in items if not it.get("is_member")],
        **stats,
    }


@app.post("/api/user-activity/analyze")
async def api_user_activity_analyze(force: bool = Query(default=False)) -> dict[str, Any]:
    """Mattermost / Trello / コード変更履歴 の各アカウント別分析結果と GitHub 情報を、
    settings.ini の [USER_ID] でユーザ単位に束ねて、プロジェクトにおけるメンバーごとの
    アクティビティを AI で分析する。
    """
    from pipeline import (
        changelog_store,
        github_activity_store,
        mm_store,
        project_config,
        trello_store,
        user_activity_analysis as uaa,
        user_activity_store as uastore,
    )
    from viewers import github as github_view

    settings = get_settings()
    rc = load_runtime_config()

    proj = project_config.load_project_config()
    if not proj["found"] or not proj["members"]:
        raise HTTPException(
            status_code=422, detail="settings.ini の [USER_ID] にメンバーが定義されていません"
        )
    repo = github_view._resolve_repo(settings, (rc.github_repo or "").strip())

    mm = await asyncio.to_thread(mm_store.get_latest_account_analysis)
    tr = await asyncio.to_thread(trello_store.get_latest_account_analysis)
    cl = await asyncio.to_thread(changelog_store.get_latest_author_analysis)
    gh = await asyncio.to_thread(github_activity_store.get_activity_summary, repo)
    gh_hash = await asyncio.to_thread(github_activity_store.latest_content_hash, repo)

    if not (mm or tr or cl or (gh and gh.get("activity_total"))):
        raise HTTPException(
            status_code=422,
            detail="先に「Mattermost/Trello/変更履歴」の分析、または「GitHub情報取得」の DB登録を実行してください",
        )

    content_hash = hashlib.sha256(
        "|".join([
            str(mm["id"]) if mm else "-",
            str(tr["id"]) if tr else "-",
            str(cl["id"]) if cl else "-",
            gh_hash or "-",
            proj["raw_hash"],
        ]).encode("utf-8")
    ).hexdigest()
    if not force:
        cached = await asyncio.to_thread(uastore.find_cached_analysis, content_hash)
        if cached:
            return _user_activity_response(cached, cached=True)

    # --- ソースをアカウント別に索引化 ---
    mm_by = {i["username"]: i for i in (mm or {}).get("accounts", [])}
    tr_by = {i["username"]: i for i in (tr or {}).get("accounts", [])}
    cl_by = {i["username"]: i for i in (cl or {}).get("accounts", [])}
    gh_tally_by = {a["actor"]: a for a in (gh or {}).get("by_actor", [])}
    gh_acts_by: dict[str, list[dict[str, Any]]] = {}
    for a in (gh or {}).get("activities", []):
        gh_acts_by.setdefault(a["actor"], []).append(a)

    used = {"mattermost": set(), "trello": set(), "changelog": set(), "github": set()}

    def _bundle(name: str, personal: str, accounts: dict, is_member: bool) -> dict[str, Any]:
        srcs: dict[str, Any] = {}
        labels: list[str] = []
        m, t, g = accounts.get("mattermost"), accounts.get("trello"), accounts.get("github")
        if m and m in mm_by:
            srcs["mattermost"] = mm_by[m]; used["mattermost"].add(m); labels.append(f"Mattermost:{m}")
        if t and t in tr_by:
            srcs["trello"] = tr_by[t]; used["trello"].add(t); labels.append(f"Trello:{t}")
        if g and g in cl_by:
            srcs["changelog"] = cl_by[g]; used["changelog"].add(g); labels.append(f"変更履歴:{g}")
        if g and (g in gh_tally_by or g in gh_acts_by):
            srcs["github"] = {"actor": g, "tally": gh_tally_by.get(g, {}), "recent": gh_acts_by.get(g, [])}
            used["github"].add(g); labels.append(f"GitHub:{g}")
        return {
            "name": name, "personal": personal, "accounts": accounts, "is_member": is_member,
            "sources": srcs, "used_labels": labels,
        }

    member_bundles = [
        _bundle(m["name"], m["personal"], m["accounts"], True) for m in proj["members"]
    ]

    # --- [USER_ID] に無いアカウント → その他のメンバー(アカウント文字列でまとめる)---
    others: dict[str, dict[str, Any]] = {}

    def _other(acct: str) -> dict[str, Any]:
        return others.setdefault(acct, {
            "name": acct, "personal": "(settings.ini の [USER_ID] に未登録)", "is_member": False,
            "accounts": {}, "sources": {}, "used_labels": [],
        })

    for u, it in mm_by.items():
        if u not in used["mattermost"]:
            e = _other(u); e["accounts"]["mattermost"] = u; e["sources"]["mattermost"] = it
            e["used_labels"].append(f"Mattermost:{u}")
    for u, it in tr_by.items():
        if u not in used["trello"]:
            e = _other(u); e["accounts"]["trello"] = u; e["sources"]["trello"] = it
            e["used_labels"].append(f"Trello:{u}")
    for u, it in cl_by.items():
        if u not in used["changelog"]:
            e = _other(u); e["accounts"]["github"] = u; e["sources"]["changelog"] = it
            e["used_labels"].append(f"変更履歴:{u}")
    for u in set(list(gh_tally_by) + list(gh_acts_by)):
        if u not in used["github"]:
            e = _other(u); e["accounts"].setdefault("github", u)
            e["sources"]["github"] = {"actor": u, "tally": gh_tally_by.get(u, {}), "recent": gh_acts_by.get(u, [])}
            e["used_labels"].append(f"GitHub:{u}")
    other_bundles = list(others.values())

    # --- メンバーごとに並列分析(材料が無い人は AI を呼ばない)---
    all_bundles = member_bundles + other_bundles
    sem = asyncio.Semaphore(DESIGN_DETAIL_MAX_PARALLEL)

    async def _one(b: dict[str, Any]) -> dict[str, Any]:
        if not b["sources"]:
            return {"overview": "対象データにこのメンバーのアクティビティは見つかりませんでした。", "sections": []}
        async with sem:
            return await asyncio.to_thread(uaa.analyze_user, settings, b, proj["tool_context"])

    results = await asyncio.gather(*(_one(b) for b in all_bundles), return_exceptions=True)

    items: list[dict[str, Any]] = []
    for b, res in zip(all_bundles, results):
        base = {
            "is_member": b["is_member"],
            "display_name": b["name"],
            "personal": b["personal"],
            "accounts": b["accounts"],
            "sources": b["used_labels"],
        }
        if isinstance(res, Exception):
            logger.error("アクティビティ分析に失敗 name=%s: %s", b["name"], res)
            items.append({**base, "overview": "分析に失敗しました。", "sections": []})
        else:
            items.append({**base, "overview": res["overview"], "sections": res["sections"]})

    saved = await asyncio.to_thread(
        uastore.save_analysis,
        content_hash=content_hash,
        model=uaa.MODEL_NAME,
        source_ids={
            "mattermost": mm["id"] if mm else None,
            "trello": tr["id"] if tr else None,
            "changelog": cl["id"] if cl else None,
            "github_content_hash": gh_hash,
        },
        stats={
            "member_count": len(member_bundles),
            "other_count": len(other_bundles),
            "available_sources": [
                k for k, v in {
                    "mattermost": mm, "trello": tr, "changelog": cl,
                    "github": bool(gh and gh.get("activity_total")),
                }.items() if v
            ],
        },
        items=items,
    )
    return _user_activity_response(saved, cached=False)


@app.get("/api/user-activity/latest")
def api_user_activity_latest() -> dict[str, Any]:
    """保存済みの最新のアクティビティ分析。無ければ analysis_id=null。"""
    from pipeline import user_activity_store as uastore

    a = uastore.get_latest_analysis()
    if a is None:
        return {"analysis_id": None, "members": [], "others": []}
    return _user_activity_response(a, cached=True)


@app.get("/api/user-activity/runs")
def api_user_activity_runs(limit: int = Query(default=30, le=200)) -> list[dict[str, Any]]:
    from pipeline import user_activity_store as uastore

    return uastore.list_analyses(limit=limit)


@app.get("/api/user-activity/runs/{analysis_id}")
def api_user_activity_run(analysis_id: int) -> dict[str, Any]:
    from pipeline import user_activity_store as uastore

    a = uastore.get_analysis(analysis_id)
    if not a:
        raise HTTPException(status_code=404, detail="分析結果が見つかりません")
    return _user_activity_response(a, cached=True)


# ----------------------------------------------------------------------
# KPT分析(Mattermost / Trello / GitHub / 変更履歴 / 実装差分 の分析結果を
# プロジェクト全体で束ね、Keep / Problem / Try を AI で導出する)
# ----------------------------------------------------------------------
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


@app.post("/api/kpt/analyze")
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


@app.get("/api/kpt/latest")
def api_kpt_latest() -> dict[str, Any]:
    """保存済みの最新の KPT分析。無ければ analysis_id=null。"""
    from pipeline import kpt_store

    a = kpt_store.get_latest_analysis()
    if a is None:
        return {"analysis_id": None, "keep": [], "problem": [], "try": []}
    return _kpt_response(a, cached=True)


@app.get("/api/kpt/runs")
def api_kpt_runs(limit: int = Query(default=30, le=200)) -> list[dict[str, Any]]:
    from pipeline import kpt_store

    return kpt_store.list_analyses(limit=limit)


@app.get("/api/kpt/runs/{analysis_id}")
def api_kpt_run(analysis_id: int) -> dict[str, Any]:
    from pipeline import kpt_store

    a = kpt_store.get_analysis(analysis_id)
    if not a:
        raise HTTPException(status_code=404, detail="分析結果が見つかりません")
    return _kpt_response(a, cached=True)


@app.put("/api/kpt/runs/{analysis_id}")
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


# ----------------------------------------------------------------------
# 定期実行パイプライン(各ツールの取得・分析 → 実装差分解析 → アクティビティ分析)
# ----------------------------------------------------------------------
def _pipeline_step_summary(key: str, res: Any) -> dict[str, Any]:
    """各ステップの主要な結果を、フロー図表示用の小さな dict に要約する。"""
    if not isinstance(res, dict):
        return {}
    if key in ("design", "code"):
        return {"run_id": res.get("run_id"), "feature_count": res.get("feature_count"), "cached": res.get("cached")}
    if key in ("mattermost", "trello", "changelog"):
        return {"analysis_id": res.get("analysis_id"), "account_count": res.get("account_count"), "cached": res.get("cached")}
    if key == "github":
        return {"ingested": res.get("ingested"), "activity_total": res.get("activity_total")}
    if key == "spec_diff":
        return {"diff_id": res.get("diff_id"), "diff_count": res.get("diff_count")}
    if key == "user_activity":
        return {"analysis_id": res.get("analysis_id"), "member_count": res.get("member_count"), "other_count": res.get("other_count")}
    if key == "kpt":
        st = res.get("stats") or {}
        return {
            "analysis_id": res.get("analysis_id"),
            "keep": st.get("keep_count"),
            "problem": st.get("problem_count"),
            "try": st.get("try_count"),
        }
    return {}


async def _run_pipeline(run_id: int, force: bool) -> None:
    """パイプライン本体。各ステップの状態を pipeline_run_steps へ随時記録する。"""
    from datetime import date as _date

    from pipeline import pipeline_store as pstore

    today = _date.today().isoformat()

    async def _step(key: str, factory) -> Any:
        pstore.set_step(run_id, key, "running", started=True)
        try:
            res = await factory()
            pstore.set_step(run_id, key, "success", result=_pipeline_step_summary(key, res), finished=True)
            return res
        except HTTPException as exc:
            pstore.set_step(run_id, key, "error", error=str(exc.detail), finished=True)
        except Exception as exc:  # pragma: no cover - ステップ内の最終防波堤
            logger.exception("パイプライン step=%s で失敗", key)
            pstore.set_step(run_id, key, "error", error=str(exc), finished=True)
        return None

    try:
        # --- フェーズ 1: 各ツールの取得・分析(並列)---
        async def _changelog() -> Any:
            await api_changelog_fetch(force=False, full=False)  # 増分取得
            return await api_changelog_analyze(force=force)

        await asyncio.gather(
            _step("design", lambda: api_design_analyze(force=force)),
            _step("code", lambda: api_code_analyze(force=force)),
            _step("mattermost", lambda: api_mattermost_analyze(
                MattermostAnalyzeBody(mode="current", latest_date=today), force=force
            )),
            _step("trello", lambda: api_trello_analyze(force=force)),
            _step("github", lambda: api_github_ingest(force=force)),
            _step("changelog", _changelog),
        )

        # --- フェーズ 2: 解析(並列)---
        await asyncio.gather(
            _step("spec_diff", lambda: api_spec_diff_analyze()),
            _step("user_activity", lambda: api_user_activity_analyze(force=force)),
            _step("kpt", lambda: api_kpt_analyze(force=force)),
        )

        run = pstore.get_run(run_id) or {"steps": []}
        has_error = any(s["status"] == "error" for s in run["steps"])
        pstore.finish_run(run_id, "error" if has_error else "success")
    except Exception as exc:  # pragma: no cover - パイプライン全体の防波堤
        logger.exception("パイプライン run=%s で未捕捉例外", run_id)
        pstore.finish_run(run_id, "error", detail=str(exc))


@app.post("/api/pipeline/run")
async def api_pipeline_run(force: bool = Query(default=False)) -> dict[str, Any]:
    """定期実行パイプラインを即時開始する(バックグラウンド)。run_id を即返す。"""
    from pipeline import pipeline_store as pstore

    existing = await asyncio.to_thread(pstore.running_run_id)
    if existing:
        raise HTTPException(status_code=409, detail=f"パイプラインは既に実行中です(run #{existing})")

    run_id = await asyncio.to_thread(pstore.create_run)
    asyncio.create_task(_run_pipeline(run_id, force))
    return {"run_id": run_id, "status": "running"}


@app.get("/api/pipeline/latest")
def api_pipeline_latest() -> dict[str, Any]:
    """最新のパイプライン実行の進捗(フロー図用)。無ければ id=null。"""
    from pipeline import pipeline_store as pstore

    run = pstore.get_latest_run()
    return run or {"id": None, "status": None, "steps": []}


@app.get("/api/pipeline/runs")
def api_pipeline_runs(limit: int = Query(default=30, le=200)) -> list[dict[str, Any]]:
    from pipeline import pipeline_store as pstore

    return pstore.list_runs(limit=limit)


@app.get("/api/pipeline/runs/{run_id}")
def api_pipeline_run(run_id: int) -> dict[str, Any]:
    from pipeline import pipeline_store as pstore

    run = pstore.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="実行が見つかりません")
    return run


@app.exception_handler(Exception)
async def _unhandled(_request, exc: Exception):  # pragma: no cover
    """未捕捉例外を 500 + 説明文で返す。"""
    logger.exception("API 未捕捉例外")
    return JSONResponse(status_code=500, content={"detail": str(exc)})
