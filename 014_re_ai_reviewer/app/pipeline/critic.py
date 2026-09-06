from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.core.azure_client import call_structured
from app.prompts.critic_prompts import build_critic_prompt_package
from app.schemas.models import Candidate, Finding

_VALID_VERDICTS = {"keep", "drop"}
_SEVERITY_RANK = {"high": 2, "medium": 1, "low": 0}


def _normalize_severity(severity: str) -> str:
    """severity文字列を high / medium / low の3段階に正規化する（廃止した blocker は high に丸める）"""
    value = (severity or "").strip().lower()
    if value == "blocker":
        return "high"
    return value if value in _SEVERITY_RANK else "medium"


def verify_candidates(
    scored_candidates: list[tuple[Candidate, float | None]],
    slides_by_number: dict[int, str],
    aspect: str = "content",
) -> list[Finding]:
    """
    候補を、スライド画像に照らして根拠検証し、Findingのリストを返す

    スライド単位でまとめて1回のLLM呼び出しにすることで、同じスライド画像を候補ごとに
    何度も送る無駄を避けている（010_ai_reviewer の画像編集提案がスライド単位で並列実行する
    設計と揃えている）。

    Args
    -----------------
    - scored_candidates: list[tuple[Candidate, float | None]],   候補と上司らしさスコアのペア
        （aspect="content" の場合は manager_ranker層が出したスコア、aspect="design" の場合は
        上司嗜好スコアリングを行わないため常に None）
    - slides_by_number: dict[int, str],                    slide_number をキーとするPNG画像Base64辞書
    - aspect: str,                                          "content" または "design"。Findingに
        そのままセットされ、design の場合は manager_likeness ではなく severity で並べ替える

    Returns
    -----------------
    - findings: list[Finding],   verdict="keep"となった指摘のみを返す
        （contentはmanager_likeness降順、designはseverity降順）

    """
    if not scored_candidates:
        return []

    by_slide: dict[int, list[tuple[int, Candidate, float | None]]] = defaultdict(list)
    for original_index, (candidate, likeness) in enumerate(scored_candidates):
        by_slide[candidate.slide_number].append((original_index, candidate, likeness))

    def _verify_slide(slide_number: int, items: list[tuple[int, Candidate, float | None]]) -> list[Finding]:
        """1スライド分の候補をまとめて検証する（スライド単位で並列実行するためのワーカー関数）"""
        slide_image_b64 = slides_by_number.get(slide_number)
        if not slide_image_b64:
            # 対応する画像が見つからないスライド番号は検証不能のためスキップする
            return []

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

        slide_findings: list[Finding] = []
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

            # likeness は content 群では 0.0〜1.0 の値、design 群では None（上司嗜好スコアリング未実施）
            clamped_likeness = None if likeness is None else max(0.0, min(1.0, likeness))

            slide_findings.append(Finding(
                slide_number=slide_number,
                issue=candidate.issue,
                evidence=str(entry.get("evidence", "") or candidate.evidence_hint),
                category=candidate.category,
                aspect=aspect,
                severity=_normalize_severity(candidate.severity_guess),
                manager_likeness=clamped_likeness,
                confidence=confidence,
                verdict=verdict,
                critic_comment=str(entry.get("critic_comment", "")),
                suggestion=str(entry.get("suggestion", "")),
            ))
        return slide_findings

    # スライドごとのcritic呼び出しは互いに独立しているため並列実行する
    # （従来はスライド数ぶん直列に呼んでおり、スライド数が増えるほど処理時間が線形に伸びていた）
    findings: list[Finding] = []
    with ThreadPoolExecutor(max_workers=max(1, len(by_slide))) as executor:
        for slide_findings in executor.map(lambda pair: _verify_slide(*pair), by_slide.items()):
            findings.extend(slide_findings)

    if aspect == "design":
        # デザイン観点は上司らしさによる並べ替えを行わず、重要度（severity）順に並べる
        findings.sort(key=lambda f: _SEVERITY_RANK.get(f.severity, 0), reverse=True)
    else:
        findings.sort(key=lambda f: f.manager_likeness or 0.0, reverse=True)
    return findings
