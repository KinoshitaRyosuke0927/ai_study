"""暗黙知抽出(Mattermost / Trello / GitHub から抽出したプロジェクト固有の知見の
一覧表示・★評価)と、評価値の学習(バックグラウンドタスク)。
抽出処理は pipeline/tacit_analysis.py・tacit_store.py に、学習処理は
pipeline/tacit_ml.py・tacit_store.py に委譲する。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger("frontier.tacit")

router = APIRouter()


class TacitRatingBody(BaseModel):
    """画面での★評価リクエスト。rating=None は「未評価に戻す」。"""

    rating: int | None = None


async def _rescore_items(settings, model_path: str, items: list[dict[str, Any]]) -> int:
    """items([{"id","content"}])を最新モデルでスコアリングし、predicted_rating を反映する。"""
    from pipeline import tacit_ml, tacit_store

    if not items:
        return 0
    preds = await asyncio.to_thread(
        tacit_ml.predict_ratings, settings, model_path, [it["content"] for it in items]
    )
    if preds is None:
        return 0
    pairs = list(zip((it["id"] for it in items), preds))
    return await asyncio.to_thread(tacit_store.bulk_update_predicted_rating, pairs)


@router.post("/api/tacit/extract")
async def api_tacit_extract(force: bool = Query(default=False)) -> dict[str, Any]:
    """Mattermost / Trello / GitHub の未処理データから暗黙知を抽出し DB へ登録する。

    force=True の場合、処理済みマーカーを無視してすべての候補を再抽出する。
    学習済みモデルがあれば、新規に登録した未評価アイテムへ予測評価値を付与する。
    """
    from config.runtime import load_runtime_config
    from config.settings import get_settings
    from pipeline import tacit_analysis as ta, tacit_store
    from viewers import github as github_view

    settings = get_settings()
    rc = load_runtime_config()
    repo = github_view._resolve_repo(settings, (rc.github_repo or "").strip())

    candidates = await asyncio.to_thread(tacit_store.fetch_candidates, repo, force)
    if not any(candidates.values()):
        return await asyncio.to_thread(tacit_store.save_run_empty, ta.MODEL_NAME)

    try:
        extracted = await asyncio.to_thread(ta.extract_all, settings, candidates)
    except ta.TacitAnalysisError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    saved = await asyncio.to_thread(
        tacit_store.save_extraction,
        model=ta.MODEL_NAME,
        candidates=candidates,
        extracted=extracted,
    )

    model_path = await asyncio.to_thread(tacit_store.get_latest_successful_model_path)
    if model_path:
        new_items = await asyncio.to_thread(tacit_store.fetch_unrated_unscored_items)
        try:
            await _rescore_items(settings, model_path, new_items)
        except Exception:  # pragma: no cover - スコアリング失敗は抽出結果自体には影響させない
            logger.exception("抽出後の予測評価値スコアリングに失敗")

    return saved


@router.get("/api/tacit/items")
def api_tacit_items(
    rating: str | None = Query(default=None, description='"unrated" / "0"〜"5" / 省略で全件'),
    limit: int = Query(default=1000, le=1000),
) -> dict[str, Any]:
    from pipeline import tacit_store

    return {"items": tacit_store.list_items(rating=rating, limit=limit)}


@router.put("/api/tacit/items/{item_id}")
def api_tacit_rate(item_id: int, body: TacitRatingBody) -> dict[str, Any]:
    """画面での★評価を保存する。"""
    from pipeline import tacit_store

    if body.rating is not None and not (0 <= body.rating <= 5):
        raise HTTPException(status_code=422, detail="rating は 0〜5 の範囲で指定してください")

    updated = tacit_store.update_rating(item_id, body.rating)
    if updated is None:
        raise HTTPException(status_code=404, detail="項目が見つかりません")
    return updated


@router.get("/api/tacit/runs")
def api_tacit_runs(limit: int = Query(default=30, le=200)) -> list[dict[str, Any]]:
    from pipeline import tacit_store

    return tacit_store.list_runs(limit=limit)


# ----------------------------------------------------------------------
# 評価値学習
# ----------------------------------------------------------------------
async def _train_with_items(run_id: int, items: list[dict[str, Any]]) -> None:
    """学習本体(items は呼び出し元が取得済みのものを渡す)。

    手動実行(/api/tacit/train)からは asyncio.create_task でバックグラウンド起動され、
    定期実行パイプラインからは await で完了を待って呼ばれる(パイプライン自体が
    既にバックグラウンドタスクのため、ここで改めて非同期化する必要が無い)。
    """
    from config.settings import get_settings
    from pipeline import tacit_ml, tacit_store

    settings = get_settings()
    ratings_hash = tacit_store.hash_rated_pairs(items)
    try:
        result = await asyncio.to_thread(tacit_ml.train_model, settings, run_id, items)
        await asyncio.to_thread(
            tacit_store.finish_training_run,
            run_id,
            status="success",
            algorithm="ridge",
            training_item_count=result["training_item_count"],
            feature_dim=result["feature_dim"],
            model_path=result["model_path"],
            metrics=result["metrics"],
            ratings_hash=ratings_hash,
        )
        # 学習し直したので、未評価アイテム全件を最新モデルで再スコアリングする
        unrated = await asyncio.to_thread(tacit_store.fetch_all_unrated_items)
        await _rescore_items(settings, result["model_path"], unrated)
    except tacit_ml.TacitTrainingError as exc:
        await asyncio.to_thread(tacit_store.finish_training_run, run_id, status="error", detail=str(exc))
    except Exception as exc:  # pragma: no cover - 学習処理全体の防波堤
        logger.exception("暗黙知モデル学習で失敗 run=%s", run_id)
        await asyncio.to_thread(tacit_store.finish_training_run, run_id, status="error", detail=str(exc))


@router.post("/api/tacit/train")
async def api_tacit_train() -> dict[str, Any]:
    """★評価済みの暗黙知を教師データにモデルを学習する(バックグラウンド実行。run_id を即返す)。"""
    from pipeline import tacit_store

    existing = await asyncio.to_thread(tacit_store.running_training_run_id)
    if existing:
        raise HTTPException(status_code=409, detail=f"学習は既に実行中です(run #{existing})")

    items = await asyncio.to_thread(tacit_store.fetch_rated_items)
    run_id = await asyncio.to_thread(tacit_store.create_training_run)
    asyncio.create_task(_train_with_items(run_id, items))
    return {"run_id": run_id, "status": "running"}


async def run_training_for_pipeline(force: bool = False) -> dict[str, Any]:
    """定期実行パイプラインからの呼び出し用。完了まで待って結果を返す。

    force=False の場合、前回学習成功時から評価内容(id×rating)に変更が無ければ、
    学習をスキップする(他の分析ステップと同じ「内容が変わっていなければキャッシュ再利用」の考え方。
    ★評価はユーザーの手動操作なので、変更が無い限り毎回再学習する必要が無い)。
    """
    from pipeline import tacit_store

    items = await asyncio.to_thread(tacit_store.fetch_rated_items)
    ratings_hash = tacit_store.hash_rated_pairs(items)
    if not force:
        latest_hash = await asyncio.to_thread(tacit_store.get_latest_successful_ratings_hash)
        if latest_hash is not None and latest_hash == ratings_hash:
            return {"run_id": None, "status": "skipped", "cached": True}

    existing = await asyncio.to_thread(tacit_store.running_training_run_id)
    if existing:
        return {"run_id": existing, "status": "running", "detail": "既に学習が実行中のため今回はスキップしました"}

    run_id = await asyncio.to_thread(tacit_store.create_training_run)
    await _train_with_items(run_id, items)
    return await asyncio.to_thread(tacit_store.get_training_run, run_id)


@router.get("/api/tacit/train/latest")
def api_tacit_train_latest() -> dict[str, Any]:
    from pipeline import tacit_store

    run = tacit_store.get_latest_training_run()
    return run or {"id": None, "status": None}


@router.get("/api/tacit/train/runs")
def api_tacit_train_runs(limit: int = Query(default=30, le=200)) -> list[dict[str, Any]]:
    from pipeline import tacit_store

    return tacit_store.list_training_runs(limit=limit)


@router.get("/api/tacit/train/runs/{run_id}")
def api_tacit_train_run(run_id: int) -> dict[str, Any]:
    from pipeline import tacit_store

    run = tacit_store.get_training_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="実行が見つかりません")
    return run
