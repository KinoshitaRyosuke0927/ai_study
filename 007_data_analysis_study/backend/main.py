# -*- coding: utf-8 -*-
"""データサイエンス基礎ドリル - FastAPI アプリ

起動:
    uvicorn backend.main:app --reload --host 0.0.0.0 --port 8777
"""

import os

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import curriculum, db, extra_lessons, grader

app = FastAPI(title="データサイエンス基礎ドリル", version="0.2.0")

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATIC_DIR = os.path.join(BASE_DIR, "static")

db.init_db()

# 全レッスン = 第1章（curriculum.py）+ 第2章以降（extra_lessons.py）
ALL_LESSONS = curriculum.LESSONS + extra_lessons.EXTRA_LESSONS


# ---------- リクエストボディ ----------
class CodeSubmit(BaseModel):
    code: str


class StdoutGrade(BaseModel):
    code: str
    stdout: str


class VizCheck(BaseModel):
    code: str
    ran_ok: bool
    chart_count: int


class QuizAnswer(BaseModel):
    answer_index: int


class ReportText(BaseModel):
    text: str


# ---------- ヘルパー ----------
def _find_lesson(lesson_id: str):
    for l in ALL_LESSONS:
        if l["id"] == lesson_id:
            return l
    return None


def _find_drill(lesson, drill_id: str):
    for d in lesson.get("drills", []):
        if d["id"] == drill_id:
            return d
    return None


def _require(lesson_id: str, drill_id: str):
    lesson = _find_lesson(lesson_id)
    if lesson is None:
        raise HTTPException(404, "レッスンが見つかりません")
    drill = _find_drill(lesson, drill_id)
    if drill is None:
        raise HTTPException(404, "ドリルが見つかりません")
    return lesson, drill


def _is_done(drill_id: str, progress: dict) -> bool:
    return progress.get(drill_id, {}).get("completed", False)


def _lesson_card(lesson, progress) -> dict:
    drills = lesson.get("drills", [])
    done = sum(1 for d in drills if _is_done(d["id"], progress))
    return {
        "id": lesson["id"], "chapter": lesson.get("chapter"),
        "chapter_title": lesson.get("chapter_title", ""), "order": lesson.get("order"),
        "title": lesson["title"], "minutes": lesson.get("minutes", 0),
        "status": lesson.get("status", "open"), "summary": lesson.get("summary", ""),
        "drill_count": len(drills), "drill_done": done,
    }


def _public_lesson(lesson) -> dict:
    """解答（expected / answer_index）を除いた公開用レッスン"""
    result = {k: v for k, v in lesson.items() if k != "drills"}
    public_drills = []
    for d in lesson.get("drills", []):
        pd_ = {k: v for k, v in d.items() if k not in ("expected", "answer_index")}
        public_drills.append(pd_)
    result["drills"] = public_drills
    return result


# ---------- API ----------
@app.get("/api/course")
def get_course():
    return curriculum.COURSE


@app.get("/api/lessons")
def get_lessons():
    progress = db.get_progress()
    lessons = [_lesson_card(l, progress) for l in ALL_LESSONS]
    total_drills = sum(l["drill_count"] for l in lessons)
    total_done = sum(l["drill_done"] for l in lessons)
    return {"lessons": lessons, "total_drills": total_drills, "total_done": total_done}


@app.get("/api/lessons/{lesson_id}")
def get_lesson(lesson_id: str):
    lesson = _find_lesson(lesson_id)
    if lesson is None:
        raise HTTPException(404, "レッスンが見つかりません")
    return _public_lesson(lesson)


@app.get("/api/progress")
def get_progress():
    return db.get_progress()


@app.delete("/api/progress")
def reset_progress():
    db.reset_progress()
    return {"ok": True, "message": "進捗をリセットしました"}


# ---------- 実行（採点なし。ブラウザ実行が使えないときのフォールバック） ----------
@app.post("/api/lessons/{lesson_id}/drills/{drill_id}/run")
def run_drill(lesson_id: str, drill_id: str, body: CodeSubmit):
    lesson, drill = _require(lesson_id, drill_id)
    if drill["type"] not in ("code_gap", "viz"):
        raise HTTPException(400, "このドリルはコードを実行できません（選択式です）")
    data_files = drill.get("data_files")
    code = grader.build_full_code(drill["starter"], body.code)
    result = grader.run_code(code, data_files=data_files,
                             save_chart=(drill["type"] == "viz"), drill_id=drill_id)
    return {"ran": result["ok"], "stdout": result["stdout"], "stderr": result["stderr"],
            "returncode": result["returncode"], "elapsed_ms": result["elapsed_ms"],
            "chart_url": result["chart_url"]}


