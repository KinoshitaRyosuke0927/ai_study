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
        if "構成案を作ります" in system_prompt:
            return json.dumps(OUTLINE, ensure_ascii=False)
        if "小テストを作ります" in system_prompt:
            return json.dumps(QUIZ, ensure_ascii=False)
        return json.dumps(UNIT, ensure_ascii=False).replace("\\\\n", "\\n")


# 概念理解型の講座の単元と小テスト(コードを使わず、選択式・数値入力・表形式で出題する)
CONCEPT_UNIT = {
    "cells": [
        {"type": "markdown", "source": "## 学習目標\n- 平均を計算できる"},
        {"type": "markdown", "source": "## 平均\n値の合計を個数で割ったもの。"},
        {
            "type": "exercise",
            "exercise": {
                "type": "numeric",
                "title": "平均",
                "prompt": "2, 4, 9 の平均を求めよ。",
                "answer": "5",
                "tolerance": 0.001,
                "check_code": "print((2 + 4 + 9) / 3)",
            },
        },
        {
            "type": "exercise",
            "exercise": {
                "type": "matrix",
                "title": "変数の種類",
                "prompt": "次の変数の種類を選べ。",
                "choices": ["量的変数", "質的変数"],
                "matrix_rows": ["身長", "血液型"],
                "matrix_answers": ["量的変数", "質的変数"],
            },
        },
        {
            "type": "exercise",
            "exercise": {
                "type": "choice",
                "title": "外れ値",
                "prompt": "外れ値の影響を受けにくいものは?",
                "choices": ["平均", "中央値"],
                "answer": "中央値",
            },
        },
    ]
}
CONCEPT_QUIZ = {
    "questions": [
        {"type": "matrix", "prompt": "分類せよ。", "choices": ["A", "B"], "matrix_rows": ["x", "y"], "matrix_answers": ["B", "A"], "unit": 1},
        {"type": "numeric", "prompt": "1, 2, 3 の平均は?", "answer": "2", "tolerance": 0.01, "unit": 1, "check_code": "print(2)"},
    ]
}


class ConceptAI(FakeAI):
    """概念理解型の単元・小テストを返す偽の AI。"""

    def complete_json(self, system_prompt: str, user_prompt: str, model: str) -> str:
        self.calls.append((system_prompt, model))
        if "構成案を作ります" in system_prompt:
            return json.dumps({**OUTLINE, "units": OUTLINE["units"][:1], "libraries": []}, ensure_ascii=False)
        if "小テストを作ります" in system_prompt:
            return json.dumps(CONCEPT_QUIZ, ensure_ascii=False)
        return json.dumps(CONCEPT_UNIT, ensure_ascii=False)


@pytest.fixture()
def admin(seeded):
    from app.main import app

    c = TestClient(app)
    assert c.post("/api/auth/login", json={"login_name": "admin", "password": "pw-admin"}).status_code == 200
    return c


def _post_draft(client, body: dict, files: list | None = None):
    """下書きの作成を要求する(マルチパート: payload に JSON、files にデータファイル)"""
    return client.post("/api/authoring/ai/drafts", data={"payload": json.dumps(body, ensure_ascii=False)}, files=files or [])


REQUEST = {"title": "時系列分析入門", "topic": "移動平均と予測の評価", "level": "intermediate", "unit_count": 2}


def test_ai_unavailable_without_settings(admin, monkeypatch):
    # 接続情報が無い場合は 503 で理由を返す
    from app.config.settings import get_settings

    monkeypatch.setattr(get_settings(), "azure_openai_endpoint", "")
    assert admin.get("/api/authoring/ai/status").json()["enabled"] is False
    res = admin.post("/api/authoring/ai/outline", json=REQUEST)
    assert res.status_code == 503 and "接続情報" in res.json()["detail"]


def test_outline_retries_broken_output(admin):
    # 形式の崩れた応答は、誤りを伝えて1回だけ再試行する
    fake = FakeAI(broken_first=True)
    set_ai_client(fake)
    res = admin.post("/api/authoring/ai/outline", json=REQUEST)
    assert res.status_code == 200 and res.json()["title"] == "時系列分析入門"
    assert len(fake.calls) == 2
    # 呼び出しはすべて記録される(失敗 1 件 + 成功 1 件、プロンプトの版番号つき)
    with db.new_session() as s:
        logs = s.scalars(select(AIGeneration).order_by(AIGeneration.id)).all()
        assert [(g.purpose, g.success) for g in logs] == [("outline", False), ("outline", True)]
        assert logs[1].prompt_version == "v6" and "前回の出力の誤り" in logs[1].user_prompt


