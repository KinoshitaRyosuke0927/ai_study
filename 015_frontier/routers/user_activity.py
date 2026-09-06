"""アクティビティ分析(各ツールのアカウント別分析を settings.ini の
[USER_ID] でユーザ単位に束ねる)。"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from config.runtime import load_runtime_config
from config.settings import get_settings
from routers.common import DESIGN_DETAIL_MAX_PARALLEL

logger = logging.getLogger("frontier.routers.user_activity")

router = APIRouter()


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


@router.post("/api/user-activity/analyze")
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


@router.get("/api/user-activity/latest")
def api_user_activity_latest() -> dict[str, Any]:
    """保存済みの最新のアクティビティ分析。無ければ analysis_id=null。"""
    from pipeline import user_activity_store as uastore

    a = uastore.get_latest_analysis()
    if a is None:
        return {"analysis_id": None, "members": [], "others": []}
    return _user_activity_response(a, cached=True)


@router.get("/api/user-activity/runs")
def api_user_activity_runs(limit: int = Query(default=30, le=200)) -> list[dict[str, Any]]:
    from pipeline import user_activity_store as uastore

    return uastore.list_analyses(limit=limit)


@router.get("/api/user-activity/runs/{analysis_id}")
def api_user_activity_run(analysis_id: int) -> dict[str, Any]:
    from pipeline import user_activity_store as uastore

    a = uastore.get_analysis(analysis_id)
    if not a:
        raise HTTPException(status_code=404, detail="分析結果が見つかりません")
    return _user_activity_response(a, cached=True)
