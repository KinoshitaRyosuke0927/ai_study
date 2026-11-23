"""スケジュール確認ツールの FastAPI エントリポイント。

GROUPSESSION にログインし、マイグループのメンバーの予定を指定期間分取得して画面に返す。
予定の内容はファイルに保存せず、画面(ブラウザのメモリ上)にだけ表示する。
"""

from __future__ import annotations

import math
from datetime import date

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import status_model, status_store
from app.config import RESOURCE_ROOT, load_config, save_selection
from app.groupsession_client import GroupsessionClient

STATIC_DIR = RESOURCE_ROOT / "app" / "static"
CONFIG = load_config()
client = GroupsessionClient(CONFIG["groupsession_base_url"])

app = FastAPI(title="スケジュール確認ツール", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# 以前の版でラベルと一緒に保存していた予定(予定名)を取り除く(ラベルは残す)
status_store.remove_saved_events()


class LoginRequest(BaseModel):
    username: str
    password: str


class ScheduleRequest(BaseModel):
    group: str
    member_ids: list[str]
    start: date
    end: date
    purpose: str = "free"  # "free": 空き時間 / "status": 業務状況(取得できる期間の上限が異なる)


class EstimateRequest(BaseModel):
    members: list[dict]
    days: list[dict]
    events: list[dict]


class LabelRecord(BaseModel):
    uid: str
    name: str = ""
    group: str = ""
    date: str
    slots: list[str]
    labels: list[str]


class SaveLabelsRequest(BaseModel):
    records: list[LabelRecord]


class DeleteLabelsRequest(BaseModel):
    keys: list[dict]  # [{"uid", "date"}]


class TrainRequest(BaseModel):
    group: str = ""  # グループが記録されていないラベルに使うマイグループ(画面で選んでいるもの)


@app.middleware("http")
async def no_store(request: Request, call_next):
    """
    APIの応答(予定の内容を含む)をブラウザのキャッシュに残さないようにする

    Args
    -----------------
    - request: Request,  リクエスト
    - call_next:         次の処理

    Returns
    -----------------
    - response: Response,  Cache-Control: no-store を付けた応答

    """
    response = await call_next(request)
    if request.url.path.startswith("/api/") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-store"
    return response


def _gs_error(exc: Exception) -> HTTPException:
    """
    GROUPSESSION とのやり取りで起きた例外を、画面に返すエラーに変換する

    Args
    -----------------
    - exc: Exception,  発生した例外

    Returns
    -----------------
    - error: HTTPException,  画面に返すエラー

    """
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=401, detail=str(exc))
    if isinstance(exc, requests.RequestException):
        return HTTPException(status_code=502, detail=f"GROUPSESSIONへのアクセスに失敗しました: {exc}")
    return HTTPException(status_code=502, detail=str(exc))


@app.get("/")
def index() -> FileResponse:
    """トップページを返す"""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/config")
def get_config() -> dict:
    """
    画面の初期値(空き時間の判定条件・最大週数・前回の選択)を返す

    Returns
    -----------------
    - config: dict,  画面で使う設定値(接続先のURLは返さない)

    """
    keys = ["business_start", "business_end", "slot_minutes", "lunch_start", "lunch_end",
            "min_duration_minutes", "max_weeks", "max_weeks_status", "labeling_enabled",
            "last_group", "last_member_ids"]
    current = load_config()
    return {k: current[k] for k in keys}


def _status_slots() -> list[str]:
    """
    業務状況の判定に使う枠(config.json の業務時間・昼休みを30分ごとに区切る)

    Returns
    -----------------
    - slots: list[str],  枠の開始時刻の一覧

    """
    c = load_config()
    return status_model.build_slots(c["business_start"], c["business_end"], c["lunch_start"], c["lunch_end"])


def _require_labeling() -> None:
    """
    ラベルの保存・削除、学習が許可されているか確認する(config.json の labeling_enabled)

    Args
    -----------------
    - なし

    Returns
    -----------------
    - None(許可されていなければ HTTPException 403)

    """
    if not load_config().get("labeling_enabled"):
        raise HTTPException(status_code=403, detail="この版ではラベルの保存・学習はできません(config.json の labeling_enabled が false)")


@app.get("/api/login-status")
def get_login_status() -> dict:
    """ログイン済みかどうかを返す"""
    return {"logged_in": client.logged_in}


