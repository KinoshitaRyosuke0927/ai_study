"""FastAPI アプリ本体。

- 起動時に schema.sql を適用し、APScheduler(有効時)を開始する。
- ダッシュボード(static/index.html)と JSON API を提供する。
- パイプラインの手動実行はバックグラウンドスレッドで開始し run_id を即返す。
"""

from __future__ import annotations

import json
import logging
import threading
from contextlib import asynccontextmanager
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import text

import weekly
from ai import AiAnalyzer
from db import apply_schema, get_session_factory, ping
from provider_options import (
    check_github_path,
    check_github_repo,
    check_growi_path,
    list_mattermost_channels,
    list_trello_boards,
)
from rag import search as rag_search
from runtime_config import (
    SCHEDULE_KINDS,
    WEEKDAY_LABELS_JA,
    RuntimeConfig,
    load_runtime_config,
    save_runtime_config,
)
from settings import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("frontier.app")

STATIC_DIR = "static"
_scheduler: BackgroundScheduler | None = None


def _run_pipeline_async(mode: str, analyze: bool) -> int:
    """パイプラインを別スレッドで開始し、run_id を返す。"""
    run_id = weekly.create_run(mode)

    def _target() -> None:
        try:
            weekly.run(mode=mode, analyze=analyze, run_id=run_id)
        except Exception:  # pragma: no cover - スレッド内の最終防波堤
            logger.exception("パイプラインスレッドで未捕捉例外")

    threading.Thread(target=_target, name=f"pipeline-{run_id}", daemon=True).start()
    return run_id


def _scheduler_tick() -> None:
    """毎日 0:00 に APScheduler から呼ばれるディスパッチャ。

    実際の実行間隔判定(日次 N 日 / 週次 曜日)は weekly.scheduled_tick が
    acquisition_settings.json を「実行時に」読み込んで行う。
    """
    try:
        weekly.scheduled_tick()
    except Exception:  # pragma: no cover - スケジューラスレッドの防波堤
        logger.exception("定期実行チェックで未捕捉例外")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """起動時: スキーマ適用 + スケジューラ開始 / 終了時: スケジューラ停止。"""
    settings = get_settings()
    apply_schema(settings)
    logger.info(
        "起動: run_mode=%s ai_enabled=%s schedule_enabled=%s",
        settings.app_run_mode,
        settings.ai_enabled,
        settings.app_schedule_enabled,
    )

    global _scheduler
    if settings.app_schedule_enabled:
        _scheduler = BackgroundScheduler(timezone=settings.app_tz)
        # 毎日 0:00 に起動判定。間隔・曜日の設定は tick 実行時に acquisition_settings.json から読む
        _scheduler.add_job(
            _scheduler_tick,
            CronTrigger(hour=0, minute=0, timezone=settings.app_tz),
            id="daily-tick",
            replace_existing=True,
        )
        _scheduler.start()
        logger.info("APScheduler 開始: 毎日 0:00 に定期実行を判定 tz=%s", settings.app_tz)

    yield

    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler 停止")


app = FastAPI(title="Frontier", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ----------------------------------------------------------------------
# ヘルパ
# ----------------------------------------------------------------------
def _session():
    """新しい SQLAlchemy セッションを返す。"""
    return get_session_factory(get_settings())()


def _json_col(value: Any) -> Any:
    """MySQL の JSON カラム値(dict または str)を Python オブジェクトへ。"""
    if value is None:
        return None
    return value if not isinstance(value, (str, bytes)) else json.loads(value)


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
        "is_sample_mode": settings.is_sample_mode,
        "ai_enabled": settings.ai_enabled,
        "schedule_enabled": settings.app_schedule_enabled,
    }


@app.post("/api/run")
def api_run(analyze: bool = Query(default=True)) -> dict[str, Any]:
    """パイプラインを手動実行(非同期開始)。run_id を返す。"""
    run_id = _run_pipeline_async(mode="manual", analyze=analyze)
    return {"run_id": run_id, "status": "started", "analyze": analyze}


@app.get("/api/runs")
def api_runs(limit: int = Query(default=30, le=200)) -> list[dict[str, Any]]:
    """実行履歴一覧(新しい順)。"""
    with _session() as s:
        rows = s.execute(
            text(
                """
                SELECT id, started_at, finished_at, status, mode, detail
                FROM runs ORDER BY id DESC LIMIT :lim
                """
            ),
            {"lim": limit},
        ).all()
    return [
        {
            "id": r.id,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "status": r.status,
            "mode": r.mode,
            "detail": r.detail,
        }
        for r in rows
    ]


