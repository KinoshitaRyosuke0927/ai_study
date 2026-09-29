"""受講 API を通しで確認するテスト。"""

from fastapi.testclient import TestClient

from app.common.constants import CellType


def _unit(client: TestClient, position: int) -> dict:
    """講座の n 番目の単元の表示内容を取得する。"""
    course = client.get("/api/courses/statistics-basics").json()
    unit_id = next(u["id"] for u in course["units"] if u["position"] == position)
    return client.get(f"/api/units/{unit_id}").json()


def test_login_required(seeded):
    # 未ログインでは講座一覧を取得できない
    from app.main import app

    assert TestClient(app).get("/api/courses").status_code == 401


def test_wrong_password(seeded):
    # パスワード誤りはログインできない
    from app.main import app

    res = TestClient(app).post("/api/auth/login", json={"login_name": "learner", "password": "x"})
    assert res.status_code == 401


def test_course_list_and_detail(client):
    # 講座一覧にサンプル講座が表示される
    courses = client.get("/api/courses").json()
    assert [c["slug"] for c in courses] == ["statistics-basics"]
    assert courses[0]["unit_count"] == 5
    assert courses[0]["exercise_count"] == 6
    # 講座詳細に単元とデータファイルが含まれる
    detail = client.get("/api/courses/statistics-basics").json()
    assert [u["position"] for u in detail["units"]] == [1, 2, 3, 4, 5]
    assert detail["datasets"][0]["filename"] == "scores.csv"


def test_unit_hides_answers(client):
    # 単元の演習には想定出力・解答が含まれない
    unit = _unit(client, 3)
    ex = next(c["exercise"] for c in unit["cells"] if c["cell_type"] == CellType.EXERCISE)
    assert "expected_output" not in ex and "author_answer" not in ex
    assert "____" in ex["starter_code"]
    # 出力一致の問題にはテストコードを渡さない
    assert ex["test_code"] == ""


def test_submit_and_complete_unit(client):
    # 単元3の演習を取得
    unit = _unit(client, 3)
    ex = next(c["exercise"] for c in unit["cells"] if c["cell_type"] == CellType.EXERCISE)
    url = f"/api/problems/{ex['problem_id']}/submit-code"
    # 不正解の出力を提出
    res = client.post(url, json={"code": "...", "output": "平均: 76.00\n中央値: 75.0"}).json()
    assert res["passed"] is False and res["unit_completed"] is False
    # 実行エラーは不正解
    res = client.post(url, json={"code": "...", "output": "", "error": "NameError"}).json()
    assert res["passed"] is False
    # 正解の出力を提出すると単元が完了する
    res = client.post(url, json={"code": "ok", "output": "平均: 100.89\n中央値: 75.0\n"}).json()
    assert res["passed"] is True and res["unit_newly_completed"] is True
    # 単元・講座の進捗に反映される
    assert _unit(client, 3)["completed"] is True
    course = client.get("/api/courses/statistics-basics").json()
    assert course["completed_unit_count"] == 1
    assert course["next_unit_id"] == course["units"][0]["id"]


def test_test_graded_exercise(client):
    # 単元4は演習2問(出力一致・テストコード)
    unit = _unit(client, 4)
    exs = [c["exercise"] for c in unit["cells"] if c["cell_type"] == CellType.EXERCISE]
    assert "assert" in exs[1]["test_code"]
    # 1問目だけ正解しても単元は完了しない
    res = client.post(
        f"/api/problems/{exs[0]['problem_id']}/submit-code", json={"code": "", "output": "12.43"}
    ).json()
    assert res["passed"] is True and res["unit_completed"] is False
    # テストコードに合格すると単元が完了する
    res = client.post(
        f"/api/problems/{exs[1]['problem_id']}/submit-code",
        json={"code": "", "output": "", "test_passed": True},
    ).json()
    assert res["passed"] is True and res["unit_newly_completed"] is True


def test_draft_course_hidden_from_learner(client, engine):
    # 講座を下書きに戻すと受講者からは見えない
    from app.infra import db
    from app.models import Course

    with db.new_session() as session:
        session.query(Course).update({Course.status: "draft"})
        session.commit()
    assert client.get("/api/courses").json() == []
    assert client.get("/api/courses/statistics-basics").status_code == 404
