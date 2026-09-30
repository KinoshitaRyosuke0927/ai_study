"""管理者向け API のテスト。"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def admin(seeded):
    """管理者でログイン済みのクライアント。"""
    from app.main import app

    c = TestClient(app)
    assert c.post("/api/auth/login", json={"login_name": "admin", "password": "pw-admin"}).status_code == 200
    return c


def _exercise_cell(prompt="問題文", starter="x = ____\nprint(x)", answer="x = 42\nprint(x)", pid=None, ai=""):
    return {
        "cell_type": "exercise",
        "source": "",
        "problem": {
            "id": pid,
            "title": "答えを表示",
            "prompt": prompt,
            "starter_code": starter,
            "author_answer": answer,
            "ai_model_answer": ai,
            "grading": "output",
        },
    }


def test_admin_api_requires_admin(client):
    # 受講者は管理者 API を使えない
    assert client.get("/api/admin/courses").status_code == 403


def test_create_edit_verify_publish(admin):
    # 白紙から講座を作成(単元1つ付き、下書き)
    info = {"slug": "new-course", "title": "新しい講座", "summary": "", "level": "basic"}
    editor = admin.post("/api/admin/courses", json=info).json()
    assert editor["status"] == "draft" and len(editor["units"]) == 1
    cid, uid = editor["id"], editor["units"][0]["id"]
    # 識別名の重複はエラー
    dup = admin.post("/api/admin/courses", json={**info, "slug": "statistics-basics"})
    assert dup.status_code == 400 and "使われています" in dup.json()["detail"]
    # 公開前チェック:概要・演習・小テストが足りない
    check = admin.get(f"/api/admin/courses/{cid}/publish-check").json()
    assert check["publishable"] is False
    assert {c["key"]: c["ok"] for c in check["checks"]} == {"info": False, "units": False, "exercises": True, "quiz": False}
    # 単元にセル(説明・例題・演習)を保存
    unit = admin.put(
        f"/api/admin/units/{uid}",
        json={
            "title": "はじめての演習",
            "goals": ["答えを表示できる", ""],
            "estimated_minutes": 10,
            "cells": [
                {"cell_type": "markdown", "source": "## 説明"},
                {"cell_type": "code", "source": "print(1)"},
                _exercise_cell(),
            ],
        },
    ).json()
    assert [c["cell_type"] for c in unit["cells"]] == ["markdown", "code", "exercise"]
    assert unit["goals"] == ["答えを表示できる"]
    problem = unit["cells"][2]["problem"]
    assert problem["verify_status"] == "todo"
    # 作成者の解答の実行結果で検証(AI の模範解答なし → 作成者の出力が想定出力になる)
    res = admin.post(f"/api/admin/problems/{problem['id']}/verify", json={"author": {"output": "42\n"}}).json()
    assert res["verify_status"] == "verified" and res["expected_output"] == "42\n"
    # 実行エラーでは検証できない
    err = admin.post(f"/api/admin/problems/{problem['id']}/verify", json={"author": {"output": "", "error": "NameError"}})
    assert err.status_code == 400
    # 小テスト(選択式・数値は保存時に検証済み)と講座情報を保存
    quiz = admin.put(
        f"/api/admin/courses/{cid}/quiz",
        json={
            "questions": [
                {"answer_format": "choice", "prompt": "正しいのは?", "choices": ["A", "B"], "correct_answer": "B", "related_unit_id": uid},
                {"answer_format": "numeric", "prompt": "1+1", "correct_answer": "2"},
            ]
        },
    ).json()
    assert [q["verify_status"] for q in quiz] == ["verified", "verified"]
    admin.put(f"/api/admin/courses/{cid}", json={**info, "summary": "概要です", "tags": ["入門", " "]})
    # 例題の実行チェックが済んでいなければ公開できない
    assert admin.post(f"/api/admin/courses/{cid}/publish", json={"examples_ok": False}).status_code == 400
    published = admin.post(f"/api/admin/courses/{cid}/publish", json={"examples_ok": True}).json()
    assert published["status"] == "published"
    rows = {r["slug"]: r for r in admin.get("/api/admin/courses").json()}
    assert rows["new-course"]["problem_count"] == 3 and rows["new-course"]["verified_count"] == 3

    # 公開後に演習の初期コードを変えると、その問題だけ未検証に戻る(内容バージョンが上がる)
    unit = admin.put(
        f"/api/admin/units/{uid}",
        json={
            "title": "はじめての演習",
            "cells": [
                {"id": unit["cells"][0]["id"], "cell_type": "markdown", "source": "## 説明(改訂)"},
                _exercise_cell(starter="x = ____  # 42 を入れる\nprint(x)", pid=problem["id"]),
            ],
        },
    ).json()
    changed = unit["cells"][1]["problem"]
    assert changed["id"] == problem["id"] and changed["verify_status"] == "todo"
    assert changed["content_version"] == 2
    assert len(unit["cells"]) == 2  # 例題セルは削除された
    # ヒントだけの変更では再検証は不要
    admin.post(f"/api/admin/problems/{problem['id']}/verify", json={"author": {"output": "42"}})
    cell = _exercise_cell(starter="x = ____  # 42 を入れる\nprint(x)", pid=problem["id"])
    cell["problem"]["hint"] = "42 です"
    unit = admin.put(f"/api/admin/units/{uid}", json={"title": "はじめての演習", "cells": [cell]}).json()
    assert unit["cells"][0]["problem"]["verify_status"] == "verified"


def test_verify_with_ai_answer_mismatch(admin):
    # AI の模範解答がある演習は、作成者の出力と一致しなければ不一致になる
    editor = admin.post("/api/admin/courses", json={"slug": "ai-course", "title": "AI講座"}).json()
    uid = editor["units"][0]["id"]
    unit = admin.put(
        f"/api/admin/units/{uid}",
        json={"title": "単元", "cells": [_exercise_cell(ai="print(41)")]},
    ).json()
    pid = unit["cells"][0]["problem"]["id"]
    res = admin.post(
        f"/api/admin/problems/{pid}/verify", json={"author": {"output": "42"}, "ai": {"output": "41"}}
    ).json()
    assert res["verify_status"] == "mismatch"
    # 作成者の解答を正とすると検証済みになり、作成者の出力が想定出力になる
    res = admin.post(f"/api/admin/problems/{pid}/accept-author", json={"output": "42"}).json()
    assert res["verify_status"] == "verified" and res["expected_output"] == "42"
    # 一致する場合は AI の出力を想定出力にして検証済み
    res = admin.post(
        f"/api/admin/problems/{pid}/verify", json={"author": {"output": "42 "}, "ai": {"output": "42"}}
    ).json()
    assert res["verify_status"] == "verified"


def test_members_and_progress(admin):
    # メンバーを追加
    res = admin.post("/api/admin/users", json={"login_name": "new.member", "display_name": "新メンバー", "password": "password1"})
    assert res.status_code == 200
    uid = res.json()["id"]
    # 短すぎるパスワード・重複ログイン名はエラー
    assert admin.post("/api/admin/users", json={"login_name": "x", "display_name": "x", "password": "short"}).status_code == 422
    assert admin.post("/api/admin/users", json={"login_name": "new.member", "display_name": "x", "password": "password1"}).status_code == 400
    # パスワードを変更すると新しいパスワードでログインできる
    admin.put(f"/api/admin/users/{uid}", json={"display_name": "新メンバー", "is_admin": False, "is_active": True, "password": "password2"})
    from app.main import app

    member = TestClient(app)
    assert member.post("/api/auth/login", json={"login_name": "new.member", "password": "password2"}).status_code == 200
    # 自分自身の管理者権限は外せない・自分は削除できない
    me = next(u for u in admin.get("/api/admin/users").json() if u["login_name"] == "admin")
    assert admin.put(f"/api/admin/users/{me['id']}", json={"display_name": "管理者", "is_admin": False, "is_active": True}).status_code == 400
    assert admin.delete(f"/api/admin/users/{me['id']}").status_code == 400
    # 受講状況:公開講座の列と、全メンバーの行が並ぶ
    matrix = admin.get("/api/admin/progress").json()
    assert [c["slug"] for c in matrix["courses"]] == ["statistics-basics"]
    assert {m["login_name"] for m in matrix["members"]} >= {"admin", "learner", "new.member"}
    assert all(m["cells"][0]["state"] == "none" for m in matrix["members"])
    # メンバー詳細(マイページと同じ内容)
    assert admin.get(f"/api/admin/members/{uid}").json()["completed_course_count"] == 0
    # 削除すると一覧から消える
    assert admin.delete(f"/api/admin/users/{uid}").status_code == 204
    assert all(u["id"] != uid for u in admin.get("/api/admin/users").json())


def test_dataset_upload(admin):
    editor = admin.get("/api/admin/courses").json()[0]
    cid = editor["id"]
    # アップロード(同名は置き換え)
    res = admin.post(f"/api/admin/courses/{cid}/datasets", files={"file": ("extra.csv", b"a,b\n1,2\n", "text/csv")}).json()
    names = [d["filename"] for d in res["datasets"]]
    assert "extra.csv" in names
    res = admin.post(f"/api/admin/courses/{cid}/datasets", files={"file": ("extra.csv", b"a,b\n3,4\n", "text/csv")}).json()
    assert [d["filename"] for d in res["datasets"]].count("extra.csv") == 1
    ds = next(d for d in res["datasets"] if d["filename"] == "extra.csv")
    assert admin.get(ds["url"]).content == b"a,b\n3,4\n"
    assert admin.delete(f"/api/admin/datasets/{ds['id']}").status_code == 204
