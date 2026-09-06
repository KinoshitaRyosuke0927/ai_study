from __future__ import annotations

import csv
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from app.core.azure_client import TECHNICAL_MODEL, call_structured
from app.pipeline.aspect import classify_aspect
from app.prompts.candidate_prompts import build_candidate_generation_prompt_package
from app.prompts.design_checklist_prompts import build_design_checklist_prompt_package
from app.prompts.technical_prompts import build_technical_candidate_prompt_package
from app.schemas.models import Candidate

if getattr(sys, "frozen", False):
    _APP_ROOT = Path(sys.executable).resolve().parent
else:
    _APP_ROOT = Path(__file__).resolve().parents[2]

_SEED_CSV_PATH = _APP_ROOT / "data" / "seed_review_points.csv"

_VALID_SEVERITIES = {"high", "medium", "low"}


def _normalize_severity(severity: str) -> str:
    """severity文字列を high / medium / low の3段階に正規化する（廃止した blocker は high に丸める）"""
    value = (severity or "").strip().lower()
    if value == "blocker":
        return "high"
    return value if value in _VALID_SEVERITIES else "medium"


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


def _parse_candidates(result: dict[str, Any]) -> list[Candidate]:
    """
    call_structuredが返した {"candidates": [...]} 形式のJSONを Candidate のリストに変換する
    （汎用候補生成・技術面候補生成の両方で共通利用）
    """
    candidates: list[Candidate] = []
    for entry in result.get("candidates", []):
        try:
            candidates.append(Candidate(
                slide_number=int(entry.get("slide_number", 0)),
                issue=str(entry.get("issue", "")).strip(),
                evidence_hint=str(entry.get("evidence_hint", "")).strip(),
                category=str(entry.get("category", "")).strip(),
                severity_guess=_normalize_severity(str(entry.get("severity_guess", "medium"))),
            ))
        except (TypeError, ValueError):
            # AIの出力が想定外の形式だった1件はスキップし、他の候補の処理は継続する
            continue
    return [c for c in candidates if c.issue]


def _run_content_perspective(
    perspective_type: str,
    checklist_items: list[str],
    slides: list[dict[str, Any]],
    overall_intended_message: str,
    memory_hints: list[str],
) -> list[Candidate]:
    """
    1つの内容観点タイプ（assignment / plan / story など）について、その観点に絞った候補生成を実行する（同期処理）
    """
    package = build_candidate_generation_prompt_package(
        slides=slides,
        overall_intended_message=overall_intended_message,
        perspective_type=perspective_type,
        checklist_items=checklist_items,
        memory_hints=memory_hints,
    )
    result = call_structured(package)
    return _parse_candidates(result)


def generate_candidates(
    slides: list[dict[str, Any]],
    overall_intended_message: str,
    memory_hints: list[str],
) -> list[Candidate]:
    """
    資料全体のスライド画像から、内容観点の指摘候補を複数生成する（候補生成層のエントリポイント）

    1回のAI呼び出しで全観点を見ると1回あたりの確認観点が多くなり指摘が浅くなるため、
    内容観点タイプ（assignment / evaluation / feasibility / overall / plan / priority / story）ごとに
    独立したLLM呼び出しへ分割し、各呼び出しはその観点だけに集中させる
    （デザイン観点の generate_design_candidates と同じ方針）。

    Args
    -----------------
    - slides: list[dict[str, Any]],     スライドデータ（slide_number, image_png_b64）のリスト
    - overall_intended_message: str,    資料全体で伝えたい内容
    - memory_hints: list[str],          review_memory層から取得した過去指摘の参考テキスト（空リスト可）

    Returns
    -----------------
    - candidates: list[Candidate],      生成された指摘候補のリスト（全観点タイプ分をまとめたもの）

    """
    # デザイン観点（character/colors/composition/figures/sentence）は generate_design_candidates で
    # 別途チェックリスト形式でレビューするため、ここでは内容観点タイプのみを対象にする
    content_points_by_type = {
        ptype: points
        for ptype, points in _load_seed_points().items()
        if classify_aspect(ptype) == "content" and points
    }
    if not content_points_by_type:
        return []

    # 観点タイプ数（最大7件）ぶん並列実行してレイテンシを抑える
    with ThreadPoolExecutor(max_workers=len(content_points_by_type)) as executor:
        futures = [
            executor.submit(
                _run_content_perspective,
                perspective_type=ptype,
                checklist_items=items,
                slides=slides,
                overall_intended_message=overall_intended_message,
                memory_hints=memory_hints,
            )
            for ptype, items in content_points_by_type.items()
        ]
        candidates: list[Candidate] = []
        for future in futures:
            candidates.extend(future.result())
    return candidates


