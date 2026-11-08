"""Markdown の出力と、データの受け渡し（ZIP）の API。"""

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..config import load_config
from ..markdown_export import render_field, render_plan, save_export
from ..storage import read_table, split_ids
from ..transfer import apply_import, export_zip, preview_import

router = APIRouter(prefix="/api")

# 出力の種類と、保存するファイル名の先頭
EXPORT_KINDS = {
    "plan": "plan",
    "summary": "summary",
    "request": "request",
}


class ApplyImport(BaseModel):
    """取り込みの実行の指示を受け取る。"""

    token: str


def _file_label(session_ids: list[str]) -> str:
    """出力ファイル名に付ける、対象者と回の文字列を作る。

    Args:
        session_ids: 回のIDの一覧。

    Returns:
        str: 例 "round2_石井さん"。
    """
    # 回と対象者の名前を集める
    sessions = {s["session_id"]: s for s in read_table("sessions")}
    persons = {p["person_id"]: p["name"] for p in read_table("persons")}
    picked = [sessions[i] for i in session_ids if i in sessions]
    rounds = sorted({s["round"] for s in picked})
    names = [persons.get(s["person_id"], "") for s in picked]

    # ファイル名に使えない文字を除いてつなぐ
    text = "round" + "-".join(rounds) + "_" + "_".join(names)
    return "".join(c for c in text if c not in '\\/:*?"<>|')


@router.get("/export/{kind}")
def get_export(kind: str, session_ids: str, save: bool = False) -> dict:
    """Markdown の資料を作る。

    Args:
        kind: "plan"（進行資料）、"summary"（本人向けの要約）、"request"（事前の依頼文）。
        session_ids: 回のID。";" 区切りで複数指定できる（要約と依頼文は最初の1つだけ）。
        save: True なら exports フォルダにも保存する。

    Returns:
        dict: markdown（内容）と saved（保存したファイル名。保存しないときは空）。
    """
    # 種類と回を確かめる
    if kind not in EXPORT_KINDS:
        raise HTTPException(status_code=404, detail="出力の種類が正しくありません。")
    ids = split_ids(session_ids)
    if not ids:
        raise HTTPException(status_code=400, detail="回を選んでください。")

    # 種類に応じて資料を作る
    if kind == "plan":
        text = render_plan(ids)
    else:
        ids = ids[:1]
        text = render_field(ids[0], "screen_summary" if kind == "summary" else "request_message")

    # 必要なら保存する
    saved = save_export(f"{EXPORT_KINDS[kind]}_{_file_label(ids)}", text) if save else ""
    return {"markdown": text, "saved": saved}


@router.get("/transfer/export")
def get_transfer_export() -> FileResponse:
    """データを ZIP にまとめてダウンロードさせる。

    Returns:
        FileResponse: ZIP ファイル。exports フォルダにも残る。
    """
    path = export_zip(load_config()["user_name"])
    return FileResponse(path, filename=path.name, media_type="application/zip")


@router.post("/transfer/preview")
async def post_transfer_preview(file: UploadFile = File(...)) -> dict:
    """取り込む ZIP を今のデータと比べる。

    Args:
        file: アップロードされた ZIP。

    Returns:
        dict: transfer.preview_import の結果。
    """
    try:
        return preview_import(await file.read())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/transfer/apply")
def post_transfer_apply(body: ApplyImport) -> dict:
    """確認した ZIP を取り込む。

    Args:
        body: preview で受け取った番号。

    Returns:
        dict: transfer.apply_import の結果。
    """
    try:
        return apply_import(body.token, load_config()["user_name"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
