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
from rag import search as rag_search
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


def _scheduled_job() -> None:
    """APScheduler から呼ばれる週次ジョブ。"""
    logger.info("スケジュール実行を開始します")
    _run_pipeline_async(mode="scheduled", analyze=True)


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
        # crontab 形式("m h dom mon dow")を CronTrigger へ
        trigger = CronTrigger.from_crontab(
            settings.app_schedule_cron, timezone=settings.app_tz
        )
        _scheduler.add_job(_scheduled_job, trigger, id="weekly", replace_existing=True)
        _scheduler.start()
        logger.info("APScheduler 開始: cron='%s' tz=%s", settings.app_schedule_cron, settings.app_tz)

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


@app.exception_handler(Exception)
async def _unhandled(_request, exc: Exception):  # pragma: no cover
    """未捕捉例外を 500 + 説明文で返す。"""
    logger.exception("API 未捕捉例外")
    return JSONResponse(status_code=500, content={"detail": str(exc)})
