from __future__ import annotations

# デザイン観点（010_ai_reviewerの pp_check_points.csv 由来のカテゴリ）
_DESIGN_CATEGORIES = {"character", "colors", "composition", "figures", "sentence"}


def classify_aspect(category: str) -> str:
    """
    指摘のカテゴリ文字列から、資料の「内容」に関する観点か「デザイン」に関する観点かを判定する

    区分は010_ai_reviewerの2つの観点CSV由来のカテゴリに合わせている:
    - デザイン観点（pp_check_points.csv由来）: character, colors, composition, figures, sentence
    - それ以外はすべて内容観点として扱う（assignment, evaluation, feasibility, overall, plan,
      priority, story に加え、014で新設した technical も含む）

    Args
    -----------------
    - category: str,   Candidate/Findingのcategory値

    Returns
    -----------------
    - aspect: str,      "content" または "design"

    """
    return "design" if (category or "").strip().lower() in _DESIGN_CATEGORIES else "content"
