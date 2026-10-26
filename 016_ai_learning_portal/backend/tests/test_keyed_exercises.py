"""選択式・数値入力・表形式の選択の演習(単元内)と、表形式の採点・取り込みのテスト。"""

import json
from pathlib import Path

import nbformat
import pytest
from fastapi.testclient import TestClient

from app.common.constants import AnswerFormat, CellType
from app.models import Problem
from app.services.answer_check import answer_key_error, grade_answer
from app.services.notebook_import import NotebookFormatError, parse_notebook

_MATRIX_PROMPT = """<!-- @question
type: matrix
answer: 名義, 離散, 順序
title: 変数の種類
hint: 平均に意味があるかで考えます。
explanation: 満足度は順序尺度です。
-->
各列の種類を選んでください。

| 列 | 名義 | 順序 | 離散 | 連続 |
|---|---|---|---|---|
| `region`(地域) | | | | |
| `members`(世帯人数) | | | | |
| `satisfaction`(満足度) | | | | |
"""


@pytest.fixture()
def admin(seeded):
    """管理者でログイン済みのクライアント。"""
    from app.main import app

    c = TestClient(app)
    assert c.post("/api/auth/login", json={"login_name": "admin", "password": "pw-admin"}).status_code == 200
    return c


def _write_nb(tmp_path: Path, cells) -> Path:
    """テスト用のノートブックを書き出す。"""
    nb = nbformat.v4.new_notebook()
    nb.cells = cells
    path = tmp_path / "unit.ipynb"
    nbformat.write(nb, str(path))
    return path


def _matrix(rows: list[str], choices: list[str], answers: list[str]) -> Problem:
    """採点テスト用の表形式の問題。"""
    return Problem(
        answer_format=AnswerFormat.MATRIX,
        choices=choices,
        matrix_rows=rows,
        correct_answer=json.dumps(answers, ensure_ascii=False),
        tolerance=1e-6,
    )


def test_grade_matrix():
    p = _matrix(["a", "b", "c"], ["名義", "順序"], ["名義", "順序", "名義"])
    # すべての行が一致すれば正解
    assert grade_answer(p, json.dumps(["名義", "順序", "名義"]))[0] is True
    # 1行違えば不正解(正解した行の数を伝える)
    ok, answered, message = grade_answer(p, json.dumps(["名義", "名義", "名義"]))
    assert (ok, answered) == (False, True) and "3 行中 2 行" in message
    # 未選択の行があれば不正解、すべて未選択なら未回答
    assert grade_answer(p, json.dumps(["名義", "", "名義"]))[:2] == (False, True)
    assert grade_answer(p, json.dumps(["", "", ""]))[:2] == (False, False)
    # 形式の誤り(行の数が違う・JSON でない)は不正解
    assert grade_answer(p, json.dumps(["名義"]))[0] is False
    assert grade_answer(p, "名義")[0] is False


def test_answer_key_error_for_matrix():
    rows, choices = ["a", "b"], ["x", "y"]
    assert answer_key_error("matrix", choices, rows, json.dumps(["x", "y"])) is None
    assert answer_key_error("matrix", choices, rows, json.dumps(["x", ""])) is not None
    assert answer_key_error("matrix", choices, rows, json.dumps(["x", "z"])) is not None
    assert answer_key_error("matrix", ["x"], rows, json.dumps(["x", "x"])) is not None
    assert answer_key_error("matrix", choices, [], "[]") is not None


def test_parse_unit_with_matrix_exercise(tmp_path):
    path = _write_nb(
        tmp_path,
        [nbformat.v4.new_markdown_cell("# タイトル\n概要"), nbformat.v4.new_markdown_cell(_MATRIX_PROMPT)],
    )
    unit = parse_notebook(path)
    kind, _, q = unit.cells[0]
    assert kind == CellType.EXERCISE
    assert q.answer_format == AnswerFormat.MATRIX
    assert q.choices == ["名義", "順序", "離散", "連続"]
    assert q.matrix_rows == ["`region`(地域)", "`members`(世帯人数)", "`satisfaction`(満足度)"]
    assert json.loads(q.correct_answer) == ["名義", "離散", "順序"]
    # 問題文には表を含めない(表は回答欄として表示する)
    assert q.prompt == "各列の種類を選んでください。"
    assert (q.title, q.hint, q.explanation) == ("変数の種類", "平均に意味があるかで考えます。", "満足度は順序尺度です。")


def test_parse_matrix_answer_errors(tmp_path):
    # answer の数が行の数と違う
    bad = _MATRIX_PROMPT.replace("answer: 名義, 離散, 順序", "answer: 名義, 離散")
    path = _write_nb(tmp_path, [nbformat.v4.new_markdown_cell("# タイトル"), nbformat.v4.new_markdown_cell(bad)])
    with pytest.raises(NotebookFormatError, match="行の数"):
        parse_notebook(path)
    # answer に選択肢に無い値がある
    bad = _MATRIX_PROMPT.replace("answer: 名義, 離散, 順序", "answer: 名義, 離散, 比例")
    path = _write_nb(tmp_path, [nbformat.v4.new_markdown_cell("# タイトル"), nbformat.v4.new_markdown_cell(bad)])
    with pytest.raises(NotebookFormatError, match="比例"):
        parse_notebook(path)


