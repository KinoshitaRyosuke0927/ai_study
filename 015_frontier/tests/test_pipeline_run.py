"""パイプライン本体(app._run_pipeline)のオーケストレーションのテスト。

各ツールのエンドポイント関数をモックに差し替え、フェーズ1(並列)→フェーズ2(順次)の
進捗記録・エラーハンドリング・全体ステータス判定を検証する。
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

import app
from pipeline import pipeline_store as pstore


def _mk(key, calls, *, result=None, exc=None):
    async def _f(*_a, **_k):
        calls.append(key)
        if exc is not None:
            raise exc
        return result or {}
    return _f


@pytest.fixture()
def mock_steps(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(app, "api_design_analyze", _mk("design", calls, result={"run_id": 1, "feature_count": 3, "cached": False}))
    monkeypatch.setattr(app, "api_code_analyze", _mk("code", calls, result={"run_id": 2, "feature_count": 5, "cached": True}))
    monkeypatch.setattr(app, "api_mattermost_analyze", _mk("mattermost", calls, result={"analysis_id": 1, "account_count": 4}))
    monkeypatch.setattr(app, "api_trello_analyze", _mk("trello", calls, result={"analysis_id": 2, "account_count": 3}))
    monkeypatch.setattr(app, "api_github_ingest", _mk("github", calls, result={"ingested": True, "activity_total": 80}))
    monkeypatch.setattr(app, "api_changelog_fetch", _mk("cl_fetch", calls, result={}))
    monkeypatch.setattr(app, "api_changelog_analyze", _mk("changelog", calls, result={"analysis_id": 3, "account_count": 4}))
    monkeypatch.setattr(app, "api_spec_diff_analyze", _mk("spec_diff", calls, exc=HTTPException(status_code=422, detail="材料が不足")))
    monkeypatch.setattr(app, "api_user_activity_analyze", _mk("user_activity", calls, result={"analysis_id": 1, "member_count": 5, "other_count": 2}))
    monkeypatch.setattr(app, "api_kpt_analyze", _mk("kpt", calls, result={"analysis_id": 1, "stats": {"keep_count": 3, "problem_count": 2, "try_count": 2}}))
    return calls


def test_run_pipeline_progress_and_error_handling(db_session, mock_steps):
    run_id = pstore.create_run()
    asyncio.run(app._run_pipeline(run_id, force=False))

    run = pstore.get_run(run_id)
    st = {s["step_key"]: s for s in run["steps"]}

    # フェーズ1: すべて成功、結果サマリが入る
    for k in ("design", "code", "mattermost", "trello", "github", "changelog"):
        assert st[k]["status"] == "success", k
    assert st["design"]["result"]["feature_count"] == 3
    assert st["code"]["result"]["cached"] is True
    assert st["github"]["result"]["activity_total"] == 80
    # 変更履歴は fetch → analyze の 2 サブ呼び出し
    assert "cl_fetch" in mock_steps and "changelog" in mock_steps

    # フェーズ2: spec_diff は失敗を記録、後続の user_activity は実行される
    assert st["spec_diff"]["status"] == "error" and "材料が不足" in st["spec_diff"]["error"]
    assert st["user_activity"]["status"] == "success"
    assert st["user_activity"]["result"]["member_count"] == 5

    # 1 つでも error なら全体 error
    assert run["status"] == "error" and run["finished_at"] is not None
    assert pstore.running_run_id() is None


def test_run_pipeline_all_success(db_session, monkeypatch):
    calls: list[str] = []
    for name in (
        "api_design_analyze", "api_code_analyze", "api_mattermost_analyze",
        "api_trello_analyze", "api_github_ingest", "api_changelog_fetch",
        "api_changelog_analyze", "api_spec_diff_analyze", "api_user_activity_analyze",
        "api_kpt_analyze",
    ):
        monkeypatch.setattr(app, name, _mk(name, calls, result={}))

    run_id = pstore.create_run()
    asyncio.run(app._run_pipeline(run_id, force=True))

    run = pstore.get_run(run_id)
    assert run["status"] == "success"
    assert all(s["status"] == "success" for s in run["steps"])