@app.get("/api/weeks")
def api_weeks() -> list[str]:
    """データが存在する週の一覧(古い順)。"""
    with _session() as s:
        rows = s.execute(
            text(
                """
                SELECT DISTINCT week FROM (
                    SELECT week FROM metrics
                    UNION SELECT week FROM events
                    UNION SELECT week FROM week_items
                ) t ORDER BY week ASC
                """
            )
        ).scalars().all()
    return list(rows)


@app.get("/api/metrics")
def api_metrics() -> dict[str, Any]:
    """週ごとの指標(推移グラフ用)。"""
    from metrics import METRIC_NAMES

    with _session() as s:
        weeks = s.execute(
            text("SELECT DISTINCT week FROM metrics ORDER BY week ASC")
        ).scalars().all()
        rows = s.execute(text("SELECT week, name, value FROM metrics")).all()
    by_week: dict[str, dict[str, float]] = {w: {} for w in weeks}
    for w, name, value in rows:
        by_week.setdefault(w, {})[name] = value
    return {"weeks": list(weeks), "metric_names": METRIC_NAMES, "data": by_week}


@app.get("/api/report/{week}")
def api_report(week: str) -> dict[str, Any]:
    """指定週の KPT + risks + サマリ。"""
    with _session() as s:
        row = s.execute(
            text("SELECT week, kpt, risks, summary_md, created_at FROM reports WHERE week = :w"),
            {"w": week},
        ).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"レポート未生成の週です: {week}")
    return {
        "week": row.week,
        "kpt": _json_col(row.kpt),
        "risks": _json_col(row.risks),
        "summary_md": row.summary_md,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@app.get("/api/diff/{week}")
def api_diff(week: str) -> dict[str, Any]:
    """指定週の added / changed / removed 一覧。"""
    from store import compute_diff

    with _session() as s:
        diff = compute_diff(s, week)
    return {"week": week, **diff}


@app.get("/api/events")
def api_events(
    week: str | None = None,
    source: str | None = None,
    type: str | None = None,
    limit: int = Query(default=200, le=1000),
) -> list[dict[str, Any]]:
    """生イベント閲覧(week / source / type で絞り込み)。"""
    clauses: list[str] = []
    params: dict[str, Any] = {"lim": limit}
    if week:
        clauses.append("week = :week")
        params["week"] = week
    if source:
        clauses.append("source = :source")
        params["source"] = source
    if type:
        clauses.append("type = :type")
        params["type"] = type
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _session() as s:
        rows = s.execute(
            text(
                f"""
                SELECT id, week, source, type, actor, ts, ref, payload, event_uid
                FROM events {where}
                ORDER BY ts DESC LIMIT :lim
                """
            ),
            params,
        ).all()
    return [
        {
            "id": r.id,
            "week": r.week,
            "source": r.source,
            "type": r.type,
            "actor": r.actor,
            "ts": r.ts.isoformat() if r.ts else None,
            "ref": r.ref,
            "payload": _json_col(r.payload),
            "event_uid": r.event_uid,
        }
        for r in rows
    ]


@app.get("/api/decisions")
def api_decisions(week: str | None = None) -> list[dict[str, Any]]:
    """暗黙知(決定事項)一覧。"""
    where = "WHERE week = :week" if week else ""
    params = {"week": week} if week else {}
    with _session() as s:
        rows = s.execute(
            text(
                f"""
                SELECT id, week, summary, rationale, participants, source_refs
                FROM decisions {where} ORDER BY week DESC, id DESC
                """
            ),
            params,
        ).all()
    return [
        {
            "id": r.id,
            "week": r.week,
            "summary": r.summary,
            "rationale": r.rationale,
            "participants": _json_col(r.participants),
            "source_refs": _json_col(r.source_refs),
        }
        for r in rows
    ]


class SearchBody(BaseModel):
    """/api/search のリクエストボディ。"""

    query: str


@app.post("/api/search")
def api_search(body: SearchBody) -> dict[str, Any]:
    """自然文検索(RAG): 検索結果 + AI 回答。"""
    settings = get_settings()
    analyzer = AiAnalyzer(settings)
    with _session() as s:
        result = rag_search(s, analyzer, body.query)
    return result


# ----------------------------------------------------------------------
# 設定(データ取得に関する実行時設定 / acquisition_settings.json)
# ----------------------------------------------------------------------
class ScheduleBody(BaseModel):
    """定期実行間隔。"""

    kind: str  # "daily" | "weekly"
    interval_days: int = 7  # daily: N 日ごと
    weekday: int = 0  # weekly: 0=月 .. 6=日


class SettingsBody(BaseModel):
    """/api/settings (POST) のリクエストボディ。"""

    since_date: str | None = None  # "YYYY-MM-DD" または null
    schedule: ScheduleBody
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
        "schedule_kinds": list(SCHEDULE_KINDS),
        "weekday_labels": WEEKDAY_LABELS_JA,
        "is_sample_mode": settings.is_sample_mode,
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

    # --- 形式バリデーション ---
    if body.schedule.kind not in SCHEDULE_KINDS:
        raise HTTPException(status_code=422, detail=f"kind は {SCHEDULE_KINDS} のいずれか")
    if not (1 <= body.schedule.interval_days <= 31):
        raise HTTPException(status_code=422, detail="interval_days は 1〜31")
    if not (0 <= body.schedule.weekday <= 6):
        raise HTTPException(status_code=422, detail="weekday は 0(月)〜6(日)")

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
        schedule_kind=body.schedule.kind,
        schedule_interval_days=body.schedule.interval_days,
        schedule_weekday=body.schedule.weekday,
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


@app.post("/api/mattermost/fetch")
def api_mattermost_fetch(body: MattermostFetchBody) -> dict[str, Any]:
    """設定チャンネルの投稿を、指定期間ぶんチャンネル別・スレッド構造で返す。"""
    from datetime import date as _date

    import mattermost_view

    settings = get_settings()
    rc = load_runtime_config()

    def _parse(label: str, value: str | None) -> _date:
        if not value:
            raise HTTPException(status_code=422, detail=f"{label} を指定してください")
        try:
            return _date.fromisoformat(value)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"{label} は YYYY-MM-DD 形式で指定してください")

    if body.mode == "current":
        if rc.since_date is None:
            raise HTTPException(
                status_code=422,
                detail="設定画面で「データ取得開始日時」を設定してください",
            )
        start_d = rc.since_date
        end_d = _parse("最新日", body.latest_date)
    elif body.mode == "range":
        start_d = _parse("開始日", body.start_date)
        end_d = _parse("終了日", body.end_date)
    else:
        raise HTTPException(status_code=422, detail="mode は current / range のいずれか")

    try:
        result = mattermost_view.fetch_posts(
            settings, rc.mattermost_channel_ids, start_d, end_d
        )
    except mattermost_view.MattermostViewError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    result["mode"] = body.mode
    return result


