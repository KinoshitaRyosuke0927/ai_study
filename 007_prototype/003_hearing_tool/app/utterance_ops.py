"""文字起こしの発言の結合、分割、置き換えなどの操作。

どの操作も utterances.csv を1回だけ書き換え、操作の後に順番を 1 から振り直す。
"""

from .planning import to_number
from .storage import columns_of, modify_table, new_id, now_text, split_ids


class UtteranceError(Exception):
    """発言の操作に失敗したことを表す。"""


def _session_rows(rows: list[dict], session_id: str) -> list[dict]:
    """回の発言を順番どおりに返す。

    Args:
        rows: utterances の全行。
        session_id: 回のID。

    Returns:
        list[dict]: 回の発言（order の順）。
    """
    return sorted([r for r in rows if r["session_id"] == session_id], key=lambda r: to_number(r["order"], 99999))


def _renumber(rows: list[dict], session_id: str) -> None:
    """回の発言の順番を 1 から振り直す。

    Args:
        rows: utterances の全行（その場で書き換える）。
        session_id: 回のID。

    Returns:
        None
    """
    for i, row in enumerate(_session_rows(rows, session_id), start=1):
        row["order"] = str(i)


def _touch(row: dict, user: str) -> None:
    """行の更新情報を付ける。

    Args:
        row: 行（その場で書き換える）。
        user: 更新者の名前。

    Returns:
        None
    """
    row["updated_by"] = user
    row["updated_at"] = now_text()


def _merge_into(target: dict, source: dict) -> None:
    """source の発言を target の後ろにつなげる。

    Args:
        target: 残す発言（その場で書き換える）。
        source: つなげる発言。

    Returns:
        None
    """
    # 本文は改行でつなぐ
    target["text"] = "\n".join(t for t in (target["text"].strip(), source["text"].strip()) if t)
    # ひも付けは両方を合わせる
    for col in ("question_ids", "hypothesis_ids", "issue_ids"):
        merged = split_ids(target[col]) + [i for i in split_ids(source[col]) if i not in split_ids(target[col])]
        target[col] = ";".join(merged)
    # どちらかが未推敲なら未推敲、両方が対象外のときだけ対象外にする
    if "未推敲" in (target["review_status"], source["review_status"]):
        target["review_status"] = "未推敲"
    target["excluded"] = "1" if target["excluded"] == "1" and source["excluded"] == "1" else "0"
    # 発言者が空なら、つなげる側の発言者を使う
    target["speaker"] = target["speaker"] or source["speaker"]


def merge_with_previous(session_id: str, utterance_id: str, user: str) -> None:
    """発言を1つ前の発言につなげる。

    Args:
        session_id: 回のID。
        utterance_id: つなげる発言のID。
        user: 更新者の名前。

    Returns:
        None
    """
    def change(rows: list[dict]):
        # 対象と1つ前の発言を探す
        ordered = _session_rows(rows, session_id)
        index = next((i for i, r in enumerate(ordered) if r["utterance_id"] == utterance_id), None)
        if index is None:
            raise UtteranceError("発言が見つかりません。")
        if index == 0:
            raise UtteranceError("最初の発言は、前の発言につなげられません。")

        # つなげて、つなげた側を消す
        previous, current = ordered[index - 1], ordered[index]
        _merge_into(previous, current)
        _touch(previous, user)
        rows = [r for r in rows if r["utterance_id"] != utterance_id]
        _renumber(rows, session_id)
        return rows, None

    modify_table("utterances", change)


def merge_same_speakers(session_id: str, user: str) -> int:
    """続けて同じ発言者が話している発言を1つにまとめる。

    発言者が空の発言はまとめない。

    Args:
        session_id: 回のID。
        user: 更新者の名前。

    Returns:
        int: まとめて減った発言の数。
    """
    def change(rows: list[dict]):
        removed = set()
        keeper = None
        for row in _session_rows(rows, session_id):
            # 直前と同じ発言者なら、直前の発言につなげる
            if keeper and row["speaker"] and row["speaker"] == keeper["speaker"]:
                _merge_into(keeper, row)
                _touch(keeper, user)
                removed.add(row["utterance_id"])
            else:
                keeper = row
        rows = [r for r in rows if r["utterance_id"] not in removed]
        _renumber(rows, session_id)
        return rows, len(removed)

    return modify_table("utterances", change)


