"""業務状況のラベル(学習データ)の保存・読み込み。

保存先: data/labels.json
1件 = 1人×1日。保存するのは次の項目だけで、予定(予定名・時刻など)は保存しない。
学習するときは、ラベルのある日の予定を GROUPSESSION から読み込み直し、メモリ上で組み合わせる。
    {
      "uid": "308", "name": "氏名", "group": "M1143", "date": "2026-11-24",
      "slots": ["09:00", "09:30", ...],          # 枠の開始時刻
      "labels": ["office", "outside", "off", ...], # 枠ごとのラベル
      "saved_at": "2026-11-23T10:00:00"
    }
"""

from __future__ import annotations

import json
import threading
from datetime import datetime

from app.config import DATA_DIR

LABELS_FILE = DATA_DIR / "labels.json"
LABEL_VALUES = ("office", "outside", "off")
# 保存する項目(これ以外の項目は書き込まない。以前の版で保存していた予定 "events" もここで取り除かれる)
RECORD_KEYS = ("uid", "name", "group", "date", "slots", "labels", "saved_at")

_lock = threading.Lock()


def _key(uid: str, date: str) -> str:
    """
    ラベル1件を表すキー

    Args
    -----------------
    - uid: str,   メンバーのID
    - date: str,  日付 "YYYY-MM-DD"

    Returns
    -----------------
    - key: str,  "uid|date"

    """
    return f"{uid}|{date}"


def load_all() -> dict[str, dict]:
    """
    保存済みのラベルをすべて読み込む

    Args
    -----------------
    - なし

    Returns
    -----------------
    - labels: dict[str, dict],  {"uid|date": ラベル1件}

    """
    if not LABELS_FILE.exists():
        return {}
    return json.loads(LABELS_FILE.read_text(encoding="utf-8"))


def _write(labels: dict[str, dict]) -> None:
    """
    ラベルをファイルに書き込む(書きかけで壊れないよう、一時ファイルに書いてから置き換える)

    Args
    -----------------
    - labels: dict[str, dict],  すべてのラベル

    Returns
    -----------------
    - None

    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # 決めた項目だけを書き込む(予定名などが紛れ込まないようにする)
    cleaned = {k: {f: r[f] for f in RECORD_KEYS if f in r} for k, r in labels.items()}
    tmp = LABELS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cleaned, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(LABELS_FILE)


def get_range(uids: list[str], start: str, end: str) -> list[dict]:
    """
    指定したメンバー・期間の保存済みラベルを返す

    Args
    -----------------
    - uids: list[str],  メンバーのID
    - start: str,       開始日 "YYYY-MM-DD"
    - end: str,         終了日 "YYYY-MM-DD"

    Returns
    -----------------
    - records: list[dict],  ラベルの一覧

    """
    targets = set(uids)
    return [r for r in load_all().values() if r["uid"] in targets and start <= r["date"] <= end]


def save_records(records: list[dict]) -> int:
    """
    ラベルを保存する(同じメンバー・日付のものは上書き)

    Args
    -----------------
    - records: list[dict],  保存するラベル(uid, name, group, date, slots, labels)

    Returns
    -----------------
    - count: int,  保存した件数

    """
    # 内容を確認する(枠とラベルの数が合っているか、ラベルの値が正しいか)
    for r in records:
        if len(r["slots"]) != len(r["labels"]):
            raise ValueError(f"{r['date']} の枠とラベルの数が合いません")
        if any(v not in LABEL_VALUES for v in r["labels"]):
            raise ValueError(f"{r['date']} のラベルの値が正しくありません")

    # 既存のラベルに上書きして保存する
    now = datetime.now().isoformat(timespec="seconds")
    with _lock:
        labels = load_all()
        for r in records:
            labels[_key(r["uid"], r["date"])] = {
                "uid": r["uid"],
                "name": r.get("name", ""),
                "group": r.get("group", ""),
                "date": r["date"],
                "slots": r["slots"],
                "labels": r["labels"],
                "saved_at": now,
            }
        _write(labels)
    return len(records)


def delete_records(keys: list[tuple[str, str]]) -> int:
    """
    ラベルを削除する

    Args
    -----------------
    - keys: list[tuple[str, str]],  削除する (uid, date) の一覧

    Returns
    -----------------
    - count: int,  削除した件数

    """
    with _lock:
        labels = load_all()
        count = 0
        for uid, date in keys:
            if labels.pop(_key(uid, date), None) is not None:
                count += 1
        _write(labels)
    return count


def remove_saved_events() -> int:
    """
    以前の版で保存していた予定(予定名を含む "events")を、保存済みのラベルから取り除く(ラベルは残す)

    Args
    -----------------
    - なし

    Returns
    -----------------
    - count: int,  予定を取り除いたラベルの件数

    """
    with _lock:
        labels = load_all()
        count = sum(1 for r in labels.values() if "events" in r)
        if count:
            _write(labels)
    return count
