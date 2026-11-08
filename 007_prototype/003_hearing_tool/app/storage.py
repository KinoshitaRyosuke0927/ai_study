"""CSVファイルの読み書きを行う。

データはすべて data フォルダの CSV に保存する。
1人で使うツールなので、同時に書き込む人はいない前提とし、
同じプロセスの中の書き込みだけをロックで順番にする。
"""

import csv
import os
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path

from .config import load_config

# 全ファイルに共通の列
COMMON_COLUMNS = ["updated_by", "updated_at"]

# テーブルの定義。キーはファイル名（拡張子なし）、値は (IDの列, 列の一覧)
TABLES: dict[str, tuple[str, list[str]]] = {
    "persons": ("person_id", ["person_id", "name", "role", "note"]),
    "sessions": ("session_id", [
        "session_id", "person_id", "round", "held_on", "interviewers", "duration_min",
        "status", "purpose", "screen_summary", "request_message", "audio_file", "memo",
    ]),
    "segments": ("segment_id", [
        "segment_id", "session_id", "order", "start_min", "end_min", "title", "aim", "hypothesis_ids",
    ]),
    "hypotheses": ("hypothesis_id", [
        "hypothesis_id", "person_id", "session_id", "label", "title", "body", "examples",
        "status", "source", "visibility",
    ]),
    "questions": ("question_id", [
        "question_id", "session_id", "segment_id", "order", "label", "priority", "text",
        "check_point", "is_data_question", "est_min", "hypothesis_ids", "asked", "answer_memo",
    ]),
    "utterances": ("utterance_id", [
        "utterance_id", "session_id", "order", "speaker", "text", "start_sec", "review_status",
        "excluded", "question_ids", "hypothesis_ids", "issue_ids",
    ]),
    "issues": ("issue_id", [
        "issue_id", "person_id", "session_ids", "title", "theme", "quote", "scene", "frequency", "time_per",
        "core_step", "judgment", "workaround", "impact", "certainty", "hypothesis_ids", "status",
        "visibility",
    ]),
    "data_sources": ("source_id", [
        "source_id", "person_id", "issue_ids", "name", "location", "format", "period", "volume",
        "has_result", "restriction", "confirmation",
    ]),
    "solutions": ("solution_id", [
        "solution_id", "issue_ids", "method", "uses_genai", "required_data", "concern",
    ]),
    "evaluations": ("evaluation_id", ["evaluation_id", "issue_id", "criterion", "rating", "comment"]),
    "criteria": ("criterion_id", ["criterion_id", "criterion", "question", "order"]),
    "terms": ("term_id", ["term_id", "term", "category", "description", "misrecognitions"]),
}

# 新しく行を作るときの既定値
DEFAULT_VALUES: dict[str, dict[str, str]] = {
    "sessions": {"status": "準備中", "duration_min": "30"},
    "hypotheses": {"status": "未確認", "visibility": "聞き手のみ"},
    "questions": {"priority": "○", "asked": "未", "is_data_question": "0"},
    "utterances": {"review_status": "未推敲", "excluded": "0"},
    "issues": {"status": "候補", "visibility": "聞き手のみ"},
    "data_sources": {"confirmation": "本人の認識"},
    "solutions": {"uses_genai": "0"},
}

# CSV の文字コード（Excel で開いても文字化けしないよう BOM 付き）
ENCODING = "utf-8-sig"

# 書き込みを順番にするためのロック
_lock = threading.Lock()


class StorageError(Exception):
    """CSV の読み書きに失敗したことを表す。"""


def data_dir() -> Path:
    """データフォルダの場所を返す。なければ作る。

    Returns:
        Path: データフォルダ。
    """
    # 設定からデータの場所を取り出し、サブフォルダも含めて用意する
    path = load_config()["data_path"]
    for sub in ("", "audio", "inbox", "exports", "backups"):
        (path / sub).mkdir(parents=True, exist_ok=True)
    return path


def new_id() -> str:
    """重複しないIDを作る。

    Returns:
        str: UUID の先頭12文字。
    """
    return uuid.uuid4().hex[:12]