# ---------- サーバー実行で採点（ブラウザ実行が使えないときのフォールバック） ----------
@app.post("/api/lessons/{lesson_id}/drills/{drill_id}/submit")
def submit_drill(lesson_id: str, drill_id: str, body: CodeSubmit):
    lesson, drill = _require(lesson_id, drill_id)
    data_files = drill.get("data_files")
    if drill["type"] == "code_gap":
        grade = grader.grade_code_gap(drill["starter"], body.code,
                                      drill["expected"], data_files=data_files)
    elif drill["type"] == "viz":
        grade = grader.grade_code_check(drill["starter"], body.code,
                                        data_files=data_files, drill_id=drill_id)
    else:
        raise HTTPException(400, "このドリルは対象外です")
    db.record_attempt(drill_id, grade["passed"])
    return {"drill_id": drill_id, **grade}


# ---------- ブラウザ内実行（Pyodide）での採点 ----------
@app.post("/api/lessons/{lesson_id}/drills/{drill_id}/grade")
def grade_stdout(lesson_id: str, drill_id: str, body: StdoutGrade):
    """コードはブラウザで実行済み。サーバーは出力を期待値と照合して記録する"""
    lesson, drill = _require(lesson_id, drill_id)
    if drill["type"] != "code_gap":
        raise HTTPException(400, "このドリルは出力照合の対象外です")
    got_n = grader._normalize(body.stdout)
    exp_n = grader._normalize("\n".join(drill["expected"]))
    passed = got_n == exp_n
    db.record_attempt(drill_id, passed)
    return {
        "drill_id": drill_id, "passed": passed,
        "kind": "match" if passed else "mismatch",
        "message": "正解です！期待した出力と一致しました。"
        if passed else "出力が期待値と一致しません。下の「期待される出力」と見比べてみましょう。",
        "expected": "\n".join(drill["expected"]),
        "got": (body.stdout or "").rstrip("\n"),
    }


@app.post("/api/lessons/{lesson_id}/drills/{drill_id}/viz_check")
def viz_check(lesson_id: str, drill_id: str, body: VizCheck):
    """可視化ドリル：ブラウザでエラーなく実行でき、図が1つ以上出来たら合格"""
    lesson, drill = _require(lesson_id, drill_id)
    if drill["type"] != "viz":
        raise HTTPException(400, "対象外のドリルです")
    passed = body.ran_ok and body.chart_count >= 1
    db.record_attempt(drill_id, passed)
    return {
        "drill_id": drill_id, "passed": passed, "kind": "run_ok",
        "message": "エラーなく実行できました。図ができていればOKです。"
        if passed else "まだ図（グラフ）が作られていません。plt で図を作ってから再挑戦しましょう。",
    }


# ---------- 選択式 ----------
@app.post("/api/lessons/{lesson_id}/drills/{drill_id}/quiz")
def answer_quiz(lesson_id: str, drill_id: str, body: QuizAnswer):
    lesson, drill = _require(lesson_id, drill_id)
    if drill["type"] != "quiz":
        raise HTTPException(400, "このドリルは選択式ではありません")
    passed = body.answer_index == drill["answer_index"]
    db.record_attempt(drill_id, passed)
    return {"drill_id": drill_id, "passed": passed,
            "answer_index": body.answer_index, "feedback": drill["feedback"]}


# ---------- レポート提出（総合ドリルの最終課題） ----------
@app.post("/api/lessons/{lesson_id}/drills/{drill_id}/report")
def submit_report(lesson_id: str, drill_id: str, body: ReportText):
    lesson, drill = _require(lesson_id, drill_id)
    if drill["type"] != "report":
        raise HTTPException(400, "このドリルはレポート提出の対象外です")
    if not body.text or not body.text.strip():
        raise HTTPException(400, "レポートが空です。1行以上書いてください")
    db.record_attempt(drill_id, True)  # 提出できたら完了
    return {"drill_id": drill_id, "passed": True,
            "message": "レポートを提出しました。講座の完走おめでとうございます！"}


# ---------- 静的ファイル ----------
app.mount("/media", StaticFiles(directory=os.path.join(STATIC_DIR, "media")), name="media")
app.mount("/data", StaticFiles(directory=os.path.join(STATIC_DIR, "data")), name="data")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