def generate_technical_candidates(
    slides: list[dict[str, Any]],
    overall_intended_message: str,
) -> list[Candidate]:
    """
    資料内に開発・設計対象のアプリケーション／システムが含まれる場合、実装利用者・利用シーンを
    具体的に想像した上での技術的実現可能性の指摘候補を生成する（候補生成層のもう1つのエントリポイント）

    汎用の generate_candidates とは独立した別プロンプト・別モデル（TECHNICAL_MODEL）で実行する。
    対象アプリケーションが資料に含まれない場合はAI自身が空リストを返す設計になっている。

    Args
    -----------------
    - slides: list[dict[str, Any]],     スライドデータ（slide_number, image_png_b64）のリスト
    - overall_intended_message: str,    資料全体で伝えたい内容

    Returns
    -----------------
    - candidates: list[Candidate],      生成された技術面の指摘候補のリスト（対象アプリケーションがなければ空）

    """
    package = build_technical_candidate_prompt_package(
        slides=slides,
        overall_intended_message=overall_intended_message,
    )
    result = call_structured(package, model=TECHNICAL_MODEL)
    return _parse_candidates(result)


def _run_design_checklist(category: str, checklist_items: list[str], slides: list[dict[str, Any]]) -> list[Candidate]:
    """
    1つのデザイン観点カテゴリについて、チェックリスト形式のレビューを実行し Candidate のリストに変換する（同期処理）
    """
    package = build_design_checklist_prompt_package(category, checklist_items, slides)
    result = call_structured(package)

    candidates: list[Candidate] = []
    for item in result.get("results", []):
        for occ in item.get("occurrences", []):
            try:
                slide_number = int(occ.get("slide_number", 0))
            except (TypeError, ValueError):
                continue
            detail = str(occ.get("detail", "")).strip()
            if not detail:
                continue
            # 指摘観点（チェック項目の文言 = question）はプロンプト内部の判定用途に留め、
            # 画面表示する issue にはそのスライドで実際に見つかった指摘結果（detail）のみを入れる
            issue = detail
            severity_guess = _normalize_severity(str(occ.get("severity_guess", "medium")))
            candidates.append(Candidate(
                slide_number=slide_number,
                issue=issue,
                evidence_hint=detail,
                category=category,
                severity_guess=severity_guess,
            ))
    return candidates


def generate_design_candidates(slides: list[dict[str, Any]]) -> list[Candidate]:
    """
    資料のデザイン観点（character/colors/composition/figures/sentence）について、
    seed_review_points.csv のチェック項目を「必須チェックリスト」として1件ずつ確認し、
    指摘候補を生成する（候補生成層のもう1つのエントリポイント）

    汎用の generate_candidates が「観点ヒントを参考にしつつ自由に指摘を洗い出す」方式なのに対し、
    こちらは「カテゴリごとにチェック項目を全スライドへ機械的に照らし合わせる」方式にすることで、
    人が目で見て気づくような明白なデザイン上の問題の見落としを減らす。

    Args
    -----------------
    - slides: list[dict[str, Any]],     スライドデータ（slide_number, image_png_b64）のリスト

    Returns
    -----------------
    - candidates: list[Candidate],      生成されたデザイン観点の指摘候補のリスト

    """
    design_points_by_type = {
        ptype: points
        for ptype, points in _load_seed_points().items()
        if classify_aspect(ptype) == "design" and points
    }
    if not design_points_by_type:
        return []

    # カテゴリ数（character/colors/composition/figures/sentenceの最大5件）ぶん並列実行する
    with ThreadPoolExecutor(max_workers=len(design_points_by_type)) as executor:
        futures = [
            executor.submit(_run_design_checklist, category, items, slides)
            for category, items in design_points_by_type.items()
        ]
        candidates: list[Candidate] = []
        for future in futures:
            candidates.extend(future.result())
    return candidates
