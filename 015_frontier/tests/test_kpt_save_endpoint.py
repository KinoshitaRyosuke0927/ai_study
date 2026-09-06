"""KPT分析の保存エンドポイント(app.api_kpt_save)のテスト。"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

import app
from pipeline import kpt_store


def _seed() -> int:
    saved = kpt_store.save_analysis(
        content_hash="h-ep", model="m",
        source_ids={}, stats={"available_sources": ["github"], "keep_count": 1},
        items=[
            {"kind": "keep", "title": "K1", "detail": "d", "evidence": "keep-ev", "sources": ["github"]},
            {"kind": "problem", "title": "P1", "detail": "", "evidence": "", "sources": ["spec_diff"]},
        ],
    )
    return saved["id"]


def test_api_kpt_save_persists_order_kind_and_importance(db_session):
    aid = _seed()
    body = app.KptSaveBody(items=[
        # P1 を keep へ移動、importance は 5 超えをクランプ、未知ソースは除去
        app.KptItemBody(kind="keep", title="P1", detail="", evidence="p-ev",
                        sources=["spec_diff", "bogus"], importance=9),
        app.KptItemBody(kind="keep", title="K1", detail="d", evidence="keep-ev",
                        sources=["github"], importance=0),
        # 不正な kind は無視される
        app.KptItemBody(kind="junk", title="X", importance=1),
        app.KptItemBody(kind="try", title="T-new", detail="", evidence="", sources=[], importance=-3),
    ])
    res = asyncio.run(app.api_kpt_save(aid, body))

    assert [i["title"] for i in res["keep"]] == ["P1", "K1"]
    assert res["keep"][0]["importance"] == 5           # 9 -> 5 にクランプ
    assert res["keep"][0]["sources"] == ["spec_diff"]  # "bogus" 除去
    assert [i["title"] for i in res["try"]] == ["T-new"]
    assert res["try"][0]["importance"] == 0            # -3 -> 0
    assert res["problem"] == []
    assert res["stats"]["keep_count"] == 2 and res["stats"]["problem_count"] == 0
    assert res["stats"]["available_sources"] == ["github"]

    # DB にも反映されている
    again = kpt_store.get_analysis(aid)
    assert [i["title"] for i in again["keep"]] == ["P1", "K1"]


def test_api_kpt_save_unknown_id_404(db_session):
    with pytest.raises(HTTPException) as ei:
        asyncio.run(app.api_kpt_save(424242, app.KptSaveBody(items=[])))
    assert ei.value.status_code == 404
