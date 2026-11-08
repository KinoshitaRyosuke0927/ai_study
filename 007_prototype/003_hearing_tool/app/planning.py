"""ヒアリングの回の時間配分の集計、警告、前回からの引き継ぎを計算する。"""

from .storage import read_all, split_ids

# 目安の時間が空欄の質問に使う時間（分）
DEFAULT_EST_MIN = {"◎": 2.0, "○": 1.0}

# 回が「実施した後」であることを表す状態
HELD_STATUSES = {"実施済み", "整理済み"}


def to_number(value: str, default: float = 0.0) -> float:
    """文字列を数値に変換する。

    Args:
        value: 変換する文字列。
        default: 変換できないときの値。

    Returns:
        float: 変換した数値。
    """
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def est_min_of(question: dict) -> float:
    """質問の目安の時間を返す。

    Args:
        question: questions の行。

    Returns:
        float: 目安の時間（分）。空欄なら優先度ごとの既定値。
    """
    # 入力があればそれを使い、なければ優先度から決める
    if str(question.get("est_min", "")).strip():
        return to_number(question["est_min"])
    return DEFAULT_EST_MIN.get(question.get("priority", ""), 1.0)


def sort_by_order(rows: list[dict]) -> list[dict]:
    """order 列の数値順に並べる。

    Args:
        rows: order 列を持つ行の一覧。

    Returns:
        list[dict]: 並べ替えた一覧。
    """
    return sorted(rows, key=lambda r: to_number(r.get("order", ""), 9999))


def analyze_session(session_id: str, data: dict | None = None) -> dict:
    """回のタイムテーブルを集計し、警告と引き継ぎの候補を返す。

    Args:
        session_id: 回のID。
        data: read_all() の結果。省略時は読み込む。

    Returns:
        dict: segments（区切りごとの集計）、unassigned（区切りのない質問の集計）、
            totals（全体の集計）、warnings（警告の一覧）、carryover（引き継ぎの候補）。
    """
    # データを読み込み、対象の回を探す
    data = data or read_all()
    session = next((s for s in data["sessions"] if s["session_id"] == session_id), None)
    if session is None:
        return {"error": "回が見つかりません。"}

    # この回の区切りと質問を取り出す
    segments = sort_by_order([s for s in data["segments"] if s["session_id"] == session_id])
    questions = [q for q in data["questions"] if q["session_id"] == session_id]
    warnings: list[str] = []

    # 区切りごとに、質問の数と時間を集計する
    segment_rows = []
    prev_end = None
    for seg in segments:
        start, end = to_number(seg["start_min"]), to_number(seg["end_min"])
        length = end - start
        in_seg = [q for q in questions if q["segment_id"] == seg["segment_id"]]
        must = [q for q in in_seg if q["priority"] == "◎"]
        must_min = sum(est_min_of(q) for q in must)
        all_min = sum(est_min_of(q) for q in in_seg)
        seg_warnings = []

        # ◎の質問だけで区切りの長さを超えていないか確かめる
        if length > 0 and must_min > length:
            seg_warnings.append(f"◎の質問だけで{must_min:g}分あり、区切りの{length:g}分を超えています。")
        # 時間が逆転していないか、前の区切りと重なっていないか確かめる
        if length < 0:
            seg_warnings.append("終了が開始より前になっています。")
        if prev_end is not None and start < prev_end:
            seg_warnings.append("前の区切りと時間が重なっています。")
        prev_end = end

        warnings.extend(f"「{seg['title']}」：{w}" for w in seg_warnings)
        segment_rows.append({
            "segment_id": seg["segment_id"],
            "title": seg["title"],
            "length_min": length,
            "must_count": len(must),
            "optional_count": len(in_seg) - len(must),
            "must_min": must_min,
            "all_min": all_min,
            "warnings": seg_warnings,
        })

    # 区切りに入っていない質問を集計する
    known_segments = {s["segment_id"] for s in segments}
    unassigned = [q for q in questions if q["segment_id"] not in known_segments]
    if unassigned:
        warnings.append(f"区切りに入っていない質問が{len(unassigned)}件あります。")

    # 全体の時間を予定の時間と比べる
    duration = to_number(session["duration_min"])
    planned = sum(r["length_min"] for r in segment_rows)
    must_total = sum(est_min_of(q) for q in questions if q["priority"] == "◎")
    all_total = sum(est_min_of(q) for q in questions)
    if duration and planned > duration:
        warnings.append(f"タイムテーブルの合計{planned:g}分が、予定の{duration:g}分を超えています。")
    if duration and must_total > duration:
        warnings.append(f"◎の質問だけで{must_total:g}分あり、予定の{duration:g}分を超えています。")

    return {
        "segments": segment_rows,
        "unassigned": {
            "count": len(unassigned),
            "must_min": sum(est_min_of(q) for q in unassigned if q["priority"] == "◎"),
        },
        "totals": {
            "duration_min": duration,
            "planned_min": planned,
            "must_count": sum(1 for q in questions if q["priority"] == "◎"),
            "optional_count": sum(1 for q in questions if q["priority"] != "◎"),
            "must_min": must_total,
            "all_min": all_total,
        },
        "warnings": warnings,
        "carryover": carryover_candidates(session, data),
    }


