from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.pipeline import candidate_generator, critic, manager_ranker, review_memory
from app.pipeline.aspect import classify_aspect
from app.schemas.models import Candidate, Finding

# デザイン観点はチェックリスト方式で網羅的に候補を出す分ノイズが増えやすいため、
# 画面には重大度の高い指摘のみを表示する（内容観点は severity を絞らず全件表示する）
_DESIGN_DISPLAY_SEVERITIES = {"blocker", "high"}


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
    - findings: list[Finding],          critic検証を通過した指摘事項。内容観点は全severityを
                                          manager_likeness降順で、デザイン観点はseverity（blocker/highのみ）降順で返す

    """
    # Step1: 過去レビュー参照（review_log.jsonl が空の間は常に空リストが返り、後続はヒントなしで動く）
    memory_hints = review_memory.retrieve_similar_comments(overall_intended_message)

    # Step2: 候補生成
    #   - 汎用の候補生成（内容観点のみ。観点シードを参考例として、AIが自由に幅広く指摘を洗い出す）
    #   - 技術面の候補生成（資料内に開発対象アプリがある場合のみ、実装利用者・利用シーンを
    #     具体的に想像した上での実現可能性レビュー。別プロンプト・別モデルで独立実行）
    #   - デザイン面の候補生成（character/colors/composition/figures/sentence の各チェック項目を
    #     「必須チェックリスト」として全スライドに機械的に照らし合わせる。自由生成だと見た目の
    #     明白な問題を見落とすことがあったため、この観点だけは網羅チェック方式にしている）
    # 互いに依存しない別々のLLM呼び出しのため、並列実行してレイテンシを抑える
    with ThreadPoolExecutor(max_workers=3) as executor:
        general_future = executor.submit(
            candidate_generator.generate_candidates,
            slides=slides,
            overall_intended_message=overall_intended_message,
            memory_hints=memory_hints,
        )
        technical_future = executor.submit(
            candidate_generator.generate_technical_candidates,
            slides=slides,
            overall_intended_message=overall_intended_message,
        )
        design_future = executor.submit(candidate_generator.generate_design_candidates, slides=slides)
        candidates = general_future.result() + technical_future.result() + design_future.result()

    if not candidates:
        return []

    # 資料の「内容」に関する観点と「デザイン」に関する観点を分けて以降を処理する。
    # デザイン観点（character/colors/composition/figures/sentence）は、口調・重視観点といった
    # 個人差ではなく客観的なルールに基づく指摘が中心のため、上司嗜好スコアリングは行わない。
    content_candidates = [c for c in candidates if classify_aspect(c.category) == "content"]
    design_candidates = [c for c in candidates if classify_aspect(c.category) == "design"]

    slides_by_number = {slide["slide_number"]: slide["image_png_b64"] for slide in slides}

    def _run_content_pipeline() -> list[Finding]:
        if not content_candidates:
            return []
        # Step3a: 上司嗜好スコアリング（manager_likenessでランク付け、severityを上司視点で補正）
        scored_content = manager_ranker.score_candidates(content_candidates, memory_hints)
        # Step4a: critic検証（スライド画像に照らして根拠確認、根拠が薄い指摘はdropされる）
        return critic.verify_candidates(scored_content, slides_by_number, aspect="content")

    def _run_design_pipeline() -> list[Finding]:
        if not design_candidates:
            return []
        # Step3b: デザイン観点は上司嗜好スコアリングを行わず、候補生成時点のseverityをそのまま使う
        scored_design: list[tuple[Candidate, float | None]] = [(c, None) for c in design_candidates]
        # Step4b: critic検証（内容観点と同様、根拠確認は行う）
        design_findings = critic.verify_candidates(scored_design, slides_by_number, aspect="design")
        # デザイン観点はチェックリスト方式で件数が多くなりやすいため、重大度の高いものだけ残す
        return [f for f in design_findings if f.severity in _DESIGN_DISPLAY_SEVERITIES]

    # 内容観点パイプライン（ランキング+critic）とデザイン観点パイプライン（critic）は互いに独立
    # しているため並列実行する
    with ThreadPoolExecutor(max_workers=2) as executor:
        content_future = executor.submit(_run_content_pipeline)
        design_future = executor.submit(_run_design_pipeline)
        return content_future.result() + design_future.result()