def now_text() -> str:
    """現在時刻を秒までの文字列で返す。

    Returns:
        str: 例 "2026-11-08T10:15:00"。
    """
    return datetime.now().isoformat(timespec="seconds")


def columns_of(table: str) -> list[str]:
    """テーブルの全列（共通の列を含む）を返す。

    Args:
        table: テーブル名。

    Returns:
        list[str]: 列名の一覧。
    """
    _check_table(table)
    return TABLES[table][1] + COMMON_COLUMNS


def id_column(table: str) -> str:
    """テーブルのIDの列名を返す。

    Args:
        table: テーブル名。

    Returns:
        str: IDの列名。
    """
    _check_table(table)
    return TABLES[table][0]


def _check_table(table: str) -> None:
    """テーブル名が定義済みか確かめる。

    Args:
        table: テーブル名。

    Returns:
        None。未定義なら StorageError を送出する。
    """
    if table not in TABLES:
        raise StorageError(f"未定義のテーブルです：{table}")


def read_table(table: str, folder: Path | None = None) -> list[dict]:
    """CSV を読み込んで行の一覧を返す。

    Args:
        table: テーブル名。
        folder: 読み込むフォルダ。省略時はデータフォルダ。

    Returns:
        list[dict]: 行の一覧。ファイルがなければ空の一覧。足りない列は空文字で補う。
    """
    # 読み込むファイルを決める
    path = (folder or data_dir()) / f"{table}.csv"
    if not path.exists():
        return []

    # CSV を読み込み、定義にある列が欠けていれば空文字で補う
    with path.open(encoding=ENCODING, newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for col in columns_of(table):
            if row.get(col) is None:
                row[col] = ""
    return rows


def write_table(table: str, rows: list[dict], folder: Path | None = None) -> None:
    """行の一覧を CSV に書き込む。

    一時ファイルに書いてから置き換えるので、途中で失敗しても元のファイルは壊れない。

    Args:
        table: テーブル名。
        rows: 書き込む行の一覧。
        folder: 書き込むフォルダ。省略時はデータフォルダ。

    Returns:
        None。書き込めなかったら StorageError を送出する。
    """
    # 列の順番を決める（定義の列のあとに、手で追加された列を残す）
    fieldnames = list(columns_of(table))
    for row in rows:
        for key in row:
            if key not in fieldnames and key is not None:
                fieldnames.append(key)

    # 一時ファイルに書き込む
    target = (folder or data_dir()) / f"{table}.csv"
    temp = target.with_suffix(".csv.tmp")
    with temp.open("w", encoding=ENCODING, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in fieldnames})

    # 元のファイルと置き換える（Excel で開いていると失敗する）
    try:
        os.replace(temp, target)
    except PermissionError as exc:
        temp.unlink(missing_ok=True)
        raise StorageError(f"{target.name} に書き込めません。Excel などで開いている場合は閉じてください。") from exc


def create_row(table: str, values: dict, user: str) -> dict:
    """行を追加する。

    Args:
        table: テーブル名。
        values: 列の値。定義にない列は無視する。
        user: 更新者の名前。

    Returns:
        dict: 追加した行（IDと更新情報を含む）。
    """
    with _lock:
        # 既定値に入力値を重ね、IDと更新情報を付ける
        row = {col: "" for col in columns_of(table)}
        row.update(DEFAULT_VALUES.get(table, {}))
        row.update({k: _to_text(v) for k, v in values.items() if k in row})
        row[id_column(table)] = row[id_column(table)] or new_id()
        row["updated_by"] = user
        row["updated_at"] = now_text()

        # 末尾に追加して保存する
        rows = read_table(table)
        rows.append(row)
        write_table(table, rows)
        return row