def previous_session(session: dict, data: dict) -> dict | None:
    """同じ対象者の、この回より前で最も新しい回を返す。

    Args:
        session: sessions の行。
        data: read_all() の結果。

    Returns:
        dict | None: 前の回。なければ None。
    """
    # 同じ対象者で、回の番号が小さいものを集める
    current = to_number(session["round"])
    earlier = [
        s for s in data["sessions"]
        if s["person_id"] == session["person_id"] and to_number(s["round"]) < current
    ]
    # 番号が最も大きい回を返す
    return max(earlier, key=lambda s: to_number(s["round"]), default=None)


def carryover_candidates(session: dict, data: dict) -> dict:
    """前回から引き継ぐ候補を返す。

    Args:
        session: sessions の行。
        data: read_all() の結果。

    Returns:
        dict: questions（前回聞けなかった◎の質問）と
            hypotheses（この回でまだ扱っていない未確認・確認中の仮説）。
    """
    # 前回の◎の質問のうち、「聞いた」になっていないものを集める
    prev = previous_session(session, data)
    questions = []
    if prev:
        questions = [
            {"question_id": q["question_id"], "label": q["label"], "text": q["text"], "asked": q["asked"],
             "round": prev["round"]}
            for q in sort_by_order([q for q in data["questions"] if q["session_id"] == prev["session_id"]])
            if q["priority"] == "◎" and q["asked"] != "聞いた"
        ]

    # この回の区切りと質問でまだひも付いていない仮説を集める
    linked = set()
    for seg in data["segments"]:
        if seg["session_id"] == session["session_id"]:
            linked.update(split_ids(seg["hypothesis_ids"]))
    for q in data["questions"]:
        if q["session_id"] == session["session_id"]:
            linked.update(split_ids(q["hypothesis_ids"]))
    hypotheses = [
        {"hypothesis_id": h["hypothesis_id"], "label": h["label"], "title": h["title"], "status": h["status"]}
        for h in data["hypotheses"]
        if h["person_id"] == session["person_id"]
        and h["status"] in ("未確認", "確認中")
        and h["hypothesis_id"] not in linked
    ]
    return {"questions": questions, "hypotheses": hypotheses}


def home_summary() -> dict:
    """ホーム画面に出す、対象者ごとの状況と次にやることを返す。

    Returns:
        dict: persons（対象者ごとの状況）と todos（次にやることの一覧）。
    """
    data = read_all()
    persons = []
    todos = []

    for person in data["persons"]:
        pid = person["person_id"]
        sessions = sorted(
            [s for s in data["sessions"] if s["person_id"] == pid], key=lambda s: to_number(s["round"])
        )

        # 準備中の回は、時間配分の警告を確かめる
        for s in sessions:
            label = f"{person['name']} 第{s['round']}回"
            if s["status"] == "準備中":
                result = analyze_session(s["session_id"], data)
                if result.get("warnings"):
                    todos.append({"kind": "準備", "session_id": s["session_id"],
                                  "text": f"{label}：時間配分の警告が{len(result['warnings'])}件あります。"})
            # 実施した回は、聞けなかった◎の質問を確かめる
            if s["status"] in HELD_STATUSES:
                left = [q for q in data["questions"]
                        if q["session_id"] == s["session_id"] and q["priority"] == "◎" and q["asked"] != "聞いた"]
                if left:
                    todos.append({"kind": "整理", "session_id": s["session_id"],
                                  "text": f"{label}：聞いたことになっていない◎の質問が{len(left)}件あります。"})

                # 文字起こしがまだか、推敲が終わっていない発言があるかを確かめる
                utterances = [u for u in data["utterances"] if u["session_id"] == s["session_id"]]
                unreviewed = [u for u in utterances if u["review_status"] != "推敲済み"]
                if not utterances:
                    todos.append({"kind": "文字起こし", "session_id": s["session_id"],
                                  "text": f"{label}：文字起こしがまだありません。"})
                elif unreviewed:
                    todos.append({"kind": "文字起こし", "session_id": s["session_id"],
                                  "text": f"{label}：未推敲の発言が{len(unreviewed)}件あります。"})

        # 仮説とデータ台帳の確認状況を数える
        open_hyp = [h for h in data["hypotheses"] if h["person_id"] == pid and h["status"] in ("未確認", "確認中")]
        open_src = [d for d in data["data_sources"] if d["person_id"] == pid and d["confirmation"] != "確認済み"]
        issues = [i for i in data["issues"] if i["person_id"] == pid]
        if open_src:
            todos.append({"kind": "データ", "person_id": pid,
                          "text": f"{person['name']}：確認済みでないデータが{len(open_src)}件あります。"})

        persons.append({
            "person_id": pid,
            "name": person["name"],
            "role": person["role"],
            "sessions": [{"session_id": s["session_id"], "round": s["round"], "status": s["status"],
                          "held_on": s["held_on"]} for s in sessions],
            "open_hypotheses": len(open_hyp),
            "issues": len(issues),
            "open_data_sources": len(open_src),
        })

    return {"persons": persons, "todos": todos}
