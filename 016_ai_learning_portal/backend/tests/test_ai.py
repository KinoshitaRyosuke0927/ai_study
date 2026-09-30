"""AI による講座作成のテスト(AI は偽のクライアントに差し替える)。"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ai.client import set_ai_client
from app.infra import db
from app.models import AIGeneration, AIJob

OUTLINE = {
    "title": "時系列分析入門",
    "summary": "移動平均から予測の評価までを学ぶ。",
    "tags": ["時系列"],
    "outcomes": ["移動平均を計算できる"],
    "libraries": ["pandas"],
    "units": [
        {"title": "移動平均", "summary": "rolling の使い方", "goals": ["移動平均を計算できる"], "minutes": 20, "exercise_count": 1},
        {"title": "予測の評価", "summary": "MAE と RMSE", "goals": ["誤差を計算できる"], "minutes": 25, "exercise_count": 1},
    ],
    "quiz_count": 3,
}
UNIT = {
    "cells": [
        {"type": "markdown", "source": "## 移動平均とは\\n直近 k 個の平均です。"},
        {"type": "code", "source": "import pandas as pd\\nprint(pd.Series([1, 2, 3]).rolling(2).mean())"},
        {
            "type": "exercise",
            "exercise": {
                "title": "3日移動平均",
                "prompt": "最終日の3日移動平均を表示してください。",
                "starter_code": "import pandas as pd\\ns = pd.Series([1, 2, 3, 4])\\nprint(s.rolling(____).mean().iloc[-1])",
                "model_answer": "import pandas as pd\\ns = pd.Series([1, 2, 3, 4])\\nprint(s.rolling(3).mean().iloc[-1])",
                "grading": "output",
            },
        },
    ]
}
QUIZ = {
    "questions": [
        {"type": "choice", "prompt": "移動平均の効果は?", "choices": ["平滑化", "増幅"], "answer": "平滑化", "unit": 1},
        {"type": "numeric", "prompt": "1,2,3 の平均は?", "answer": "2", "unit": 1},
        {"type": "code", "prompt": "MAE を表示", "starter_code": "print(____)", "model_answer": "print(0.5)", "unit": 2},
    ]
}


class FakeAI:
    """プロンプトの内容に応じて、決まった JSON を返す偽の AI。"""

    def __init__(self, broken_first: bool = False):
        self.calls: list[tuple[str, str]] = []
        self.broken_first = broken_first

    def complete_json(self, system_prompt: str, user_prompt: str, model: str) -> str:
        self.calls.append((system_prompt, model))
        # 最初の1回だけ形式の崩れた応答を返す(再試行の確認用)
        if self.broken_first and len(self.calls) == 1:
            return '{"title": "x"}'
        if "構成案" in system_prompt:
            return json.dumps(OUTLINE, ensure_ascii=False)
        if "小テスト" in system_prompt:
            return json.dumps(QUIZ, ensure_ascii=False)
        return json.dumps(UNIT, ensure_ascii=False).replace("\\\\n", "\\n")


@pytest.fixture()
def admin(seeded):
    from app.main import app

    c = TestClient(app)
    assert c.post("/api/auth/login", json={"login_name": "admin", "password": "pw-admin"}).status_code == 200
    return c


REQUEST = {"title": "時系列分析入門", "topic": "移動平均と予測の評価", "level": "intermediate", "unit_count": 2}


def test_ai_unavailable_without_settings(admin, monkeypatch):
    # 接続情報が無い場合は 503 で理由を返す
    from app.config.settings import get_settings

    monkeypatch.setattr(get_settings(), "azure_openai_endpoint", "")
    assert admin.get("/api/admin/ai/status").json()["enabled"] is False
    res = admin.post("/api/admin/ai/outline", json=REQUEST)
    assert res.status_code == 503 and "接続情報" in res.json()["detail"]


def test_outline_retries_broken_output(admin):
    # 形式の崩れた応答は、誤りを伝えて1回だけ再試行する
    fake = FakeAI(broken_first=True)
    set_ai_client(fake)
    res = admin.post("/api/admin/ai/outline", json=REQUEST)
    assert res.status_code == 200 and res.json()["title"] == "時系列分析入門"
    assert len(fake.calls) == 2
    # 呼び出しはすべて記録される(失敗 1 件 + 成功 1 件、プロンプトの版番号つき)
    with db.new_session() as s:
        logs = s.scalars(select(AIGeneration).order_by(AIGeneration.id)).all()
        assert [(g.purpose, g.success) for g in logs] == [("outline", False), ("outline", True)]
        assert logs[1].prompt_version == "v1" and "前回の出力の誤り" in logs[1].user_prompt


def test_draft_job_creates_unverified_course(admin):
    set_ai_client(FakeAI())
    # 構成案から下書きを作成(バックグラウンド処理はテストでは応答の前に完了する)
    job = admin.post("/api/admin/ai/drafts", json={"slug": "time-series", "request": REQUEST, "outline": OUTLINE}).json()
    job = admin.get(f"/api/admin/ai/jobs/{job['id']}").json()
    assert job["status"] == "done" and job["done_steps"] == job["total_steps"] == 3
    editor = admin.get(f"/api/admin/courses/{job['course_id']}").json()
    assert editor["status"] == "draft" and editor["level"] == "intermediate"
    assert [u["title"] for u in editor["units"]] == ["移動平均", "予測の評価"]
    # セルは AI 生成の印つき。演習は AI の模範解答だけがあり、作成者の解答は空で未検証
    cells = editor["units"][0]["cells"]
    assert [c["cell_type"] for c in cells] == ["markdown", "code", "exercise"]
    assert all(c["ai_generated"] for c in cells)
    problem = cells[2]["problem"]
    assert problem["ai_model_answer"] and problem["author_answer"] == "" and problem["verify_status"] == "todo"
    # 小テストもすべて未検証(関連単元つき)
    assert [q["verify_status"] for q in editor["quiz"]] == ["todo", "todo", "todo"]
    assert editor["quiz"][2]["related_unit_id"] == editor["units"][1]["id"]
    # 選択式は作成者が確認すると検証済みになる(コード問題は確認ボタンでは検証できない)
    assert admin.post(f"/api/admin/problems/{editor['quiz'][0]['id']}/confirm").json()["verify_status"] == "verified"
    assert admin.post(f"/api/admin/problems/{editor['quiz'][2]['id']}/confirm").status_code == 400
    # 公開前チェックでは未検証の問題が残っている
    check = admin.get(f"/api/admin/courses/{job['course_id']}/publish-check").json()
    assert check["publishable"] is False


def test_draft_job_failure_and_resume(admin):
    # 単元の生成で形式が直らない場合も、ほかの手順は続けて失敗内容を残し、ジョブは「失敗」になる
    class HalfBroken(FakeAI):
        def complete_json(self, system_prompt, user_prompt, model):
            if "単元の教材" in system_prompt:
                return "{}"
            return super().complete_json(system_prompt, user_prompt, model)

    set_ai_client(HalfBroken())
    job = admin.post("/api/admin/ai/drafts", json={"slug": "broken", "request": REQUEST, "outline": OUTLINE}).json()
    job = admin.get(f"/api/admin/ai/jobs/{job['id']}").json()
    assert job["status"] == "failed" and job["done_steps"] == 1
    assert "単元1" in job["message"] and "単元2" in job["message"]
    editor = admin.get(f"/api/admin/courses/{job['course_id']}").json()
    assert len(editor["quiz"]) == 3 and editor["units"][0]["cells"] == []
    # 再開すると、中身の無い単元だけを作る(小テストは作り直さない)
    fake = FakeAI()
    set_ai_client(fake)
    job = admin.post(f"/api/admin/ai/jobs/{job['id']}/resume").json()
    job = admin.get(f"/api/admin/ai/jobs/{job['id']}").json()
    assert job["status"] == "done" and job["done_steps"] == 3 and job["message"] == ""
    assert len(fake.calls) == 2 and all("単元の教材" in c[0] for c in fake.calls)
    editor = admin.get(f"/api/admin/courses/{job['course_id']}").json()
    assert all(u["cells"] for u in editor["units"]) and len(editor["quiz"]) == 3
    # 完了したジョブは再開できない
    assert admin.post(f"/api/admin/ai/jobs/{job['id']}/resume").status_code == 400


def test_interrupted_jobs_marked_on_startup(admin):
    # 実行中のまま残ったジョブは、起動時に「中断(失敗)」になり、再開できる
    from app.services.ai_course_service import mark_interrupted_jobs

    with db.new_session() as s:
        s.add(AIJob(course_id=None, status="running", total_steps=2, request={}))
        s.commit()
    assert mark_interrupted_jobs() == 1
    with db.new_session() as s:
        job = s.scalars(select(AIJob)).one()
        assert job.status == "failed" and "中断" in job.message


def test_draft_rejects_duplicate_slug(admin):
    set_ai_client(FakeAI())
    res = admin.post("/api/admin/ai/drafts", json={"slug": "statistics-basics", "request": REQUEST, "outline": OUTLINE})
    assert res.status_code == 400
