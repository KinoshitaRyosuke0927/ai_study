from __future__ import annotations

from app.core.azure_client import call_structured
from app.prompts.ranker_prompts import build_ranking_prompt_package
from app.schemas.models import Candidate

_VALID_SEVERITIES = {"blocker", "high", "medium", "low"}


def score_candidates(candidates: list[Candidate], memory_hints: list[str]) -> list[tuple[Candidate, float]]:
    """
    候補指摘リストに対して、上司らしさスコア（manager_likeness）と最終severityを付与し、スコア降順で返す

    設計メモ: アーキテクチャ設計書（docs/architecture_from_current_app.md）のStep5では
    「候補ペアをLLMに見せてどちらが上司らしいか判定する」pairwise方式をMVPとして挙げているが、
    候補数nに対しO(n^2)回のLLM呼び出しが必要になり実用速度を欠くため、本実装では
    「候補リスト全体を1回のLLM呼び出しでまとめてスコアリングする」方式に簡略化している。
    Phase3で実データを使ったpairwise reward modelに置き換える際は、この関数のインターフェース
    （Candidateのリストを受け取りスコア付きリストを返す）を変えずに中身だけ差し替えられる。

    Args
    -----------------
    - candidates: list[Candidate],           候補生成層が出した指摘候補のリスト
    - memory_hints: list[str],                review_memory層から取得した過去指摘の参考テキスト（空リスト可）

    Returns
    -----------------
    - scored: list[tuple[Candidate, float]],  (severityを更新したCandidate, manager_likeness) のスコア降順リスト

    """
    if not candidates:
        return []

    package = build_ranking_prompt_package(
        candidates=[c.model_dump() for c in candidates],
        memory_hints=memory_hints,
    )
    result = call_structured(package)

    scores_by_index: dict[int, dict] = {}
    for entry in result.get("scores", []):
        try:
            idx = int(entry.get("candidate_index"))
        except (TypeError, ValueError):
            continue
        scores_by_index[idx] = entry

    scored: list[tuple[Candidate, float]] = []
    for i, candidate in enumerate(candidates):
        entry = scores_by_index.get(i, {})
        try:
            likeness = float(entry.get("manager_likeness", 0.5))
        except (TypeError, ValueError):
            likeness = 0.5
        likeness = max(0.0, min(1.0, likeness))

        severity = str(entry.get("severity", candidate.severity_guess)).strip()
        if severity not in _VALID_SEVERITIES:
            severity = candidate.severity_guess if candidate.severity_guess in _VALID_SEVERITIES else "medium"

        updated = candidate.model_copy(update={"severity_guess": severity})
        scored.append((updated, likeness))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored
