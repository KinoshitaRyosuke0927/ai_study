"""テーブルの読み書きと設定の API。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import load_config, save_user_name
from ..storage import (
    TABLES, StorageError, columns_of, create_row, delete_rows, read_all, read_table, update_row,
)

router = APIRouter(prefix="/api")


class RowValues(BaseModel):
    """行の値を受け取る。"""

    values: dict


class Settings(BaseModel):
    """設定の変更を受け取る。"""

    user_name: str


def _check(table: str) -> None:
    """テーブル名が定義済みか確かめる。

    Args:
        table: テーブル名。

    Returns:
        None。未定義なら 404 を返す。
    """
    if table not in TABLES:
        raise HTTPException(status_code=404, detail=f"未定義のテーブルです：{table}")


@router.get("/data")
def get_all_data() -> dict:
    """すべてのテーブルと設定を返す。

    データは小さいので、画面は最初にまとめて受け取って表示する。

    Returns:
        dict: tables（テーブルごとの行）、columns（列の定義）、settings（設定）。
    """
    config = load_config()
    return {
        "tables": read_all(),
        "columns": {t: columns_of(t) for t in TABLES},
        "settings": {
            "user_name": config["user_name"],
            "data_path": str(config["data_path"]),
            "config_source": config["config_source"],
        },
    }


@router.put("/settings")
def put_settings(body: Settings) -> dict:
    """更新者の名前を保存する。

    Args:
        body: 新しい名前。

    Returns:
        dict: 保存後の名前。
    """
    # 空の名前は受け付けない
    name = body.user_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="名前を入力してください。")
    save_user_name(name)
    return {"user_name": name}


@router.post("/tables/{table}")
def post_row(table: str, body: RowValues) -> dict:
    """行を追加する。

    Args:
        table: テーブル名。
        body: 列の値。

    Returns:
        dict: 追加した行。
    """
    _check(table)
    return create_row(table, body.values, load_config()["user_name"])


@router.put("/tables/{table}/{row_id}")
def put_row(table: str, row_id: str, body: RowValues) -> dict:
    """行を更新する。

    Args:
        table: テーブル名。
        row_id: 行のID。
        body: 変更する列の値。

    Returns:
        dict: 更新後の行。
    """
    _check(table)
    user = load_config()["user_name"]
    try:
        # 評価の観点の名前を変えるときは、変える前の名前を控えておく
        before = None
        if table == "criteria":
            before = next((c["criterion"] for c in read_table("criteria") if c["criterion_id"] == row_id), None)

        row = update_row(table, row_id, body.values, user)

        # 観点の名前が変わったら、評価の行の観点の名前も合わせる
        if table == "criteria" and before and before != row["criterion"]:
            for ev in read_table("evaluations"):
                if ev["criterion"] == before:
                    update_row("evaluations", ev["evaluation_id"], {"criterion": row["criterion"]}, user)
        return row
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/tables/{table}/{row_id}")
def remove_row(table: str, row_id: str) -> dict:
    """行を削除する。

    対象者は、回が残っていると削除できない。
    回を削除すると、その回の区切り、質問、発言もあわせて削除する。

    Args:
        table: テーブル名。
        row_id: 行のID。

    Returns:
        dict: テーブルごとの削除件数。
    """
    _check(table)
    deleted: dict[str, int] = {}

    # 対象者は、回が残っていれば削除しない
    if table == "persons" and any(s["person_id"] == row_id for s in read_table("sessions")):
        raise HTTPException(status_code=400, detail="この対象者には回が残っています。先に回を削除してください。")

    # 回を削除するときは、回に属する行もまとめて削除する
    if table == "sessions":
        for child in ("segments", "questions", "utterances"):
            ids = {r[TABLES[child][0]] for r in read_table(child) if r["session_id"] == row_id}
            deleted[child] = delete_rows(child, ids)

    # 課題を削除するときは、その課題の評価もあわせて削除する
    if table == "issues":
        ids = {e["evaluation_id"] for e in read_table("evaluations") if e["issue_id"] == row_id}
        deleted["evaluations"] = delete_rows("evaluations", ids)

    # 評価の観点を削除するときは、その観点の評価もあわせて削除する
    if table == "criteria":
        name = next((c["criterion"] for c in read_table("criteria") if c["criterion_id"] == row_id), None)
        ids = {e["evaluation_id"] for e in read_table("evaluations") if e["criterion"] == name}
        deleted["evaluations"] = delete_rows("evaluations", ids)

    deleted[table] = delete_rows(table, {row_id})
    return {"deleted": deleted}