def test_draft_job_creates_unverified_course(admin):
    set_ai_client(FakeAI())
    # 構成案から下書きを作成(バックグラウンド処理はテストでは応答の前に完了する)
    job = _post_draft(admin, {"slug": "time-series", "request": REQUEST, "outline": OUTLINE}).json()
    job = admin.get(f"/api/authoring/ai/jobs/{job['id']}").json()
    assert job["status"] == "done" and job["done_steps"] == job["total_steps"] == 3
    editor = admin.get(f"/api/authoring/courses/{job['course_id']}").json()
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
    assert admin.post(f"/api/authoring/problems/{editor['quiz'][0]['id']}/confirm").json()["verify_status"] == "verified"
    assert admin.post(f"/api/authoring/problems/{editor['quiz'][2]['id']}/confirm").status_code == 400
    # 公開前チェックでは未検証の問題が残っている
    check = admin.get(f"/api/authoring/courses/{job['course_id']}/publish-check").json()
    assert check["publishable"] is False


def test_prompts_depend_on_course_type(admin):
    # 講座のタイプと目的がプロンプトに入り、タイプに合った見本の単元が添えられる
    from app.ai.prompts import outline_prompt, quiz_prompt, unit_prompt
    from app.ai.schemas import CourseOutline, OutlineRequest

    req = OutlineRequest(title="記述統計", course_type="concept", purpose="統計検定2級に合格する", topic="代表値と散らばり")
    system, user = outline_prompt(req)
    assert "概念理解型" in system and "libraries は空にする" in system and "統計検定2級に合格する" in user
    outline = CourseOutline.model_validate(OUTLINE)
    concept_system, _ = unit_prompt(outline, 0, "basic", [], "concept", "目的")
    practice_system, _ = unit_prompt(outline, 0, "basic", ["train.csv"], "practice", "目的")
    assert "code セル(例題)は使わない" in concept_system and "<!-- @question" in concept_system
    assert "# @starter" in practice_system and "コメントを付ける" in practice_system and "train.csv" in practice_system
    quiz_system, _ = quiz_prompt(outline, "basic", [], "concept")
    assert "コードの問題は出さない" in quiz_system


def test_concept_draft_saves_keyed_exercises(admin):
    # 概念理解型: 単元の演習(数値入力・表形式・選択式)と小テストの表形式が、正解と根拠のコードつきで未検証で保存される
    set_ai_client(ConceptAI())
    request = {**REQUEST, "course_type": "concept", "purpose": "概念を理解する"}
    outline = {**OUTLINE, "units": OUTLINE["units"][:1], "libraries": []}
    job = _post_draft(admin, {"slug": "concept-course", "request": request, "outline": outline}).json()
    job = admin.get(f"/api/authoring/ai/jobs/{job['id']}").json()
    assert job["status"] == "done", job["message"]
    editor = admin.get(f"/api/authoring/courses/{job['course_id']}").json()
    problems = [c["problem"] for c in editor["units"][0]["cells"] if c["problem"]]
    assert [p["answer_format"] for p in problems] == ["numeric", "matrix", "choice"]
    numeric, matrix, choice = problems
    assert numeric["correct_answer"] == "5" and numeric["tolerance"] == 0.001 and numeric["ai_model_answer"] == "print((2 + 4 + 9) / 3)"
    assert matrix["matrix_rows"] == ["身長", "血液型"] and json.loads(matrix["correct_answer"]) == ["量的変数", "質的変数"]
    assert choice["correct_answer"] == "中央値"
    assert all(p["verify_status"] == "todo" for p in problems)
    # 小テストの表形式も保存され、作成者が確認すると検証済みになる
    quiz = editor["quiz"]
    assert quiz[0]["answer_format"] == "matrix" and json.loads(quiz[0]["correct_answer"]) == ["B", "A"]
    assert admin.post(f"/api/authoring/problems/{quiz[0]['id']}/confirm").json()["verify_status"] == "verified"


