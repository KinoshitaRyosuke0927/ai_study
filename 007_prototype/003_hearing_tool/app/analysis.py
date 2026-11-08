"""横断表示、評価表、提案用の出力を作る。

AI は使わず、利用者が付けたテーマ、評価、ひも付けをもとに集計する。
"""

import re
from collections import defaultdict

from .planning import HELD_STATUSES, sort_by_order
from .storage import read_all, split_ids

# 評価の点数（合計点で課題を並べ替えるために使う）
RATING_SCORE = {"◎": 3, "○": 2, "△": 1, "×": 0}

# 評価表で、既定では表示しない課題の状態
HIDDEN_STATUSES = {"見送り"}


def overview() -> dict:
    """対象者をまたいだ状況を返す。

    Returns:
        dict: persons（対象者ごとの集計）、themes（テーマごとの課題）、
            no_theme（テーマのない課題）、shared_solutions（複数の人の課題にひも付く解決策の候補）、
            issues_without_data（データがひも付いていない課題）、unconfirmed_sources（確認済みでないデータ）。
    """
    data = read_all()
    persons = {p["person_id"]: p for p in data["persons"]}
    issues = [i for i in data["issues"] if i["status"] not in HIDDEN_STATUSES]

    # 対象者ごとに、回、仮説、課題、データの状況を数える
    person_rows = []
    for pid, person in persons.items():
        hyps = [h for h in data["hypotheses"] if h["person_id"] == pid]
        p_issues = [i for i in data["issues"] if i["person_id"] == pid]
        sources = [d for d in data["data_sources"] if d["person_id"] == pid]
        person_rows.append({
            "person_id": pid,
            "name": person["name"],
            "held_sessions": sum(1 for s in data["sessions"] if s["person_id"] == pid and s["status"] in HELD_STATUSES),
            "sessions": sum(1 for s in data["sessions"] if s["person_id"] == pid),
            "hypotheses": _count_by(hyps, "status"),
            "issues": _count_by(p_issues, "status"),
            "sources_total": len(sources),
            "sources_confirmed": sum(1 for d in sources if d["confirmation"] == "確認済み"),
        })

    # テーマごとに課題をまとめ、何人の課題があるかを数える
    by_theme: dict[str, list[dict]] = defaultdict(list)
    for issue in issues:
        if issue["theme"].strip():
            by_theme[issue["theme"].strip()].append(issue)
    themes = sorted(
        [{
            "theme": theme,
            "person_count": len({i["person_id"] for i in rows}),
            "issues": [_issue_brief(i, persons) for i in rows],
        } for theme, rows in by_theme.items()],
        key=lambda t: (-t["person_count"], -len(t["issues"]), t["theme"]),
    )
    no_theme = [_issue_brief(i, persons) for i in issues if not i["theme"].strip()]

    # 複数の人の課題にひも付く解決策の候補（または同じ名前の手法）を探す
    issue_by_id = {i["issue_id"]: i for i in data["issues"]}
    by_method: dict[str, list[dict]] = defaultdict(list)
    for sol in data["solutions"]:
        by_method[_normalize(sol["method"])].append(sol)
    shared = []
    for rows in by_method.values():
        linked = [issue_by_id[i] for sol in rows for i in split_ids(sol["issue_ids"]) if i in issue_by_id]
        names = sorted({persons.get(i["person_id"], {}).get("name", "") for i in linked})
        if len(names) >= 2:
            shared.append({"method": rows[0]["method"], "persons": names,
                           "issues": [_issue_brief(i, persons) for i in linked]})

    # データがひも付いていない課題と、確認済みでないデータ
    linked_issue_ids = {i for d in data["data_sources"] for i in split_ids(d["issue_ids"])}
    without_data = [_issue_brief(i, persons) for i in issues if i["issue_id"] not in linked_issue_ids]
    unconfirmed = [
        {**{k: d[k] for k in ("source_id", "name", "location", "confirmation", "person_id")},
         "person": persons.get(d["person_id"], {}).get("name", "")}
        for d in data["data_sources"] if d["confirmation"] != "確認済み"
    ]

    return {
        "persons": person_rows,
        "themes": themes,
        "no_theme": no_theme,
        "shared_solutions": shared,
        "issues_without_data": without_data,
        "unconfirmed_sources": unconfirmed,
    }


