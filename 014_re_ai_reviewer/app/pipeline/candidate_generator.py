from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any

from app.core.azure_client import call_structured
from app.prompts.candidate_prompts import build_candidate_generation_prompt_package
from app.schemas.models import Candidate

if getattr(sys, "frozen", False):
    _APP_ROOT = Path(sys.executable).resolve().parent
else:
    _APP_ROOT = Path(__file__).resolve().parents[2]

_SEED_CSV_PATH = _APP_ROOT / "data" / "seed_review_points.csv"


def _load_seed_points() -> dict[str, list[str]]:
    """
    観点シードCSV（旧app由来のレビュー観点を統合したもの）を読み込み、
    perspective_type 別のチェックポイント辞書を返す

    Returns
    -----------------
    - by_type: dict[str, list[str]],   perspective_type をキーとするチェックポイント辞書

    """
    by_type: dict[str, list[str]] = {}
    if not _SEED_CSV_PATH.exists():
        return by_type
    with _SEED_CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            detail = (row.get("detail") or "").strip()
            if not detail:
                continue
            ptype = (row.get("perspective_type") or "").strip()
            by_type.setdefault(ptype, []).append(detail)
    return by_type


def generate_candidates(
    slides: list[dict[str, Any]],
    overall_intended_message: str,
    memory_hints: list[str],
) -> list[Candidate]:
    """
    資料全体のスライド画像から、指摘候補を複数生成する（候補生成層のエントリポイント）

    Args
    -----------------
    - slides: list[dict[str, Any]],     スライドデータ（slide_number, image_png_b64）のリスト
    - overall_intended_message: str,    資料全体で伝えたい内容
    - memory_hints: list[str],          review_memory層から取得した過去指摘の参考テキスト（空リスト可）

    Returns
    -----------------
    - candidates: list[Candidate],      生成された指摘候補のリスト

    """
    seed_points_by_type = _load_seed_points()
    package = build_candidate_generation_prompt_package(
        slides=slides,
        overall_intended_message=overall_intended_message,
        seed_points_by_type=seed_points_by_type,
        memory_hints=memory_hints,
    )
    result = call_structured(package)

    candidates: list[Candidate] = []
    for entry in result.get("candidates", []):
        try:
            candidates.append(Candidate(
                slide_number=int(entry.get("slide_number", 0)),
                issue=str(entry.get("issue", "")).strip(),
                evidence_hint=str(entry.get("evidence_hint", "")).strip(),
                category=str(entry.get("category", "")).strip(),
                severity_guess=str(entry.get("severity_guess", "medium")).strip() or "medium",
            ))
        except (TypeError, ValueError):
            # AIの出力が想定外の形式だった1件はスキップし、他の候補の処理は継続する
            continue
    return [c for c in candidates if c.issue]
