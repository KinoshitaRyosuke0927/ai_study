"""FastAPI アプリ本体(合成ルート + 定期実行パイプラインの統括)。

- 起動時に schema.sql を適用する。
- ダッシュボード(static/index.html)と JSON API を提供する。
- 各機能のエンドポイントは routers/ 配下の APIRouter に分割し、ここで include する。
- 定期実行パイプラインは複数エンドポイントを束ねる統括役なので、このファイルに残す。
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from infra.db import apply_schema
from config.settings import get_settings

from routers import (
    analysis,
    changelog,
    code,
    design,
    github,
    growi,
    health,
    kpt,
    mattermost,
    settings as settings_router,
    spec_diff,
    trello,
    user_activity,
)
from routers.common import DESIGN_DETAIL_MAX_PARALLEL  # noqa: F401  (後方互換)

# --- テスト / パイプラインが app.<name> で参照するハンドラを名前空間へ取り込む ---
# tests/test_pipeline_run.py は monkeypatch.setattr(app, "api_*", ...) で差し替え、
# _run_pipeline は下記の bare name を呼ぶ(= app モジュール dict を見る)ため、ここで import する。
from routers.changelog import api_changelog_analyze, api_changelog_fetch  # noqa: E402
from routers.code import api_code_analyze  # noqa: E402
from routers.design import api_design_analyze  # noqa: E402
from routers.github import api_github_ingest  # noqa: E402
from routers.kpt import (  # noqa: E402
    KptItemBody,
    KptSaveBody,
    api_kpt_analyze,
    api_kpt_save,
)
from routers.mattermost import MattermostAnalyzeBody, api_mattermost_analyze  # noqa: E402
from routers.spec_diff import api_spec_diff_analyze  # noqa: E402
from routers.trello import api_trello_analyze  # noqa: E402
from routers.user_activity import api_user_activity_analyze  # noqa: E402

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

# --- 各機能のルータを取り込む ---
app.include_router(health.router)
app.include_router(settings_router.router)
app.include_router(mattermost.router)
app.include_router(trello.router)
app.include_router(changelog.router)
app.include_router(growi.router)
app.include_router(github.router)
app.include_router(design.router)
app.include_router(code.router)
app.include_router(analysis.router)
app.include_router(spec_diff.router)
app.include_router(user_activity.router)
app.include_router(kpt.router)


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