@app.post("/api/login")
def post_login(req: LoginRequest) -> dict:
    """
    GROUPSESSION にログインする(ID・パスワードはメモリ上にのみ保持する)

    Args
    -----------------
    - req: LoginRequest,  ID・パスワード

    Returns
    -----------------
    - result: dict,  {"result": "ok"}

    """
    if not req.username.strip() or not req.password:
        raise HTTPException(status_code=400, detail="IDとパスワードを入力してください")
    try:
        client.login(req.username.strip(), req.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except requests.RequestException as exc:
        raise _gs_error(exc) from exc
    return {"result": "ok"}


@app.post("/api/logout")
def post_logout() -> dict:
    """ログアウトする(メモリ上のID・パスワードを破棄する)"""
    client.logout()
    return {"result": "ok"}


@app.get("/api/groups")
def get_groups() -> list[dict]:
    """
    ログインしたユーザーのマイグループ一覧を返す

    Returns
    -----------------
    - groups: list[dict],  [{"value", "name"}]

    """
    try:
        return client.get_my_groups()
    except Exception as exc:  # noqa: BLE001  画面にエラー内容を返す
        raise _gs_error(exc) from exc


@app.get("/api/groups/{group}/members")
def get_members(group: str) -> list[dict]:
    """
    マイグループのメンバー一覧を返す

    Args
    -----------------
    - group: str,  マイグループの値(例: "M1143")

    Returns
    -----------------
    - members: list[dict],  [{"uid", "name"}]

    """
    if not group.startswith("M"):
        raise HTTPException(status_code=400, detail="マイグループを指定してください")
    try:
        return client.get_group_members(group)
    except Exception as exc:  # noqa: BLE001
        raise _gs_error(exc) from exc


@app.post("/api/schedule")
def post_schedule(req: ScheduleRequest) -> dict:
    """
    選択したメンバーの、指定期間の予定を返す。あわせて、選んだグループ・メンバーのIDを次回用に保存する

    Args
    -----------------
    - req: ScheduleRequest,  グループ・メンバーのID・期間

    Returns
    -----------------
    - schedule: dict,  {"days", "members", "events"}(選択したメンバーの分だけ)

    """
    # 入力を確認する(期間の向き・長さ、メンバーの選択)
    if not req.group.startswith("M"):
        raise HTTPException(status_code=400, detail="マイグループを指定してください")
    if not req.member_ids:
        raise HTTPException(status_code=400, detail="メンバーを1人以上選択してください")
    if req.end < req.start:
        raise HTTPException(status_code=400, detail="終了日は開始日以降の日付にしてください")
    max_weeks = int(load_config()["max_weeks_status" if req.purpose == "status" else "max_weeks"])
    weeks = math.ceil(((req.end - req.start).days + 1) / 7)
    if weeks > max_weeks:
        raise HTTPException(status_code=400, detail=f"一度に取得できる期間は{max_weeks}週間までです")

    # 予定を取得し、選択したメンバーの分だけに絞る
    try:
        schedule = client.get_schedule(req.group, req.start, req.end)
    except Exception as exc:  # noqa: BLE001
        raise _gs_error(exc) from exc
    selected = set(req.member_ids)
    schedule["members"] = [m for m in schedule["members"] if m["uid"] in selected]
    schedule["events"] = [e for e in schedule["events"] if e["uid"] in selected]

    # 次回用に、グループとメンバーのIDだけを保存する(予定の内容は保存しない)
    save_selection({"last_group": req.group, "last_member_ids": req.member_ids})
    return schedule


# ============================================================================ 業務状況(ステップ3)

@app.post("/api/status/estimate")
def post_status_estimate(req: EstimateRequest) -> dict:
    """
    メンバー×日付ごとに、枠ごとのラベルと出社割合を求める(保存済みラベル > モデル > ルール)

    Args
    -----------------
    - req: EstimateRequest,  メンバー・日付・予定(判定に使うだけで保存しない)

    Returns
    -----------------
    - result: dict,  {"slots", "results", "model"}

    """
    slots = _status_slots()
    try:
        results = status_model.estimate(req.members, req.days, req.events, slots)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"業務状況の判定に失敗しました: {exc}") from exc
    return {"slots": slots, "results": results, "model": status_model.model_info()}


@app.post("/api/status/labels")
def post_status_labels(req: SaveLabelsRequest) -> dict:
    """
    ラベル(メンバー・日付・枠ごとのラベル)を保存する。予定は保存しない

    Args
    -----------------
    - req: SaveLabelsRequest,  保存するラベル

    Returns
    -----------------
    - result: dict,  {"saved": 件数, "total": 保存済みの総件数}

    """
    _require_labeling()
    try:
        saved = status_store.save_records([r.model_dump() for r in req.records])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"saved": saved, "total": len(status_store.load_all())}


@app.post("/api/status/labels/delete")
def post_status_labels_delete(req: DeleteLabelsRequest) -> dict:
    """
    保存済みのラベルを削除する

    Args
    -----------------
    - req: DeleteLabelsRequest,  削除する (uid, date)

    Returns
    -----------------
    - result: dict,  {"deleted": 件数, "total": 保存済みの総件数}

    """
    _require_labeling()
    deleted = status_store.delete_records([(k["uid"], k["date"]) for k in req.keys])
    return {"deleted": deleted, "total": len(status_store.load_all())}


@app.get("/api/status/summary")
def get_status_summary() -> dict:
    """
    保存済みのラベル数と、学習済みモデルの情報を返す

    Returns
    -----------------
    - summary: dict,  {"label_count", "model", "min_train_days"}

    """
    return {
        "label_count": len(status_store.load_all()),
        "model": status_model.model_info(),
        "min_train_days": status_model.MIN_TRAIN_DAYS,
    }


@app.post("/api/status/train")
def post_status_train(req: TrainRequest) -> dict:
    """
    保存済みのラベルからモデルを学習する。ラベルのある日の予定は GROUPSESSION から読み込み直し、
    メモリ上でだけ使う(予定名はファイルに保存しない。学習はこのPCの中で行う)

    Args
    -----------------
    - req: TrainRequest,  グループが記録されていないラベルに使うマイグループ

    Returns
    -----------------
    - info: dict,  学習したモデルの情報(精度・使えなかったラベルの件数を含む)

    """
    _require_labeling()
    try:
        return status_model.train(client.get_schedule, req.group)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (PermissionError, requests.RequestException) as exc:
        raise _gs_error(exc) from exc
