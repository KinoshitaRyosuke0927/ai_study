from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.prompt import build_overall_prompt_package, build_slides_prompt_package
from app.renderer import render_pptx_to_images, images_to_base64_dict
from app.azure_ai_service import call_review


class SlideInput(BaseModel):
    slide_number: int
    image_jpeg_b64: str
    intended_message: str = ""


class ReviewRequest(BaseModel):
    overall_intended_message: str = ""
    slides: list[SlideInput]

# フロントエンドのHTMLパス
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

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

    # スライド全体に対するレビューを行う
    try:
        # AIに送信
        overall_result = call_review(build_overall_prompt_package(data))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AIレビュー（全体評価）に失敗しました: {exc}") from exc

    # スライドごとに個別レビューを行う
    try:
        # AIに送信
        slides_result = call_review(build_slides_prompt_package(data))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AIレビュー（スライド評価）に失敗しました: {exc}") from exc

    # レスポンス作成
    return {
        "presentation_summary": overall_result.get("presentation_summary", {}),
        "slides": slides_result.get("slides", []),
    }
