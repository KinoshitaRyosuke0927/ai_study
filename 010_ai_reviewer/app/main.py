from __future__ import annotations

import asyncio
import uvicorn
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.prompt import (
    build_overall_per_type_prompt_packages_by_type,
    build_overall_per_type_summarize_prompt_package,
    build_revision_findings_text,
    build_revision_suggestion_prompt_package,
)
from app.renderer import render_pptx_to_images, images_to_base64_dict
from app.azure_ai_service import call_review


class SlideInput(BaseModel):
    slide_number: int
    image_jpeg_b64: str
    intended_message: str = ""


class ReviewRequest(BaseModel):
    overall_intended_message: str = ""
    slides: list[SlideInput]


class SuggestionSlideInput(BaseModel):
    slide_number: int
    image_jpeg_b64: str


class PerspectiveResult(BaseModel):
    type: str
    label: str
    summary: str


class SuggestionRequest(BaseModel):
    slides: list[SuggestionSlideInput]
    perspectives: list[PerspectiveResult]

# フロントエンドのHTMLパス
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
# 観点一覧
PTYPE_LABELS: dict[str, str] = {
    "overall":     "全体",
    "story":       "構成・表現",
    "plan":        "計画・戦略",
    "assignment":  "課題設定",
    "priority":    "優先度・差別化",
    "feasibility": "実現可能性",
    "evaluation":  "評価・検証",
}


# アプリケーション実行
app = FastAPI(title="AI PowerPoint Reviewer", version="1.0.0")

# CORS ミドルウェアを設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# 静的ファイルをマウント
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    """
    トップページを返す
    """
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/api/health")
def health() -> dict:
    """
    ヘルスチェックエンドポイント
    """
    return {"status": "ok"}


@app.post("/api/upload")
async def upload_pptx(file: UploadFile = File(...)) -> dict:
    """
    アップロードされたPowerPointファイルを, LibreOfficeによりPDF変換してスライドごとの画像を抽出する
    """
    # ファイル形式を検証
    if not file.filename or not file.filename.lower().endswith(".pptx"):
        # PowerPoint以外のファイルが選択されていた場合はエラー
        raise HTTPException(status_code=400, detail=".pptx ファイルを指定してください。")

    # ファイル読み込み
    file_bytes = await file.read()
    # ファイルのサイズが取得できなかった場合
    if not file_bytes:
        # エラーを報告
        raise HTTPException(status_code=400, detail="ファイルが空です。")

    with tempfile.TemporaryDirectory() as tmpdir:
        # 一時的にフォルダ作成
        work_dir = Path(tmpdir)
        try:
            # スライドを画像として保存
            slide_images = render_pptx_to_images(file_bytes, work_dir)
            # 画像のパスをByte文字列に変換
            images_b64 = images_to_base64_dict(slide_images)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    # 一覧用サムネイル画像
    thumbnails = [item["jpg"] for item in images_b64]
    # スライドごとの表示用画像 
    slide_pngs  = [item["png"] for item in images_b64]

    return {
        "slide_count": len(slide_images),
        "file_name": file.filename,
        "thumbnails": thumbnails,
        "slide_pngs": slide_pngs,
        "thumbnail_mime": "image/jpeg",
        "render_method": "libre_office",
    }


def _review_perspective(ptype: str, pkg: dict) -> dict:
    """
    1つのperspective_typeについて、Q&Aレビューと集約文章生成を順番に行う（同期処理）
    """

    # Step1: 観点ごとのQ&Aレビュー
    try:
        qa_result = call_review(pkg)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AIレビュー（全体観点評価）に失敗しました: {exc}") from exc

    reviews = qa_result.get("reviews", [])

    # Step2: Q&A結果を集約文章に変換
    label = PTYPE_LABELS.get(ptype, ptype)
    try:
        summary_result = call_review(build_overall_per_type_summarize_prompt_package(label, reviews))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AIレビュー（集約）に失敗しました: {exc}") from exc

    return {
        "type": ptype,
        "label": label,
        "summary": summary_result.get("summary", ""),
    }


@app.post("/api/review")
async def review_pptx(request: ReviewRequest) -> dict:
    """
    スライド画像と伝えたい内容をもとにAIがレビューを行い結果を返す
    """
    # スライド情報が読み取れなかった場合
    if not request.slides:
        raise HTTPException(status_code=400, detail="スライドデータがありません。")

    # レビュー対象のデータを取得
    data = request.model_dump()

    # perspective_typeごとにプレゼンテーション全体のレビューを行い、集約文章を生成する
    packages = build_overall_per_type_prompt_packages_by_type(data)
    # タブの表示順がPTYPE_LABELSの定義順になるよう並び替える
    ptype_order = list(PTYPE_LABELS.keys())
    packages.sort(key=lambda item: ptype_order.index(item[0]) if item[0] in ptype_order else len(ptype_order))
    perspectives = await asyncio.gather(
        *(asyncio.to_thread(_review_perspective, ptype, pkg) for ptype, pkg in packages)
    )

    # レスポンス作成
    return {
        "presentation_summary": {
            "perspectives": list(perspectives),
        },
        "slides": [],
    }


def _suggest_revision_for_slide(slide: dict, findings_text: str) -> dict:
    """
    1枚のスライドについて、修正方針提案をAIに問い合わせる（同期処理）
    """
    package = build_revision_suggestion_prompt_package(slide, findings_text)
    try:
        result = call_review(package)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AIレビュー（修正方針提案）に失敗しました: {exc}") from exc

    return {
        "slide_number": slide["slide_number"],
        "summary": result.get("summary", ""),
        "issues": result.get("issues", []),
        "actions": result.get("actions", []),
        "example_text": result.get("example_text", {}),
        "expected_outcome": result.get("expected_outcome", ""),
    }


@app.post("/api/suggest")
async def suggest_revision(request: SuggestionRequest) -> dict:
    """
    観点別レビュー結果とスライド画像をもとに、AIがスライドごとの修正方針を提案する
    """
    # スライド情報が読み取れなかった場合
    if not request.slides:
        raise HTTPException(status_code=400, detail="スライドデータがありません。")
    # レビュー結果が存在しない場合
    if not request.perspectives:
        raise HTTPException(status_code=400, detail="レビュー結果がありません。先にAIレビューを実行してください。")

    data = request.model_dump()
    findings_text = build_revision_findings_text(data["perspectives"])

    slide_suggestions = await asyncio.gather(
        *(asyncio.to_thread(_suggest_revision_for_slide, slide, findings_text) for slide in data["slides"])
    )

    return {
        "slide_suggestions": list(slide_suggestions),
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