def test_keyed_exercise_without_required_fields_is_retried():
    # 形式ごとに必要な項目が足りない出力は検証エラーになり、AI に再試行させる
    from pydantic import ValidationError

    from app.ai.schemas import GeneratedExercise

    with pytest.raises(ValidationError):
        GeneratedExercise.model_validate({"type": "choice", "title": "t", "prompt": "p", "choices": ["a", "b"], "answer": "c"})
    with pytest.raises(ValidationError):
        GeneratedExercise.model_validate({"type": "code", "title": "t", "prompt": "p"})
    with pytest.raises(ValidationError):
        GeneratedExercise.model_validate(
            {"type": "matrix", "title": "t", "prompt": "p", "choices": ["a", "b"], "matrix_rows": ["x", "y"], "matrix_answers": ["a"]}
        )


def test_draft_job_failure_and_resume(admin):
    # 単元の生成で形式が直らない場合も、ほかの手順は続けて失敗内容を残し、ジョブは「失敗」になる
    class HalfBroken(FakeAI):
        def complete_json(self, system_prompt, user_prompt, model):
            if "単元の教材" in system_prompt:
                return "{}"
            return super().complete_json(system_prompt, user_prompt, model)

    set_ai_client(HalfBroken())
    job = _post_draft(admin, {"slug": "broken", "request": REQUEST, "outline": OUTLINE}).json()
    job = admin.get(f"/api/authoring/ai/jobs/{job['id']}").json()
    assert job["status"] == "failed" and job["done_steps"] == 1
    assert "単元1" in job["message"] and "単元2" in job["message"]
    editor = admin.get(f"/api/authoring/courses/{job['course_id']}").json()
    assert len(editor["quiz"]) == 3 and editor["units"][0]["cells"] == []
    # 再開すると、中身の無い単元だけを作る(小テストは作り直さない)
    fake = FakeAI()
    set_ai_client(fake)
    job = admin.post(f"/api/authoring/ai/jobs/{job['id']}/resume").json()
    job = admin.get(f"/api/authoring/ai/jobs/{job['id']}").json()
    assert job["status"] == "done" and job["done_steps"] == 3 and job["message"] == ""
    assert len(fake.calls) == 2 and all("単元の教材" in c[0] for c in fake.calls)
    editor = admin.get(f"/api/authoring/courses/{job['course_id']}").json()
    assert all(u["cells"] for u in editor["units"]) and len(editor["quiz"]) == 3
    # 完了したジョブは再開できない
    assert admin.post(f"/api/authoring/ai/jobs/{job['id']}/resume").status_code == 400


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
    res = _post_draft(admin, {"slug": "statistics-basics", "request": REQUEST, "outline": OUTLINE})
    assert res.status_code == 400


# ---------- コードの実行による確認と、AI による修正 ----------

# 1×1 の PNG 画像(偽の実行環境が「描いた図」として返す)
PNG_1PX = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
# 別の色の 1×1 の PNG 画像(棒グラフの図として返す。説明の図と同じ図は問題点になるため)
PNG_1PX_BAR = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGOwrm8DAAI5AUEUneC3AAAAAElFTkSuQmCC"


class FakeRunner:
    """コードの中身に応じて決まった結果を返す、偽の実行環境。"""

    def __init__(self):
        self.calls = 0

    def run(self, tasks, files):
        from app.ai.executor import TaskResult

        self.calls += 1
        results = {}
        for t in tasks:
            if "1/0" in t.code:
                results[t.id] = TaskResult(id=t.id, error="ZeroDivisionError: division by zero")
            elif "plt." in t.code:
                results[t.id] = TaskResult(id=t.id, images=[PNG_1PX_BAR if "ax.bar" in t.code else PNG_1PX])
            elif "print(5)" in t.code:
                results[t.id] = TaskResult(id=t.id, output="5\n")
            else:
                results[t.id] = TaskResult(id=t.id, output="ok\n")
        return results


def _figure_unit(answer: str) -> dict:
    """図の説明セルと、図つきの数値入力の演習を含む単元(answer は数値入力の正解)"""
    return {
        "cells": [
            {"type": "markdown", "source": "## 学習目標\n- 図を読める"},
            {"type": "figure", "source": "fig, ax = plt.subplots()\nax.plot([1, 2])", "alt": "折れ線グラフ"},
            {
                "type": "exercise",
                "exercise": {
                    "type": "numeric",
                    "title": "棒の高さ",
                    "prompt": "図の棒の高さを答えよ。",
                    "answer": answer,
                    "check_code": "print(5)",
                    "figure_code": "fig, ax = plt.subplots()\nax.bar([0], [5])",
                    "figure_alt": "棒グラフ",
                },
            },
        ]
    }


