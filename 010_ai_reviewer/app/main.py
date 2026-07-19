from __future__ import annotations

import asyncio
import base64
import uvicorn
import tempfile
from io import BytesIO
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from PIL import Image
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.prompt import (
    LAYOUT_GUIDANCE_SUFFIX,
    build_change_description_prompt_package,
    build_image_edit_instruction_prompt_package,
    build_overall_per_type_prompt_packages_by_type,
    build_overall_per_type_summarize_prompt_package,
    build_revision_findings_text,
)
from app.renderer import render_pptx_to_images, images_to_base64_dict
from app.azure_ai_service import call_image_edit, call_review


class SlideInput(BaseModel):
    slide_number: int
    image_jpeg_b64: str
    intended_message: str = ""


class ReviewRequest(BaseModel):
    overall_intended_message: str = ""
    slides: list[SlideInput]


class SuggestionSlideInput(BaseModel):
    slide_number: int
    image_png_b64: str


class PerspectiveResult(BaseModel):
    type: str
    label: str
    summary: str


class SuggestionRequest(BaseModel):
    slides: list[SuggestionSlideInput]
    perspectives: list[PerspectiveResult]


class ExportSlideInput(BaseModel):
    slide_number: int
    edited_image_b64: str


class ExportPdfRequest(BaseModel):
    slides: list[ExportSlideInput]

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
    1枚のスライドについて、指摘事項をもとに画像編集AIで修正後スライド画像と修正内容説明を生成する（同期処理）
    """
    slide_number = slide["slide_number"]
    original_image_b64 = slide["image_png_b64"]

    # Step1: 指摘事項を画像編集AI向けの指示文に変換
    instruction_package = build_image_edit_instruction_prompt_package(slide_number, findings_text)
    try:
        instruction_result = call_review(instruction_package)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AIレビュー（修正指示文生成）に失敗しました: {exc}") from exc
    edit_instruction = instruction_result.get("image_edit_instruction", "")
    # AIの出力内容によらず、余白確保のガイダンスを必ず付加する
    edit_instruction = f"{edit_instruction}\n{LAYOUT_GUIDANCE_SUFFIX}"

    # Step2: 画像編集AIで元スライド画像を修正
    try:
        edited_image_bytes = call_image_edit(edit_instruction, base64.b64decode(original_image_b64))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI画像修正に失敗しました: {exc}") from exc
    edited_image_b64 = base64.b64encode(edited_image_bytes).decode()

    # Step3: 修正前後の画像を比較し、実際に施した修正内容の説明を生成
    description_package = build_change_description_prompt_package(slide_number, original_image_b64, edited_image_b64)
    try:
        description_result = call_review(description_package)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AIレビュー（修正内容説明生成）に失敗しました: {exc}") from exc

    return {
        "slide_number": slide_number,
        "edited_image_b64": edited_image_b64,
        "description": description_result.get("description", ""),
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

    # スライド枚数がPythonのデフォルトスレッドプール上限を超えても待機が発生しないよう、
    # スライド枚数分のワーカーを持つ専用スレッドプールで並列実行する
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=len(data["slides"])) as executor:
        slide_suggestions = await asyncio.gather(
            *(
                loop.run_in_executor(executor, _suggest_revision_for_slide, slide, findings_text)
                for slide in data["slides"]
            )
        )

    return {
        "slide_suggestions": list(slide_suggestions),
    }


def _build_pdf_from_slides(slides: list[dict]) -> bytes:
    """
    修正後スライド画像一覧をまとめて1つのPDFファイルに変換する（同期処理）
    """
    images = [
        Image.open(BytesIO(base64.b64decode(slide["edited_image_b64"]))).convert("RGB")
        for slide in slides
    ]
    buffer = BytesIO()
    images[0].save(buffer, format="PDF", save_all=True, append_images=images[1:])
    return buffer.getvalue()


@app.post("/api/suggest/export-pdf")
async def export_suggestion_pdf(request: ExportPdfRequest) -> Response:
    """
    修正後スライド画像一覧をまとめたPDFファイルを生成して返す
    """
    # スライド情報が読み取れなかった場合
    if not request.slides:
        raise HTTPException(status_code=400, detail="スライドデータがありません。")

    data = request.model_dump()
    # スライドを番号順に並べる
    slides = sorted(data["slides"], key=lambda s: s["slide_number"])

    try:
        pdf_bytes = await asyncio.to_thread(_build_pdf_from_slides, slides)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDFファイルの生成に失敗しました: {exc}") from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="revision_suggestion.pdf"'},
    )


# exe起動用
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
