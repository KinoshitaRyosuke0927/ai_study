from __future__ import annotations

from typing import Any

from app.pipeline import candidate_generator, critic, manager_ranker, review_memory
from app.schemas.models import Finding


def run_review(slides: list[dict[str, Any]], overall_intended_message: str) -> list[Finding]:
    """
    候補生成 → 過去レビュー参照 → 上司嗜好スコアリング → critic検証 の4層パイプラインを実行し、
    最終的なFindingリストを返す（同期処理。呼び出し側でスレッドに逃がすこと）

    Args
    -----------------
    - slides: list[dict[str, Any]],     スライドデータ（slide_number, image_png_b64）のリスト
    - overall_intended_message: str,    資料全体で伝えたい内容

    Returns
    -----------------
    - findings: list[Finding],          critic検証を通過した指摘事項（manager_likeness降順）

    """
    # Step1: 過去レビュー参照（review_log.jsonl が空の間は常に空リストが返り、後続はヒントなしで動く）
    memory_hints = review_memory.retrieve_similar_comments(overall_intended_message)

    # Step2: 候補生成（スライド全体を見て、指摘候補を幅広く複数生成）
    candidates = candidate_generator.generate_candidates(
        slides=slides,
        overall_intended_message=overall_intended_message,
        memory_hints=memory_hints,
    )
    if not candidates:
        return []

    # Step3: 上司嗜好スコアリング（manager_likenessでランク付け、severityを上司視点で補正）
    scored_candidates = manager_ranker.score_candidates(candidates, memory_hints)

    # Step4: critic検証（スライド画像に照らして根拠確認、根拠が薄い指摘はdropされる）
    slides_by_number = {slide["slide_number"]: slide["image_png_b64"] for slide in slides}
    findings = critic.verify_candidates(scored_candidates, slides_by_number)

    return findings