def test_parse_unit_with_choice_exercise(tmp_path):
    source = "<!-- @question\ntype: choice\nanswer: 中央値\n-->\n外れ値に強いのは?\n\n- 平均\n- 中央値"
    path = _write_nb(tmp_path, [nbformat.v4.new_markdown_cell("# タイトル"), nbformat.v4.new_markdown_cell(source)])
    _, _, q = parse_notebook(path).cells[0]
    assert (q.answer_format, q.choices, q.correct_answer) == (AnswerFormat.CHOICE, ["平均", "中央値"], "中央値")


def _keyed_cells() -> list[dict]:
    """選択式と表形式の演習を1問ずつ持つ単元のセル。"""
    return [
        {
            "cell_type": "exercise",
            "problem": {
                "answer_format": "choice",
                "title": "代表値",
                "prompt": "外れ値に強いのは?",
                "choices": ["平均", "中央値"],
                "correct_answer": "中央値",
            },
        },
        {
            "cell_type": "exercise",
            "problem": {
                "answer_format": "matrix",
                "title": "分類",
                "prompt": "分類してください",
                "choices": ["質的", "量的"],
                "matrix_rows": ["地域", "年収"],
                "correct_answer": json.dumps(["質的", "量的"], ensure_ascii=False),
            },
        },
    ]


def test_keyed_exercises_complete_unit(client, admin):
    # 管理者が、選択式と表形式の演習だけの単元を持つ講座を作って公開する
    editor = admin.post(
        "/api/authoring/courses", json={"slug": "keyed", "title": "選択式の講座", "summary": "概要", "level": "basic"}
    ).json()
    cid, uid = editor["id"], editor["units"][0]["id"]
    unit = admin.put(f"/api/authoring/units/{uid}", json={"title": "単元", "cells": _keyed_cells()}).json()
    choice_p, matrix_p = (c["problem"] for c in unit["cells"])
    # 正解が正しく設定されていれば、保存した時点で検証済み
    assert choice_p["verify_status"] == "verified" and matrix_p["verify_status"] == "verified"
    assert matrix_p["matrix_rows"] == ["地域", "年収"]
    quiz = [{"answer_format": "numeric", "prompt": "1+1", "correct_answer": "2"}]
    assert admin.put(f"/api/authoring/courses/{cid}/quiz", json={"questions": quiz}).status_code == 200
    assert admin.post(f"/api/authoring/courses/{cid}/publish", json={"examples_ok": True}).status_code == 200

    # 受講者には回答形式・選択肢・行が渡り、正解は渡らない
    learner_unit = client.get(f"/api/units/{uid}").json()
    ex = learner_unit["cells"][1]["exercise"]
    assert ex["answer_format"] == "matrix" and ex["choices"] == ["質的", "量的"] and ex["matrix_rows"] == ["地域", "年収"]
    assert "correct_answer" not in ex

    # 表形式: 1行違えば不正解、すべて合えば正解
    wrong = client.post(f"/api/problems/{matrix_p['id']}/submit-answer", json={"answer": '["質的", "質的"]'}).json()
    assert wrong["passed"] is False and "2 行中 1 行" in wrong["message"]
    ok = client.post(f"/api/problems/{matrix_p['id']}/submit-answer", json={"answer": '["質的", "量的"]'}).json()
    assert ok["passed"] is True and ok["unit_completed"] is False
    # 選択式も正解すると、単元が完了する
    done = client.post(f"/api/problems/{choice_p['id']}/submit-answer", json={"answer": "中央値"}).json()
    assert done["passed"] is True and done["unit_newly_completed"] is True
    # 最後の回答が単元画面に残る
    again = client.get(f"/api/units/{uid}").json()
    assert again["completed"] is True and again["cells"][1]["exercise"]["last_answer"] == '["質的", "量的"]'


def test_submit_answer_rejects_quiz_and_code(client, admin):
    # 小テストの問題は1問ずつ採点できない(正解を探れないようにする)
    quiz_id = admin.get("/api/authoring/courses").json()[0]["id"]
    editor = admin.get(f"/api/authoring/courses/{quiz_id}").json()
    quiz_choice = next(p for p in editor["quiz"] if p["answer_format"] == "choice")
    assert client.post(f"/api/problems/{quiz_choice['id']}/submit-answer", json={"answer": "x"}).status_code == 404
    # コード問題は submit-answer では採点しない
    code_pid = editor["units"][0]["cells"]
    code_pid = next(c["problem"]["id"] for c in code_pid if c["problem"])
    assert client.post(f"/api/problems/{code_pid}/submit-answer", json={"answer": "x"}).status_code == 404


def test_invalid_matrix_key_stays_todo(admin):
    editor = admin.post(
        "/api/authoring/courses", json={"slug": "keyed2", "title": "表形式", "summary": "概要", "level": "basic"}
    ).json()
    cells = _keyed_cells()[1:]
    cells[0]["problem"]["correct_answer"] = json.dumps(["質的", ""], ensure_ascii=False)
    unit = admin.put(f"/api/authoring/units/{editor['units'][0]['id']}", json={"title": "単元", "cells": cells}).json()
    p = unit["cells"][0]["problem"]
    # 正解が未設定の行があると未検証のまま。内容の確認もできない
    assert p["verify_status"] == "todo"
    res = admin.post(f"/api/authoring/problems/{p['id']}/confirm")
    assert res.status_code == 400 and "すべての行" in res.json()["detail"]