def evaluation_matrix() -> dict:
    """評価表の内容を返す。

    Returns:
        dict: criteria（観点の一覧）と issues（課題ごとの評価と合計点）。
    """
    data = read_all()
    persons = {p["person_id"]: p for p in data["persons"]}
    criteria = sort_by_order(data["criteria"])
    names = [c["criterion"] for c in criteria]

    # 課題ごとに、観点ごとの評価を集める
    by_issue: dict[str, dict] = defaultdict(dict)
    for ev in data["evaluations"]:
        by_issue[ev["issue_id"]][ev["criterion"]] = ev

    rows = []
    for issue in data["issues"]:
        cells = by_issue.get(issue["issue_id"], {})
        rated = [cells[n]["rating"] for n in names if n in cells and cells[n]["rating"] in RATING_SCORE]
        rows.append({
            **_issue_brief(issue, persons),
            "cells": {n: {"evaluation_id": cells[n]["evaluation_id"], "rating": cells[n]["rating"],
                          "comment": cells[n]["comment"]} for n in names if n in cells},
            "score": sum(RATING_SCORE[r] for r in rated),
            "rated_count": len(rated),
            "solutions": sum(1 for s in data["solutions"] if issue["issue_id"] in split_ids(s["issue_ids"])),
            "sources": sum(1 for d in data["data_sources"] if issue["issue_id"] in split_ids(d["issue_ids"])),
        })

    # 合計点の高い順、同点なら評価した観点の多い順に並べる
    rows.sort(key=lambda r: (-r["score"], -r["rated_count"], r["person"], r["title"]))
    return {"criteria": criteria, "issues": rows, "max_score": 3 * len(names)}


