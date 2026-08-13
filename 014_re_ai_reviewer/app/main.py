from __future__ import annotations

import asyncio
import base64
import tempfile
import uvicorn
from io import BytesIO
from pathlib import Path

from PIL import Image
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.core.renderer import images_to_base64_dict, render_pptx_to_images
from app.pipeline.orchestrator import run_review
from app.pipeline.suggestion import stream_slide_suggestions
from app.schemas.models import ExportPdfRequest, ReviewRequest, SuggestRequest

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="AI PowerPoint Reviewer (re-architecture)", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    """トップページを返す"""
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/api/health")
def health() -> dict:
    """ヘルスチェックエンドポイント"""
    return {"status": "ok"}


@app.post("/api/upload")
async def upload_pptx(file: UploadFile = File(...)) -> dict:
    """
    アップロードされたPowerPointファイルを, LibreOfficeによりPDF変換してスライドごとの画像を抽出する
    （010_ai_reviewer と同一ロジック）
    """
    if not file.filename or not file.filename.lower().endswith(".pptx"):
        raise HTTPException(status_code=400, detail=".pptx ファイルを指定してください。")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="ファイルが空です。")

    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = Path(tmpdir)
        try:
            slide_images = render_pptx_to_images(file_bytes, work_dir)
            images_b64 = images_to_base64_dict(slide_images)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    thumbnails = [item["jpg"] for item in images_b64]
    slide_pngs = [item["png"] for item in images_b64]

    return {
        "slide_count": len(slide_images),
        "file_name": file.filename,
        "thumbnails": thumbnails,
        "slide_pngs": slide_pngs,
        "thumbnail_mime": "image/jpeg",
        "render_method": "libre_office",
    }


@app.post("/api/review")
async def review_pptx(request: ReviewRequest) -> dict:
    """
    スライド画像と伝えたい内容をもとに、候補生成→過去レビュー参照→上司嗜好スコアリング→critic検証の
    4層パイプラインを実行し、指摘事項（Finding）一覧を返す
    """
    if not request.slides:
        raise HTTPException(status_code=400, detail="スライドデータがありません。")

    slides = [
        {"slide_number": s.slide_number, "image_png_b64": s.image_png_b64}
        for s in request.slides
    ]

    try:
        findings = await asyncio.to_thread(run_review, slides, request.overall_intended_message)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AIレビューに失敗しました: {exc}") from exc

    return {"findings": [f.model_dump() for f in findings]}


@app.post("/api/suggest")
async def suggest_revision(request: SuggestRequest) -> StreamingResponse:
    """
    /api/review の指摘事項（Finding）をもとに、AIがスライドごとの修正方針を提案する
    （010_ai_reviewerの画像編集提案機能と同一。完了したスライドから順にSSE形式でストリーミング返却する）
    """
    if not request.slides:
        raise HTTPException(status_code=400, detail="スライドデータがありません。")
    if not request.findings:
        raise HTTPException(status_code=400, detail="指摘事項がありません。先にAIレビューを実行してください。")

    data = request.model_dump()

    return StreamingResponse(
        stream_slide_suggestions(data["slides"], data["findings"]),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _build_pdf_from_slides(slides: list[dict]) -> bytes:
    """
    修正後スライド画像一覧をまとめて1つのPDFファイルに変換する（同期処理、010_ai_reviewerと同一ロジック）
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
    """修正後スライド画像一覧をまとめたPDFファイルを生成して返す（010_ai_reviewerと同一）"""
    if not request.slides:
        raise HTTPException(status_code=400, detail="スライドデータがありません。")

    data = request.model_dump()
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