def create_rows(table: str, values_list: list[dict], user: str) -> list[dict]:
    """複数の行をまとめて追加する（書き込みは1回）。

    Args:
        table: テーブル名。
        values_list: 行ごとの列の値。
        user: 更新者の名前。

    Returns:
        list[dict]: 追加した行。
    """
    with _lock:
        stamp = now_text()
        created = []
        for values in values_list:
            # 既定値に入力値を重ね、IDと更新情報を付ける
            row = {col: "" for col in columns_of(table)}
            row.update(DEFAULT_VALUES.get(table, {}))
            row.update({k: _to_text(v) for k, v in values.items() if k in row})
            row[id_column(table)] = row[id_column(table)] or new_id()
            row["updated_by"] = user
            row["updated_at"] = stamp
            created.append(row)

        # 末尾に追加して保存する
        rows = read_table(table)
        rows.extend(created)
        write_table(table, rows)
        return created


def modify_table(table: str, func) -> object:
    """テーブルを読み込み、関数で書き換えて保存する（書き込みは1回）。

    Args:
        table: テーブル名。
        func: 行の一覧を受け取り、(新しい行の一覧, 戻り値) を返す関数。

    Returns:
        object: func が返した戻り値。
    """
    with _lock:
        rows, result = func(read_table(table))
        write_table(table, rows)
        return result


def update_row(table: str, row_id: str, values: dict, user: str) -> dict:
    """行を更新する。

    Args:
        table: テーブル名。
        row_id: 更新する行のID。
        values: 変更する列の値。IDと更新情報の列は無視する。
        user: 更新者の名前。

    Returns:
        dict: 更新後の行。行がなければ StorageError を送出する。
    """
    with _lock:
        # 対象の行を探す
        rows = read_table(table)
        key = id_column(table)
        target = next((r for r in rows if r[key] == row_id), None)
        if target is None:
            raise StorageError(f"{table} に ID {row_id} の行がありません。")

        # 変更してよい列だけを書き換え、更新情報を付ける
        protected = {key, *COMMON_COLUMNS}
        for col, value in values.items():
            if col in columns_of(table) and col not in protected:
                target[col] = _to_text(value)
        target["updated_by"] = user
        target["updated_at"] = now_text()

        # 保存する
        write_table(table, rows)
        return target


def delete_rows(table: str, row_ids: set[str]) -> int:
    """行を削除する。

    Args:
        table: テーブル名。
        row_ids: 削除する行のIDの集合。

    Returns:
        int: 削除した行の数。
    """
    with _lock:
        # 対象以外の行を残して保存する
        rows = read_table(table)
        key = id_column(table)
        kept = [r for r in rows if r[key] not in row_ids]
        if len(kept) != len(rows):
            write_table(table, kept)
        return len(rows) - len(kept)


def read_all(folder: Path | None = None) -> dict[str, list[dict]]:
    """すべてのテーブルを読み込む。

    Args:
        folder: 読み込むフォルダ。省略時はデータフォルダ。

    Returns:
        dict[str, list[dict]]: テーブル名ごとの行の一覧。
    """
    return {table: read_table(table, folder) for table in TABLES}


def backup(reason: str) -> Path:
    """データフォルダの CSV と音声を backups フォルダに複製する。

    Args:
        reason: バックアップの理由。フォルダ名に付ける（例：import）。

    Returns:
        Path: 作成したバックアップのフォルダ。
    """
    # 日時と理由からフォルダ名を決める
    base = data_dir()
    target = base / "backups" / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{reason}"
    target.mkdir(parents=True, exist_ok=True)

    # CSV をすべて複製する
    for path in base.glob("*.csv"):
        shutil.copy2(path, target / path.name)

    # 音声は大きいのでファイル名の一覧だけ残す（音声は上書きしないため）
    audio_names = sorted(p.name for p in (base / "audio").glob("*") if p.is_file())
    (target / "audio_files.txt").write_text("\n".join(audio_names), encoding="utf-8")
    return target


def split_ids(value: str) -> list[str]:
    """";" 区切りのIDの文字列を一覧に分ける。

    Args:
        value: 例 "abc;def"。

    Returns:
        list[str]: 空の要素を除いたIDの一覧。
    """
    return [v.strip() for v in (value or "").split(";") if v.strip()]


def _to_text(value) -> str:
    """CSV に保存する文字列に変換する。

    Args:
        value: 任意の値。一覧なら ";" でつなぐ。

    Returns:
        str: 保存する文字列。
    """
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ";".join(str(v) for v in value)
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)