# ----------------------------------------------------------------------
# Trello 情報取得(画面表示用。DB へは保存しない)
# ----------------------------------------------------------------------
class TrelloFetchBody(BaseModel):
    """/api/trello/fetch のリクエストボディ。"""

    board_id: str


@app.get("/api/trello/boards")
def api_trello_boards() -> dict[str, Any]:
    """取得対象ボード設定のプルダウン用: 設定済みボードを名前付きで返す。"""
    import trello_view

    settings = get_settings()
    rc = load_runtime_config()
    boards, err = trello_view.list_configured_boards(settings, rc.trello_board_ids)
    return {"boards": boards, "error": err}


@app.post("/api/trello/fetch")
def api_trello_fetch(body: TrelloFetchBody) -> dict[str, Any]:
    """指定ボードの現在の状況(リスト / カード / 詳細 / 活動)を返す。"""
    import trello_view

    settings = get_settings()
    try:
        return trello_view.fetch_board(settings, body.board_id.strip())
    except trello_view.TrelloViewError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ----------------------------------------------------------------------
# wiki(GROWI)情報取得(画面表示用。DB へは保存しない)
# ----------------------------------------------------------------------
class GrowiFetchBody(BaseModel):
    """/api/growi/fetch のリクエストボディ。"""

    page_id: str


@app.get("/api/growi/pages")
def api_growi_pages() -> dict[str, Any]:
    """設定の「参照する Wiki のページ」配下のページ一覧(プルダウン用)。"""
    import growi_view

    settings = get_settings()
    rc = load_runtime_config()
    try:
        return growi_view.list_pages(settings, rc.growi_page_path)
    except growi_view.GrowiViewError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/growi/fetch")
def api_growi_fetch(body: GrowiFetchBody) -> dict[str, Any]:
    """選択ページの記事内容・更新履歴・コメントを返す。"""
    import growi_view

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
    import github_view

    settings = get_settings()
    rc = load_runtime_config()
    try:
        return github_view.fetch_repo_activity(settings, rc.github_repo)
    except github_view.GitHubViewError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ----------------------------------------------------------------------
# 設計書情報取得(画面表示用。DB へは保存しない)
# ----------------------------------------------------------------------
@app.post("/api/design/fetch")
def api_design_fetch() -> dict[str, Any]:
    """設定「設計書パス」配下の全ファイル内容をファイルごとに返す。"""
    import design_view

    settings = get_settings()
    rc = load_runtime_config()
    try:
        return design_view.fetch_design_files(settings, rc.github_repo, rc.github_design_path)
    except design_view.DesignViewError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.exception_handler(Exception)
async def _unhandled(_request, exc: Exception):  # pragma: no cover
    """未捕捉例外を 500 + 説明文で返す。"""
    logger.exception("API 未捕捉例外")
    return JSONResponse(status_code=500, content={"detail": str(exc)})
