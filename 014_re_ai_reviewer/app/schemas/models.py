from __future__ import annotations

from pydantic import BaseModel


class SlideInput(BaseModel):
    """アップロード済みスライド1枚分の入力データ"""
    slide_number: int
    image_png_b64: str
    image_jpeg_b64: str = ""


class ReviewRequest(BaseModel):
    """レビューAPIへのリクエストボディ"""
    overall_intended_message: str = ""
    slides: list[SlideInput]


class Candidate(BaseModel):
    """候補生成層が出す1件の指摘候補（上司らしさ判定・critic検証を経る前の段階）"""
    slide_number: int
    issue: str
    evidence_hint: str = ""
    category: str = ""
    severity_guess: str = "medium"  # blocker / high / medium / low


class Finding(BaseModel):
    """critic検証まで通過した最終的な指摘事項（UI表示用）"""
    slide_number: int
    issue: str
    evidence: str = ""
    category: str = ""
    aspect: str = "content"  # "content"（資料の内容）または "design"（資料のデザイン）
    severity: str = "medium"
    # デザイン観点は上司嗜好スコアリングを行わないため manager_likeness は None になる
    manager_likeness: float | None = None
    confidence: float = 0.5
    verdict: str = "keep"  # keep / drop
    critic_comment: str = ""
    suggestion: str = ""


class SuggestSlideInput(BaseModel):
    """修正方針提案（画像編集）APIへの入力スライド1枚分のデータ"""
    slide_number: int
    image_png_b64: str


class SuggestRequest(BaseModel):
    """修正方針提案APIへのリクエストボディ（/api/review で得たFinding一覧をそのまま渡す）"""
    slides: list[SuggestSlideInput]
    findings: list[Finding]


class ExportSlideInput(BaseModel):
    """修正後スライドPDFエクスポートAPIへの入力スライド1枚分のデータ"""
    slide_number: int
    edited_image_b64: str


class ExportPdfRequest(BaseModel):
    """修正後スライドPDFエクスポートAPIへのリクエストボディ"""
    slides: list[ExportSlideInput]


class ReviewMemoryEntry(BaseModel):
    """review_memory層が読み書きする過去レビュー指摘ログの1件

    現時点ではデータ未整備のため review_log.jsonl は空でよい（review_memory.py が
    0件フォールバックで動作する）。データが整備され次第、このスキーマに沿って
    追記していけば、候補生成・critic層のプロンプトに自動的に反映される。
    """
    slide_summary: str
    category: str
    comment: str
    severity: str = "medium"
    accepted: bool | None = None