def split_utterance(session_id: str, utterance_id: str, position: int, user: str) -> None:
    """発言を指定の位置で2つに分ける。

    Args:
        session_id: 回のID。
        utterance_id: 分ける発言のID。
        position: 分ける位置（本文の先頭からの文字数）。
        user: 更新者の名前。

    Returns:
        None
    """
    def change(rows: list[dict]):
        # 対象の発言を探し、位置を確かめる
        target = next((r for r in rows if r["utterance_id"] == utterance_id and r["session_id"] == session_id), None)
        if target is None:
            raise UtteranceError("発言が見つかりません。")
        head, tail = target["text"][:position].strip(), target["text"][position:].strip()
        if not head or not tail:
            raise UtteranceError("分けたい位置にカーソルを置いてから押してください。")

        # 前半を残し、後半を新しい発言として直後に入れる
        target["text"] = head
        _touch(target, user)
        new_row = dict(target)
        new_row.update({"utterance_id": new_id(), "text": tail, "order": f"{to_number(target['order']) + 0.5}"})
        _touch(new_row, user)
        rows.append(new_row)
        _renumber(rows, session_id)
        return rows, None

    modify_table("utterances", change)


def replace_text(session_id: str, wrong: str, right: str, user: str, utterance_id: str = "") -> int:
    """発言の中の文字を置き換える（誤認識の修正に使う）。

    Args:
        session_id: 回のID。
        wrong: 置き換える前の文字。
        right: 置き換えた後の文字。
        user: 更新者の名前。
        utterance_id: 指定すればその発言だけ、空なら回のすべての発言を置き換える。

    Returns:
        int: 置き換えた発言の数。
    """
    if not wrong:
        raise UtteranceError("置き換える文字が空です。")

    def change(rows: list[dict]):
        count = 0
        for row in _session_rows(rows, session_id):
            if utterance_id and row["utterance_id"] != utterance_id:
                continue
            if wrong in row["text"]:
                row["text"] = row["text"].replace(wrong, right)
                _touch(row, user)
                count += 1
        return rows, count

    return modify_table("utterances", change)


def bulk_update(session_id: str, values: dict, user: str, utterance_ids: list[str] | None = None) -> int:
    """回の発言をまとめて更新する（すべて推敲済みにする、など）。

    Args:
        session_id: 回のID。
        values: 変更する列の値。変更できるのは speaker、review_status、excluded だけ。
        user: 更新者の名前。
        utterance_ids: 対象の発言。省略時は回のすべての発言。

    Returns:
        int: 更新した発言の数。
    """
    allowed = {k: v for k, v in values.items() if k in ("speaker", "review_status", "excluded")}

    def change(rows: list[dict]):
        count = 0
        for row in _session_rows(rows, session_id):
            if utterance_ids is not None and row["utterance_id"] not in utterance_ids:
                continue
            if any(row[k] != v for k, v in allowed.items()):
                row.update(allowed)
                _touch(row, user)
                count += 1
        return rows, count

    return modify_table("utterances", change)


def insert_after(session_id: str, utterance_id: str, user: str) -> dict:
    """発言の直後に空の発言を入れる（発言の抜けを足すときに使う）。

    Args:
        session_id: 回のID。
        utterance_id: この発言の直後に入れる。空なら先頭に入れる。
        user: 更新者の名前。

    Returns:
        dict: 入れた発言。
    """
    def change(rows: list[dict]):
        # 入れる位置の順番と、時刻を決める
        base = next((r for r in rows if r["utterance_id"] == utterance_id), None)
        order = to_number(base["order"]) + 0.5 if base else 0.5
        new_row = {col: "" for col in columns_of("utterances")}
        new_row.update({
            "utterance_id": new_id(), "session_id": session_id, "order": str(order), "speaker": "",
            "text": "", "start_sec": base["start_sec"] if base else "", "review_status": "未推敲",
            "excluded": "0", "question_ids": "", "hypothesis_ids": "", "issue_ids": "",
        })
        _touch(new_row, user)
        rows.append(new_row)
        _renumber(rows, session_id)
        return rows, new_row

    return modify_table("utterances", change)
