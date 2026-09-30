"""小テスト・修了判定・ホーム/マイページのテスト。"""

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.common.constants import AnswerFormat, ProblemKind
from app.infra import db
from app.models import Problem

QUIZ_URL = "/api/courses/statistics-basics/quiz"


def _complete_all_units(client: TestClient) -> None:
    """DB の想定出力を使って、全単元の演習に正解する。"""
    with db.new_session() as session:
        exercises = session.scalars(select(Problem).where(Problem.kind == ProblemKind.EXERCISE)).all()
        payloads = [(p.id, p.expected_output, p.grading) for p in exercises]
    for pid, expected, grading in payloads:
        body = {"code": "", "output": expected, "test_passed": True if grading == "test" else None}
        assert client.post(f"/api/problems/{pid}/submit-code", json=body).json()["passed"]


def _perfect_answers() -> list[dict]:
    """DB の正解から満点の回答を作る。"""
    with db.new_session() as session:
        problems = session.scalars(select(Problem).where(Problem.kind == ProblemKind.QUIZ)).all()
        answers = []
        for p in problems:
            if p.answer_format == AnswerFormat.CODE:
                answers.append({"problem_id": p.id, "answer": "code", "output": p.expected_output})
            else:
                answers.append({"problem_id": p.id, "answer": p.correct_answer})
    return answers


def test_quiz_locked_until_all_units_done(client):
    # 単元が未完了のうちは問題が表示されない
    quiz = client.get(QUIZ_URL).json()
    assert quiz["unlocked"] is False
    assert quiz["questions"] == []
    assert len(quiz["remaining_units"]) == 5
    # 提出も拒否される
    assert client.post(f"{QUIZ_URL}/attempts", json={"answers": []}).status_code == 403


def test_quiz_questions_hide_answers(client):
    _complete_all_units(client)
    quiz = client.get(QUIZ_URL).json()
    assert quiz["unlocked"] is True
    # 10問(選択式5・数値2・コード3)が出題される
    formats = [q["answer_format"] for q in quiz["questions"]]
    assert len(formats) == 10
    assert formats.count("choice") == 5 and formats.count("numeric") == 2 and formats.count("code") == 3
    # 正解・想定出力は含まれない
    for q in quiz["questions"]:
        assert "correct_answer" not in q and "expected_output" not in q
        assert q["related_unit"] is not None


def test_quiz_attempts_and_completion(client):
    _complete_all_units(client)
    answers = _perfect_answers()
    # 1問間違え(選択式を別の選択肢に)、1問未回答にして提出
    quiz = client.get(QUIZ_URL).json()
    choice_q = next(q for q in quiz["questions"] if q["answer_format"] == "choice")
    wrong = [dict(a) for a in answers]
    for a in wrong:
        if a["problem_id"] == choice_q["problem_id"]:
            a["answer"] = next(c for c in choice_q["choices"] if c != a["answer"])
    wrong = wrong[:-1]
    res = client.post(f"{QUIZ_URL}/attempts", json={"answers": wrong}).json()
    assert res["attempt"]["score"] == 8 and res["perfect"] is False
    missed = [r for r in res["results"] if not r["correct"]]
    assert {r["answered"] for r in missed} == {True, False}
    # 不正解の問題には解説を付けず、復習用の単元を付ける
    assert all(r["explanation"] == "" and r["related_unit"] for r in missed)
    assert client.get("/api/courses/statistics-basics").json()["completed"] is False
    # 数値は全角・小数表記でも受け付ける。満点で修了になる
    for a in answers:
        if a["answer"] == "5":
            a["answer"] = "５"
        elif a["answer"] == "4":
            a["answer"] = "4.0"
    res = client.post(f"{QUIZ_URL}/attempts", json={"answers": answers}).json()
    assert res["perfect"] is True and res["course_newly_completed"] is True
    # 修了後も再受験でき、修了のまま
    res = client.post(f"{QUIZ_URL}/attempts", json={"answers": wrong}).json()
    assert res["course_newly_completed"] is False
    course = client.get("/api/courses/statistics-basics").json()
    assert course["completed"] is True and course["best_quiz_score"] == 10
    assert len(client.get(QUIZ_URL).json()["attempts"]) == 3


def test_home_and_my_page(client):
    # 何もしていない状態
    home = client.get("/api/home").json()
    assert home["continue_course"] is None and home["in_progress_count"] == 0
    assert home["roadmap"]["basic"][0]["state"] == "not_started"
    assert home["new_courses"][0]["slug"] == "statistics-basics"
    # 全単元を完了すると受講中になる
    _complete_all_units(client)
    home = client.get("/api/home").json()
    assert home["continue_course"]["slug"] == "statistics-basics"
    assert home["solved_exercise_count"] == 6
    # 満点で修了すると修了講座に移る
    client.post(f"{QUIZ_URL}/attempts", json={"answers": _perfect_answers()})
    me = client.get("/api/me/summary").json()
    assert me["completed_course_count"] == 1 and me["in_progress_count"] == 0
    assert me["quiz_attempt_count"] == 1
    assert me["quiz_history"][0]["score"] == 10
    texts = [a["text"] for a in me["activities"]]
    assert any("修了" in t for t in texts) and any("小テスト" in t for t in texts)
