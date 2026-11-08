"""ヒアリングのデータから Markdown の資料を作る。"""

from datetime import datetime

from .planning import sort_by_order, to_number
from .storage import data_dir, read_all, split_ids


def _cell(text: str) -> str:
    """Markdown の表のセルに入れられる形に変える。

    Args:
        text: セルの文字列。

    Returns:
        str: 縦線をエスケープし、改行を <br> にした文字列。
    """
    return (text or "").replace("|", "\\|").replace("\r\n", "\n").replace("\n", "<br>")


def _range_text(start: str, end: str) -> str:
    """開始と終了の分から「2〜5分」の形の文字列を作る。

    Args:
        start: 開始（分）。
        end: 終了（分）。

    Returns:
        str: 例 "2〜5分"。
    """
    return f"{to_number(start):g}〜{to_number(end):g}分"


def _hypotheses_for(session: dict, data: dict) -> list[dict]:
    """回で扱う仮説を返す。

    この回で立てた仮説と、この回の区切りや質問にひも付いた仮説を対象にする。

    Args:
        session: sessions の行。
        data: read_all() の結果。

    Returns:
        list[dict]: 仮説の一覧（label の順）。
    """
    # 区切りと質問からひも付いた仮説のIDを集める
    linked = set()
    for row in data["segments"] + data["questions"]:
        if row["session_id"] == session["session_id"]:
            linked.update(split_ids(row["hypothesis_ids"]))

    # この回で立てたものと、ひも付いたものを合わせる
    rows = [
        h for h in data["hypotheses"]
        if h["person_id"] == session["person_id"]
        and (h["session_id"] == session["session_id"] or h["hypothesis_id"] in linked)
    ]
    return sorted(rows, key=lambda h: h["label"])


def _question_table(questions: list[dict]) -> list[str]:
    """質問の表の行を作る。

    Args:
        questions: questions の行の一覧。

    Returns:
        list[str]: Markdown の行の一覧。
    """
    lines = ["| | No. | 質問 | 確認すること |", "|---|---|---|---|"]
    for q in sort_by_order(questions):
        # データの有無を聞く質問は、確認することを太字にする
        check = _cell(q["check_point"])
        if q["is_data_question"] == "1" and "データの有無" in check and "**" not in check:
            check = check.replace("データの有無", "**データの有無**")
        lines.append(f"| {q['priority']} | {q['label'] or '-'} | {_cell(q['text'])} | {check} |")
    return lines


def render_plan(session_ids: list[str]) -> str:
    """進行資料（聞き手用）を作る。

    Args:
        session_ids: 資料に含める回のID。複数の対象者の同じ回をまとめて出せる。

    Returns:
        str: Markdown の文字列。
    """
    # 対象の回を読み込み、指定の順に並べる
    data = read_all()
    by_id = {s["session_id"]: s for s in data["sessions"]}
    sessions = [by_id[i] for i in session_ids if i in by_id]
    if not sessions:
        return "対象の回がありません。\n"
    persons = {p["person_id"]: p for p in data["persons"]}
    rounds = sorted({s["round"] for s in sessions}, key=to_number)
    round_text = "、".join(f"第{r}回" for r in rounds)

    # 表題と目的（最初の回の目的を使う）
    lines = [f"# {round_text}ヒアリング 進行資料", "",
             "> 聞き手だけで使う資料です。仮説や評価を含むため、対象者には共有しません。", ""]
    purposes = [s["purpose"] for s in sessions if s["purpose"].strip()]
    if purposes:
        lines += [f"## {round_text}の目的", "", purposes[0].strip(), ""]

    # 対象者ごとの仮説
    lines += ["## 深掘りしたい課題の仮説", ""]
    for s in sessions:
        person = persons.get(s["person_id"], {"name": "（不明）"})
        lines += [f"### {person['name']}", ""]
        hyps = _hypotheses_for(s, data)
        if not hyps:
            lines += ["（仮説はまだありません）", ""]
        for h in hyps:
            lines += [f"**{h['label']}：{h['title']}**（{h['status']}）", ""]
            if h["body"].strip():
                lines += [h["body"].strip(), ""]
            examples = [e.strip() for e in h["examples"].splitlines() if e.strip()]
            if examples:
                lines += ["お聞きしたいことの例：", ""] + [f"- {e}" for e in examples] + [""]

    # 対象者ごとのタイムテーブル、要約、質問
    for s in sessions:
        person = persons.get(s["person_id"], {"name": "（不明）"})
        segments = sort_by_order([g for g in data["segments"] if g["session_id"] == s["session_id"]])
        questions = [q for q in data["questions"] if q["session_id"] == s["session_id"]]
        lines += [f"## {person['name']}：タイムテーブルと質問", ""]

        # 基本情報
        lines += ["| 項目 | 内容 |", "|---|---|",
                  f"| 実施日 | {_cell(s['held_on']) or '（未定）'} |",
                  f"| 時間 | {_cell(s['duration_min'])}分 |",
                  f"| 聞き手 | {_cell(s['interviewers'])} |", ""]

        # タイムテーブル
        lines += ["### タイムテーブル", "", "| 時間 | 内容 | 狙い |", "|---|---|---|"]
        for g in segments:
            lines.append(f"| {_range_text(g['start_min'], g['end_min'])} | {_cell(g['title'])} | {_cell(g['aim'])} |")
        lines.append("")

        # 当日画面に出す要約
        if s["screen_summary"].strip():
            lines += ["### 当日画面に出す要約", "", "```text", s["screen_summary"].strip(), "```", ""]

        # 区切りごとの質問
        lines += ["### 質問", ""]
        for g in segments:
            in_seg = [q for q in questions if q["segment_id"] == g["segment_id"]]
            if not in_seg:
                continue
            lines += [f"**{g['title']}（{_range_text(g['start_min'], g['end_min'])}）**", ""]
            lines += _question_table(in_seg) + [""]
        known = {g["segment_id"] for g in segments}
        rest = [q for q in questions if q["segment_id"] not in known]
        if rest:
            lines += ["**区切りに入っていない質問**", ""] + _question_table(rest) + [""]

        # 事前の依頼文と聞き手用のメモ
        if s["request_message"].strip():
            lines += ["### 事前の依頼文", "", "```text", s["request_message"].strip(), "```", ""]
        if s["memo"].strip():
            lines += ["### 聞き手用のメモ", "", s["memo"].strip(), ""]

    return "\n".join(lines).rstrip() + "\n"


def render_field(session_id: str, field: str) -> str:
    """回の1つの欄（要約や依頼文）をそのまま出す。

    Args:
        session_id: 回のID。
        field: "screen_summary"（本人向けの要約）か "request_message"（事前の依頼文）。

    Returns:
        str: 欄の文字列。本人に見せる内容だけを出す。
    """
    # 本人に見せてよい欄だけを許可する
    if field not in ("screen_summary", "request_message"):
        raise ValueError("出力できない欄です。")
    data = read_all()
    session = next((s for s in data["sessions"] if s["session_id"] == session_id), None)
    if session is None:
        return ""
    return (session[field] or "").strip() + "\n"


def save_export(name: str, text: str) -> str:
    """出力した Markdown を exports フォルダに保存する。

    Args:
        name: ファイル名の先頭（例：plan_round2）。
        text: 保存する内容。

    Returns:
        str: 保存したファイル名。
    """
    # 日時を付けて、前の出力を上書きしないようにする
    file_name = f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    (data_dir() / "exports" / file_name).write_text(text, encoding="utf-8")
    return file_name
