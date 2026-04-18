"""
レビュアーごとの発話履歴・プロファイルの CSV 保存/読み込みモジュール

保存ファイル構成（すべて data/ フォルダの CSV ファイルに一元管理）:
  data/reviewer_feedback.csv    - レビュアーが過去に行ったコメント履歴（発表テキスト含む）
  data/reviewer_profile.csv     - レビュアーごとの傾向サマリー（feedback から自動生成）

CSV ファイルが存在しない場合は _append_csv / _write_csv 呼び出し時に自動生成する。
レビュアー削除時は delete_reviewer_history() で関連データを一括削除する。
"""
from __future__ import annotations

import csv
import json
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

# ---- ディレクトリ・ファイルパス ----
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)  # 存在しなければ自動作成

FEEDBACK_CSV = DATA_DIR / "reviewer_feedback.csv"
PROFILE_CSV  = DATA_DIR / "reviewer_profile.csv"

# ---- CSV フィールド定義 ----
FEEDBACK_FIELDS = [
    "feedback_id", "reviewer_id", "reviewer_name", "role",
    "created_at",
    "summary", "good_points_json", "improvement_points_json",
    "role_specific_concern", "questions_json", "next_actions_json",
    "transcript",  # 発表テキストを CSV に直接保存（改行は csv モジュールが自動クォート）
]
PROFILE_FIELDS = [
    "reviewer_id", "updated_at",
    "strengths_json", "weaknesses_json", "recurring_issues_json",
    "improved_points_json", "last_advice_json", "summary",
]

# ---- 表現ゆれ正規化辞書 ----
NORMALIZATION_MAP: dict[str, str] = {
    "結論が遅い":           "結論提示が遅い",
    "結論提示が遅い":       "結論提示が遅い",
    "最初に結論がない":     "結論提示が遅い",
    "結論が不明確":         "結論提示が遅い",
    "導入が長い":           "導入が長い",
    "前置きが長い":         "導入が長い",
    "イントロが長い":       "導入が長い",
    "専門用語が多い":       "専門用語の説明不足",
    "専門用語の説明がない": "専門用語の説明不足",
    "用語説明が不足":       "専門用語の説明不足",
    "用語の説明不足":       "専門用語の説明不足",
    "話すスピードが速い":   "話すスピードが速い",
    "話速が速い":           "話すスピードが速い",
    "話が速い":             "話すスピードが速い",
    "根拠が薄い":           "根拠の説明不足",
    "根拠が不足":           "根拠の説明不足",
    "根拠が弱い":           "根拠の説明不足",
    "根拠が乏しい":         "根拠の説明不足",
}

# プロファイル更新に使う直近フィードバック件数
RECENT_N: int = 5
# recurring_issues と判定する最低出現回数
RECURRING_THRESHOLD: int = 2


# ===========================================================================
# 内部ユーティリティ
# ===========================================================================

