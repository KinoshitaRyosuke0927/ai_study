"""ルータ間で共有するヘルパ・定数。

- 設計書分析 / コード分析 の 2 回目(機能ごとの詳細)を並列実行する仕組みは
  design ルータと code ルータで共通なので、ここに置く。
- 保存済み run を分析画面のレスポンス形へ整える処理も design / code / analysis で共通。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger("frontier.routers")

# 2 回目(機能ごとの詳細仕様)の AI 呼び出しを並列実行する際の最大同時数
# (Azure OpenAI のレート制限に配慮して上限を設ける)
DESIGN_DETAIL_MAX_PARALLEL = 5


def analysis_run_response(run: dict[str, Any], *, cached: bool) -> dict[str, Any]:
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


async def run_feature_details(
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