class ReviewAI(FakeAI):
    """最初は正解を間違え、実行結果を渡されると直す偽の AI(小テストの誤りは直さない)。"""

    def complete_json(self, system_prompt, user_prompt, model):
        self.calls.append((system_prompt, model))
        if "構成案を作ります" in system_prompt:
            return json.dumps({**OUTLINE, "units": OUTLINE["units"][:1]}, ensure_ascii=False)
        quiz = {"questions": [{"type": "numeric", "prompt": "1/0 は?", "answer": "1", "check_code": "print(1/0)", "unit": 1}]}
        if "小テストを作ります" in system_prompt or "小テストの下書きを" in system_prompt:
            return json.dumps(quiz, ensure_ascii=False)
        if "単元の教材の下書きを" in system_prompt:
            # 実行結果の報告に、正解の不一致が問題点として渡されていることを確かめてから直す
            assert "一致しません" in user_prompt
            return json.dumps(_figure_unit("5"), ensure_ascii=False)
        return json.dumps(_figure_unit("6"), ensure_ascii=False)


def test_verify_detects_issues():
    # 実行結果から、数値の正解の不一致・エラー・描けない図を問題点として見つける
    from app.ai.executor import TaskResult
    from app.ai.schemas import UnitDraft
    from app.ai.verify import run_unit

    class Runner:
        def run(self, tasks, files):
            assert files == {"a.csv": b"x"}
            out = {t.id: TaskResult(id=t.id, output="5\n") for t in tasks}
            out["cell2"] = TaskResult(id="cell2", error="NameError: x")  # 図が描けない
            return out

    draft = UnitDraft.model_validate(_figure_unit("6"))
    execution = run_unit(Runner(), draft, {"a.csv": b"x"})
    assert any("セル2(図)" in i for i in execution.issues)
    assert any("一致しません" in i for i in execution.issues)
    assert "check_code の実行結果" in execution.report


def test_draft_job_verifies_and_fixes_with_runner(admin):
    # 実行環境があると、下書きを実行して AI に直させ、図を講座の画像として保存する
    from app.ai.executor import set_runner

    set_ai_client(ReviewAI())
    set_runner(FakeRunner())
    outline = {**OUTLINE, "units": OUTLINE["units"][:1]}
    job = _post_draft(admin, {"slug": "verified", "request": REQUEST, "outline": outline}).json()
    job = admin.get(f"/api/authoring/ai/jobs/{job['id']}").json()
    assert job["status"] == "done"
    # 直せなかった小テストの問題点は「要確認」として残る(単元は直ったので残らない)
    assert "小テスト: 要確認" in job["message"] and "単元1" not in job["message"]
    editor = admin.get(f"/api/authoring/courses/{job['course_id']}").json()
    cells = editor["units"][0]["cells"]
    # 図は画像として保存され、説明セルと問題文に画像の参照が入る
    assert cells[1]["cell_type"] == "markdown" and cells[1]["source"] == "![折れ線グラフ](image:u01_fig2.png)"
    problem = cells[2]["problem"]
    assert "![棒グラフ](image:u01_ex1.png)" in problem["prompt"]
    # 正解は、実行結果を渡された AI が直した値になる
    assert problem["correct_answer"] == "5"
    assert {i["filename"] for i in editor["images"]} == {"u01_fig2.png", "u01_ex1.png"}
    # 直すための呼び出しも記録される
    with db.new_session() as s:
        purposes = [g.purpose for g in s.scalars(select(AIGeneration).order_by(AIGeneration.id))]
    assert purposes.count("unit_review") == 1 and purposes.count("quiz_review") == 2