def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def _append_csv(path: Path, fields: list[str], row: dict) -> None:
    file_exists = path.exists()
    with open(path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def _normalize(text: str) -> str:
    for keyword, canonical in NORMALIZATION_MAP.items():
        if keyword in text:
            return canonical
    return text


def _normalize_list(items: list[str]) -> list[str]:
    return [_normalize(item) for item in items]


def _safe_json_loads(s: str, default=None) -> list:
    try:
        return json.loads(s) if s else (default if default is not None else [])
    except Exception:
        return default if default is not None else []


# ===========================================================================
# Feedback（レビュアーの発話履歴）
# ===========================================================================

def save_feedback(
    reviewer_id: str,
    reviewer_name: str,
    role: str,
    feedback: dict,
    transcript: str = "",
) -> str:
    """評価結果を reviewer_feedback.csv に追記する。ファイルがなければ自動作成。"""
    feedback_id = uuid.uuid4().hex[:8]
    row = {
        "feedback_id":             feedback_id,
        "reviewer_id":             reviewer_id,
        "reviewer_name":           reviewer_name,
        "role":                    role,
        "created_at":              datetime.now().isoformat(),
        "summary":                 feedback.get("summary", ""),
        "good_points_json":        json.dumps(feedback.get("good_points", []),        ensure_ascii=False),
        "improvement_points_json": json.dumps(feedback.get("improvement_points", []), ensure_ascii=False),
        "role_specific_concern":   feedback.get("role_specific_concern", ""),
        "questions_json":          json.dumps(feedback.get("questions", []),           ensure_ascii=False),
        "next_actions_json":       json.dumps(feedback.get("next_actions", []),        ensure_ascii=False),
        "transcript":              transcript,  # CSV に直接インライン保存
    }
    _append_csv(FEEDBACK_CSV, FEEDBACK_FIELDS, row)
    return feedback_id


def get_feedback_by_reviewer(reviewer_id: str, limit: int | None = None) -> list[dict]:
    """指定レビュアーのフィードバック履歴を新しい順で返す。"""
    rows = [r for r in _read_csv(FEEDBACK_CSV) if r.get("reviewer_id") == reviewer_id]
    rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return rows[:limit] if limit else rows


# ===========================================================================
# Reviewer Profile（レビュアーの傾向サマリー）
# ===========================================================================

def get_reviewer_profile(reviewer_id: str) -> dict | None:
    for r in _read_csv(PROFILE_CSV):
        if r.get("reviewer_id") == reviewer_id:
            return r
    return None


def upsert_reviewer_profile(reviewer_id: str, profile: dict) -> None:
    rows = _read_csv(PROFILE_CSV)
    updated = False
    for r in rows:
        if r.get("reviewer_id") == reviewer_id:
            r.update(profile)
            updated = True
            break
    if not updated:
        rows.append({"reviewer_id": reviewer_id, **profile})
    _write_csv(PROFILE_CSV, PROFILE_FIELDS, rows)


def build_reviewer_profile(reviewer_id: str) -> dict:
    """
    直近 RECENT_N 件のフィードバックからルールベースでプロファイルを生成し、
    reviewer_profile.csv を更新する。
    """
    feedbacks = get_feedback_by_reviewer(reviewer_id, limit=RECENT_N)
    if not feedbacks:
        return {}

    all_improvements: list[str] = []
    all_goods:        list[str] = []
    all_next_actions: list[str] = []

    for fb in feedbacks:
        all_improvements.extend(_normalize_list(_safe_json_loads(fb.get("improvement_points_json"))))
        all_goods.extend(        _normalize_list(_safe_json_loads(fb.get("good_points_json"))))
        all_next_actions.extend(                  _safe_json_loads(fb.get("next_actions_json")))

    imp_counter  = Counter(all_improvements)
    good_counter = Counter(all_goods)

    recurring_issues = [item for item, cnt in imp_counter.most_common() if cnt >= RECURRING_THRESHOLD]
    weaknesses       = [item for item, _   in imp_counter.most_common(5)]
    strengths        = [item for item, cnt in good_counter.most_common(5) if cnt >= RECURRING_THRESHOLD]

    # 最新フィードバックの good_points が、それ以前の improvement_points と重なれば「改善済み」
    improved_points: list[str] = []
    if len(feedbacks) >= 2:
        latest_goods = set(_normalize_list(_safe_json_loads(feedbacks[0].get("good_points_json"))))
        prev_imps: set[str] = set()
        for fb in feedbacks[1:]:
            prev_imps.update(_normalize_list(_safe_json_loads(fb.get("improvement_points_json"))))
        improved_points = sorted(latest_goods & prev_imps)

    review_count = len(feedbacks)
    profile: dict = {
        "updated_at":            datetime.now().isoformat(),
        "strengths_json":        json.dumps(strengths,        ensure_ascii=False),
        "weaknesses_json":       json.dumps(weaknesses,       ensure_ascii=False),
        "recurring_issues_json": json.dumps(recurring_issues, ensure_ascii=False),
        "improved_points_json":  json.dumps(improved_points,  ensure_ascii=False),
        "last_advice_json":      json.dumps(all_next_actions[:5], ensure_ascii=False),
        "summary": (
            f"過去{review_count}回のレビューから生成。"
            f"繰り返し指摘: {', '.join(recurring_issues[:3]) or 'なし'}"
        ),
    }
    upsert_reviewer_profile(reviewer_id, profile)
    return profile


# ===========================================================================
# 削除
# ===========================================================================

def reset_all_memories() -> None:
    """全レビュアーの記憶（フィードバック・プロファイル）をリセットする。レビュアー自体は削除しない。"""
    _write_csv(FEEDBACK_CSV, FEEDBACK_FIELDS, [])
    _write_csv(PROFILE_CSV,  PROFILE_FIELDS,  [])


def delete_reviewer_history(reviewer_id: str) -> None:
    """
    指定レビュアーに紐づく全データ（フィードバック・プロファイル）を CSV から削除する。
    レビュアー削除ボタン押下時に呼び出す。
    """
    feedbacks = _read_csv(FEEDBACK_CSV)
    _write_csv(FEEDBACK_CSV, FEEDBACK_FIELDS,
               [fb for fb in feedbacks if fb.get("reviewer_id") != reviewer_id])

    profiles = _read_csv(PROFILE_CSV)
    _write_csv(PROFILE_CSV, PROFILE_FIELDS,
               [p for p in profiles if p.get("reviewer_id") != reviewer_id])


# ===========================================================================
# プロンプト用コンテキスト生成
# ===========================================================================

def build_profile_context(profile: dict) -> str:
    """
    reviewer_profile の dict をプロンプト挿入用テキストに変換する。
    空のプロファイルに対しては空文字を返す。
    """
    strengths   = _safe_json_loads(profile.get("strengths_json"))
    weaknesses  = _safe_json_loads(profile.get("weaknesses_json"))
    recurring   = _safe_json_loads(profile.get("recurring_issues_json"))
    improved    = _safe_json_loads(profile.get("improved_points_json"))
    last_advice = _safe_json_loads(profile.get("last_advice_json"))

    if not any([strengths, weaknesses, recurring, improved, last_advice]):
        return ""

    lines = ["【あなた自身の過去のレビュー傾向（参考情報）】"]
    if strengths:
        lines.append(f"- 過去に褒めた点: {', '.join(strengths[:3])}")
    if weaknesses:
        lines.append(f"- 過去に指摘した弱み: {', '.join(weaknesses[:3])}")
    if recurring:
        lines.append(f"- 繰り返し指摘してきた点: {', '.join(recurring[:3])}")
    if improved:
        lines.append(f"- 前回から改善が見られた点: {', '.join(improved[:3])}")
    if last_advice:
        lines.append(f"- 前回の主なアドバイス: {', '.join(last_advice[:3])}")

    lines += [
        "",
        "今回の評価では、以下にも注目してください。",
        "- 前回より改善した点（改善を具体的に認めてください）",
        "- まだ繰り返されている課題（以前も指摘したことを踏まえてコメントしてください）",
        "- 今回新たに見つかった課題",
        "",
    ]
    return "\n".join(lines) + "\n\n"
