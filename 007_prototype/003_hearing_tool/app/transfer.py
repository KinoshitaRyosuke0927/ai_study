"""データの ZIP の書き出しと取り込みを行う。

ZIP には CSV だけを入れる。音声や動画は大きいので、ファイルを直接渡して
data/audio に置いてもらう運用とする。
取り込みでは、同じIDの行は updated_at が新しいほうを残す。
上書きされる件数を先に確認できるよう、「確認」と「実行」の2段階にしている。
"""

import shutil
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from .storage import TABLES, backup, data_dir, id_column, read_table, write_table, new_id, _lock

# 取り込みの確認中のファイルを置くフォルダ名
INCOMING_DIR = "_incoming"


def export_zip(user_name: str) -> Path:
    """CSV を ZIP にまとめて exports フォルダに保存する（音声や動画は含めない）。

    Args:
        user_name: ファイル名に付ける利用者の名前。

    Returns:
        Path: 作成した ZIP のパス。
    """
    # ファイル名を決める
    base = data_dir()
    safe_user = "".join(c for c in user_name if c.isalnum()) or "user"
    target = base / "exports" / f"hearing_data_{safe_user}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

    # CSV だけを ZIP に入れる
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for table in TABLES:
            path = base / f"{table}.csv"
            if path.exists():
                zf.write(path, f"{table}.csv")
    return target


def _safe_extract(zip_path: Path, dest: Path) -> None:
    """ZIP から、ツールが扱う CSV だけを取り出す。

    フォルダの外に書き出す名前（../ など）や、CSV 以外のファイル（音声など）は無視する。

    Args:
        zip_path: ZIP のパス。
        dest: 取り出し先のフォルダ。

    Returns:
        None
    """
    allowed_csv = {f"{t}.csv" for t in TABLES}
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            # 名前を確かめる（直下にある、定義済みのテーブルの CSV だけを許可する）
            name = PurePosixPath(info.filename.replace("\\", "/"))
            if info.is_dir() or ".." in name.parts or name.is_absolute():
                continue
            if len(name.parts) != 1 or name.name not in allowed_csv:
                continue
            out = dest / name.name

            # 取り出す
            out.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, out.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def _compare(table: str, incoming: list[dict], local: list[dict]) -> dict:
    """取り込む行と今の行を比べ、区分ごとに数える。

    Args:
        table: テーブル名。
        incoming: 取り込む行。
        local: 今の行。

    Returns:
        dict: new（追加）、update（上書き）、skip（今のほうが新しいか同じ）の件数と、上書きの例。
    """
    key = id_column(table)
    local_by_id = {r[key]: r for r in local}
    result = {"new": 0, "update": 0, "skip": 0, "update_examples": []}
    for row in incoming:
        current = local_by_id.get(row.get(key, ""))
        if current is None:
            result["new"] += 1
        elif row.get("updated_at", "") > current.get("updated_at", ""):
            result["update"] += 1
            # 上書きされる行を確認しやすいよう、最初の数件だけ例を残す
            if len(result["update_examples"]) < 5:
                result["update_examples"].append({
                    "id": current[key],
                    "label": _row_label(current),
                    "local_by": current.get("updated_by", ""),
                    "local_at": current.get("updated_at", ""),
                    "incoming_by": row.get("updated_by", ""),
                    "incoming_at": row.get("updated_at", ""),
                })
        else:
            result["skip"] += 1
    return result


def _row_label(row: dict) -> str:
    """行を見分けるための短い文字列を返す。

    Args:
        row: 任意のテーブルの行。

    Returns:
        str: 名前や見出しなどの先頭30文字。
    """
    for col in ("name", "title", "label", "term", "text", "criterion", "method"):
        if row.get(col):
            return row[col][:30]
    return ""


def preview_import(zip_bytes: bytes) -> dict:
    """取り込む ZIP の中身を、今のデータと比べる。

    Args:
        zip_bytes: アップロードされた ZIP の内容。

    Returns:
        dict: token（実行時に使う番号）、tables（テーブルごとの件数）、
            missing_audio（CSV が参照しているのに data/audio にない音声のファイル名）。
    """
    # 前に確認だけして取り込まなかったファイルを片付ける（1人で使う前提）
    incoming_root = data_dir() / INCOMING_DIR
    if incoming_root.exists():
        shutil.rmtree(incoming_root, ignore_errors=True)

    # 確認用のフォルダを作り、ZIP を保存して取り出す
    token = new_id()
    work = incoming_root / token
    work.mkdir(parents=True, exist_ok=True)
    zip_path = work / "upload.zip"
    zip_path.write_bytes(zip_bytes)
    extract_dir = work / "files"
    extract_dir.mkdir()
    try:
        _safe_extract(zip_path, extract_dir)
    except zipfile.BadZipFile:
        shutil.rmtree(work, ignore_errors=True)
        raise ValueError("ZIP ファイルとして読み込めませんでした。")

    # テーブルごとに比べる
    tables = {}
    for table in TABLES:
        if (extract_dir / f"{table}.csv").exists():
            tables[table] = _compare(table, read_table(table, extract_dir), read_table(table))

    # 取り込む回が参照している音声のうち、まだ置かれていないものを調べる
    missing = sorted({
        s["audio_file"] for s in read_table("sessions", extract_dir)
        if s.get("audio_file") and not (data_dir() / "audio" / s["audio_file"]).exists()
    })
    return {"token": token, "tables": tables, "missing_audio": missing}


def apply_import(token: str, user_name: str) -> dict:
    """確認済みの ZIP を取り込む。

    Args:
        token: preview_import が返した番号。
        user_name: 実行した利用者の名前（バックアップの記録用）。

    Returns:
        dict: backup（作成したバックアップのフォルダ名）とテーブルごとの反映件数。
    """
    # 確認用のフォルダを探す（番号は英数字だけを許可する）
    if not token.isalnum():
        raise ValueError("番号が正しくありません。")
    work = data_dir() / INCOMING_DIR / token
    extract_dir = work / "files"
    if not extract_dir.exists():
        raise ValueError("確認したデータが見つかりません。もう一度ファイルを選んでください。")

    # 取り込む前に今のデータを保存する
    backup_path = backup("import")
    applied = {}

    with _lock:
        for table in TABLES:
            if not (extract_dir / f"{table}.csv").exists():
                continue
            key = id_column(table)
            local = read_table(table)
            index = {r[key]: i for i, r in enumerate(local)}
            count = 0

            # 新しい行は追加し、取り込むほうが新しい行は置き換える
            for row in read_table(table, extract_dir):
                rid = row.get(key, "")
                if not rid:
                    continue
                if rid not in index:
                    local.append(row)
                    index[rid] = len(local) - 1
                    count += 1
                elif row.get("updated_at", "") > local[index[rid]].get("updated_at", ""):
                    local[index[rid]] = row
                    count += 1
            if count:
                write_table(table, local)
            applied[table] = count

    # 確認用のフォルダを片付ける
    shutil.rmtree(work, ignore_errors=True)
    return {"backup": backup_path.name, "tables": applied, "by": user_name}
