from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.core.azure_client import call_structured
from app.prompts.critic_prompts import build_critic_prompt_package
from app.schemas.models import Candidate, Finding

_VALID_VERDICTS = {"keep", "drop"}


def verify_candidates(
    scored_candidates: list[tuple[Candidate, float]],
    slides_by_number: dict[int, str],
) -> list[Finding]:
    """
    上司嗜好スコアリング済みの候補を、スライド画像に照らして根拠検証し、Findingのリストを返す

    スライド単位でまとめて1回のLLM呼び出しにすることで、同じスライド画像を候補ごとに
    何度も送る無駄を避けている（010_ai_reviewer の画像編集提案がスライド単位で並列実行する
    設計と揃えている）。

    Args
    -----------------
    - scored_candidates: list[tuple[Candidate, float]],   manager_ranker層が出したスコア付き候補
    - slides_by_number: dict[int, str],                    slide_number をキーとするPNG画像Base64辞書

    Returns
    -----------------
    - findings: list[Finding],   verdict="keep"となった指摘のみを manager_likeness 降順で返す

    """
    if not scored_candidates:
        return []

    by_slide: dict[int, list[tuple[int, Candidate, float]]] = defaultdict(list)
    for original_index, (candidate, likeness) in enumerate(scored_candidates):
        by_slide[candidate.slide_number].append((original_index, candidate, likeness))

    findings: list[Finding] = []
    for slide_number, items in by_slide.items():
        slide_image_b64 = slides_by_number.get(slide_number)
        if not slide_image_b64:
            # 対応する画像が見つからないスライド番号は検証不能のためスキップする
            continue

        package = build_critic_prompt_package(
            slide_number=slide_number,
            slide_image_b64=slide_image_b64,
            candidates=[c.model_dump() for _, c, _ in items],
        )
        result = call_structured(package)

        verdicts_by_index: dict[int, dict[str, Any]] = {}
        for entry in result.get("verdicts", []):
            try:
                idx = int(entry.get("candidate_index"))
            except (TypeError, ValueError):
                continue
            verdicts_by_index[idx] = entry

        for local_index, (_, candidate, likeness) in enumerate(items):
            entry = verdicts_by_index.get(local_index, {})
            verdict = str(entry.get("verdict", "drop")).strip()
            if verdict not in _VALID_VERDICTS:
                verdict = "drop"
            if verdict != "keep":
                continue

            try:
                confidence = max(0.0, min(1.0, float(entry.get("confidence", 0.5))))
            except (TypeError, ValueError):
                confidence = 0.5

            findings.append(Finding(
                slide_number=slide_number,
                issue=candidate.issue,
                evidence=str(entry.get("evidence", "") or candidate.evidence_hint),
                category=candidate.category,
                severity=candidate.severity_guess,
                manager_likeness=likeness,
                confidence=confidence,
                verdict=verdict,
                critic_comment=str(entry.get("critic_comment", "")),
                suggestion=str(entry.get("suggestion", "")),
            ))

    findings.sort(key=lambda f: f.manager_likeness, reverse=True)
    return findings