def render_proposal(anonymize: bool) -> str:
    """提案用の整理を Markdown で作る。

    公開範囲が「提案に使う」の課題だけを含める。発言そのもの（本人の負担感）は含めない。

    Args:
        anonymize: True なら、対象者の名前を「メンバー1」などに置き換える。

    Returns:
        str: Markdown の文字列。
    """
    data = read_all()
    persons = {p["person_id"]: p for p in data["persons"]}
    matrix = evaluation_matrix()
    criteria = [c["criterion"] for c in matrix["criteria"]]
    targets = {i["issue_id"] for i in data["issues"] if i["visibility"] == "提案に使う"}
    rows = [r for r in matrix["issues"] if r["issue_id"] in targets]
    issue_by_id = {i["issue_id"]: i for i in data["issues"]}

    # 名前を伏せるための置き換え表を作る（「石井さん」と「石井」の両方を置き換える）
    alias = {}
    for n, pid in enumerate(sorted({r["person_id"] for r in rows}), start=1):
        alias[pid] = f"メンバー{n}" if anonymize else persons.get(pid, {}).get("name", "")

    def mask(text: str) -> str:
        """文章の中の対象者の名前を置き換える。

        Args:
            text: 文章。

        Returns:
            str: 名前を置き換えた文章。
        """
        if not anonymize:
            return text or ""
        result = text or ""
        for pid, name_alias in alias.items():
            name = persons.get(pid, {}).get("name", "")
            for variant in sorted({name, name.removesuffix("さん")}, key=len, reverse=True):
                if variant:
                    result = result.replace(variant, name_alias)
        return result

    def cell(text: str) -> str:
        """表のセルに入れられる形に変える。

        Args:
            text: 文字列。

        Returns:
            str: 縦線をエスケープし、改行を <br> にした文字列。
        """
        return mask(text).replace("|", "\\|").replace("\r\n", "\n").replace("\n", "<br>")

    lines = ["# 課題と解決策の候補（提案用の整理）", ""]
    if anonymize:
        lines += ["> 対象者の名前は「メンバー1」などに置き換えています。", ""]
    if not rows:
        lines += ["公開範囲が「提案に使う」の課題がありません。課題カードの公開範囲を変更してください。"]
        return "\n".join(lines) + "\n"

    # 評価の一覧表
    lines += ["## 評価の一覧", "", "| 課題 | 対象者 | " + " | ".join(criteria) + " | 合計 |",
              "|---|---|" + "---|" * len(criteria) + "---|"]
    for r in rows:
        ratings = [r["cells"].get(c, {}).get("rating", "") or "-" for c in criteria]
        lines.append(f"| {cell(r['title'])} | {alias[r['person_id']]} | " + " | ".join(ratings)
                     + f" | {r['score']}/{matrix['max_score']} |")
    lines += ["", "評価：◎＝3点、○＝2点、△＝1点、×＝0点", ""]

    # 課題ごとの詳細
    lines += ["## 課題ごとの詳細", ""]
    for r in rows:
        issue = issue_by_id[r["issue_id"]]
        lines += [f"### {mask(issue['title'])}（{alias[r['person_id']]}）", ""]
        detail = [("テーマ", issue["theme"]), ("状態", issue["status"]), ("具体的な場面", issue["scene"]),
                  ("頻度", issue["frequency"]), ("1回あたりの時間", issue["time_per"]),
                  ("負担の中心となる工程", issue["core_step"]), ("判断の材料と基準", issue["judgment"]),
                  ("既存の工夫や自動化", issue["workaround"]), ("問題が起きた場合の影響", issue["impact"]),
                  ("発言の確度", issue["certainty"])]
        lines += ["| 項目 | 内容 |", "|---|---|"] + [f"| {k} | {cell(v)} |" for k, v in detail if v.strip()] + [""]

        # 評価の理由
        comments = [(c, r["cells"][c]) for c in criteria if c in r["cells"] and r["cells"][c]["comment"].strip()]
        if comments:
            lines += ["**評価の理由**", ""] + [f"- {c}（{v['rating'] or '-'}）：{mask(v['comment'])}" for c, v in comments] + [""]

        # 解決策の候補
        sols = [s for s in data["solutions"] if r["issue_id"] in split_ids(s["issue_ids"])]
        if sols:
            lines += ["**解決策の候補**", "", "| 手法 | 生成AI | 必要なデータ | 懸念点 |", "|---|---|---|---|"]
            lines += [f"| {cell(s['method'])} | {'使う' if s['uses_genai'] == '1' else '使わない'} | "
                      f"{cell(s['required_data'])} | {cell(s['concern'])} |" for s in sols] + [""]

        # ひも付くデータ
        srcs = [d for d in data["data_sources"] if r["issue_id"] in split_ids(d["issue_ids"])]
        if srcs:
            lines += ["**データ**", "", "| データ | 形式 | 期間 | 件数 | 利用の制限 | 確認 |", "|---|---|---|---|---|---|"]
            lines += [f"| {cell(d['name'])} | {cell(d['format'])} | {cell(d['period'])} | {cell(d['volume'])} | "
                      f"{cell(d['restriction'])} | {d['confirmation']} |" for d in srcs] + [""]

    return "\n".join(lines).rstrip() + "\n"


def _count_by(rows: list[dict], column: str) -> dict[str, int]:
    """列の値ごとに行を数える。

    Args:
        rows: 行の一覧。
        column: 数える列。

    Returns:
        dict[str, int]: 値ごとの件数。
    """
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row[column] or "（空欄）"] += 1
    return dict(counts)


def _issue_brief(issue: dict, persons: dict) -> dict:
    """課題の要点を返す。

    Args:
        issue: issues の行。
        persons: 対象者のIDごとの行。

    Returns:
        dict: 一覧に出す項目。
    """
    return {
        "issue_id": issue["issue_id"],
        "person_id": issue["person_id"],
        "person": persons.get(issue["person_id"], {}).get("name", ""),
        "title": issue["title"],
        "theme": issue["theme"],
        "status": issue["status"],
        "certainty": issue["certainty"],
        "visibility": issue["visibility"],
    }


def _normalize(text: str) -> str:
    """手法の名前を比べやすい形にする（空白を除く）。

    Args:
        text: 手法の名前。

    Returns:
        str: 空白を除いた文字列。
    """
    return re.sub(r"\s+", "", text or "")