def test_draft_with_datasets_and_summary(admin):
    # データファイルの要約を作れる(実行環境が無ければファイル名だけ)。下書きと一緒に送ると講座のデータファイルになる
    from app.ai.executor import TaskResult, set_runner

    class SummaryRunner:
        def run(self, tasks, files):
            assert list(files) == ["sales.csv"] and b"date" in files["sales.csv"]
            return {t.id: TaskResult(id=t.id, output="### sales.csv\n行数 2、列数 2\n") for t in tasks}

    csv = ("sales.csv", b"date,amount\n2024-01-01,10\n2024-01-02,12\n", "text/csv")
    assert admin.post("/api/authoring/ai/datasets/summary", files=[("files", csv)]).json()["summary"] == "### sales.csv"
    set_runner(SummaryRunner())
    summary = admin.post("/api/authoring/ai/datasets/summary", files=[("files", csv)]).json()["summary"]
    assert "行数 2" in summary
    set_runner(None)
    # 要約は依頼に含めてプロンプトに渡し、ファイルは講座のデータファイルとして登録される
    fake = FakeAI()
    set_ai_client(fake)
    request = {**REQUEST, "data_summary": summary}
    job = _post_draft(admin, {"slug": "with-data", "request": request, "outline": OUTLINE}, files=[("files", csv)]).json()
    job = admin.get(f"/api/authoring/ai/jobs/{job['id']}").json()
    assert job["status"] == "done"
    editor = admin.get(f"/api/authoring/courses/{job['course_id']}").json()
    assert [d["filename"] for d in editor["datasets"]] == ["sales.csv"]
    assert all("行数 2" in system for system, _ in fake.calls)


def test_verify_detects_same_figure_in_exercise():
    # 演習の図が説明の図とまったく同じなら、問題点にする(説明から答えが読めてしまうため)
    from app.ai.executor import TaskResult
    from app.ai.schemas import UnitDraft
    from app.ai.verify import run_unit

    class SameImageRunner:
        def run(self, tasks, files):
            return {t.id: TaskResult(id=t.id, output="5\n", images=[PNG_1PX]) for t in tasks}

    execution = run_unit(SameImageRunner(), UnitDraft.model_validate(_figure_unit("5")), {})
    assert execution.issues == ["演習1: 問題文の図が説明の図とまったく同じです。説明から答えが読めないよう、別のデータで図を描いてください"]


def test_stray_image_reference_is_issue_and_removed():
    # 本文に直接書かれた画像の参照(表示できない)は問題点にし、保存するときには取り除く
    from app.ai.schemas import UnitDraft
    from app.ai.verify import run_unit, strip_stray_images

    unit = _figure_unit("5")
    unit["cells"][0]["source"] += "\n\n![分布の形](figure)\n\n本文"
    execution = run_unit(FakeRunner(), UnitDraft.model_validate(unit), {})
    assert len(execution.issues) == 1 and "セル1(説明)" in execution.issues[0] and "](figure)" in execution.issues[0]
    # 保存した図の参照(image:)は残し、それ以外の参照だけ取り除く
    assert strip_stray_images("前\n\n![a](figure)\n\n後 ![b](image:u01_fig2.png)") == "前\n\n後 ![b](image:u01_fig2.png)"


def test_verify_detects_unstated_values_and_repeated_code():
    # コードの演習で、模範解答の値(区間の境界・区間名)が問題文などに無ければ問題点にする。同じコードを繰り返す例題も問題点にする
    from app.ai.schemas import UnitDraft
    from app.ai.verify import run_unit

    load = 'import pandas as pd\ndf = pd.read_csv("a.csv")'
    exercise = {
        "type": "code",
        "title": "区間別の件数",
        "prompt": "x を指定された区間に分けて、区間ごとの件数を表示してください。",
        "starter_code": f"{load}\nprint(pd.cut(df['x'], bins=____, labels=____).value_counts())",
        "model_answer": f"{load}\nprint(pd.cut(df['x'], bins=[0, 15, 50], labels=['low', 'high']).value_counts())",
    }
    unit = {"cells": [{"type": "code", "source": load}, {"type": "code", "source": f"{load}\nprint(df.shape)"}, {"type": "exercise", "exercise": exercise}]}
    issues = run_unit(FakeRunner(), UnitDraft.model_validate(unit), {}).issues
    assert any("セル2(例題): セル1と同じコード" in i for i in issues)
    assert any("15, 50, 'low', 'high'" in i for i in issues)
    # 値を問題文に書けば問題点にならない(見た目だけの引数は調べない)
    exercise["prompt"] = "x を 0〜15(low)・15〜50(high)の区間に分けて、件数を表示してください。"
    exercise["model_answer"] += "\ndf.plot(figsize=(6, 3))"
    unit["cells"] = unit["cells"][1:]
    assert run_unit(FakeRunner(), UnitDraft.model_validate(unit), {}).issues == []
