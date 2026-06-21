from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.pptx_parser import parse_pptx
from app.prompt import build_prompt_package
from app.azure_ai_service import call_review
from app.slide_renderer import render_slide_thumbnails


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

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
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    """
    ヘルスチェックエンドポイント
    """
    return {"status": "ok"}


@app.post("/api/upload")
async def upload_pptx(file: UploadFile = File(...)) -> dict:
    """
    PPTXをアップロードしてスライド画像と解析データを返す
    """
    # ファイル形式を検証
    if not file.filename or not file.filename.lower().endswith(".pptx"):
        raise HTTPException(status_code=400, detail=".pptx ファイルを指定してください。")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="ファイルが空です。")

    # PPTXを解析
    try:
        parsed = parse_pptx(file_bytes=file_bytes, filename=file.filename)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"PPTX解析に失敗しました: {exc}") from exc

    thumbnails: list[str] = []
    slide_pngs: list[str] = []
    thumbnail_mime = "image/png"
    render_method = "none"
    render_error: str | None = None

    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = Path(tmpdir)

        ## LibreOffice ベースのレンダリングを試みる
        try:
            from app.renderer import render_pptx_to_images, images_to_base64_dict
            slide_images = render_pptx_to_images(file_bytes, work_dir)
            images_b64 = images_to_base64_dict(slide_images)
            thumbnails = [item["jpg"] for item in images_b64]
            slide_pngs = [item["png"] for item in images_b64]
            thumbnail_mime = "image/jpeg"
            render_method = "libre_office"
        except Exception as exc:
            render_error = str(exc)
            ## フォールバック: Pillow ベースの簡易レンダラー
            try:
                pillow_thumbs = render_slide_thumbnails(file_bytes)
                thumbnails = pillow_thumbs
                slide_pngs = pillow_thumbs
                thumbnail_mime = "image/png"
                render_method = "pillow"
            except Exception:
                thumbnails = []
                slide_pngs = []

    return {
        "slide_count": parsed["slide_count"],
        "file_name": parsed["file_name"],
        "thumbnails": thumbnails,          # 後方互換: 一覧用画像 (JPEG or PNG)
        "slide_pngs": slide_pngs,          # AI品質 PNG (200 DPI)
        "thumbnail_mime": thumbnail_mime,  # "image/jpeg" or "image/png"
        "render_method": render_method,    # "libre_office" | "pillow" | "none"
        "render_error": render_error,
    }


@app.post("/api/review")
async def review_pptx(
    file: UploadFile = File(...),
    overall_intended_message: str = Form(""),
    per_slide_intended_messages: str = Form(""),
) -> dict:
    """
    PPTXと伝えたい内容をもとにAIがレビューを行い結果を返す
    """
    # ファイル形式を検証
    if not file.filename or not file.filename.lower().endswith(".pptx"):
        raise HTTPException(status_code=400, detail=".pptx ファイルを指定してください。")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="ファイルが空です。")

    # PPTXを解析
    try:
        parsed = parse_pptx(
            file_bytes=file_bytes,
            filename=file.filename,
            overall_intended_message=overall_intended_message,
            per_slide_intended_messages=per_slide_intended_messages,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"PPTX解析に失敗しました: {exc}") from exc

    review_result: dict

    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = Path(tmpdir)

        ## 各スライドに PNG パスを付与（将来のビジョン API 対応; 失敗してもレビューは継続）
        try:
            from app.renderer import render_pptx_to_images
            slide_images = render_pptx_to_images(file_bytes, work_dir)
            for i, slide in enumerate(parsed.get("slides", [])):
                if i < len(slide_images):
                    slide["image_png_path"] = str(slide_images[i]["png"])
                    slide["image_jpg_path"] = str(slide_images[i]["jpg"])
        except Exception:
            pass

        # プロンプトパッケージを構築してAIレビューを実行
        prompt_package = build_prompt_package(parsed)

        try:
            review_result = call_review(prompt_package)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"AIレビューに失敗しました: {exc}") from exc

    return review_result
