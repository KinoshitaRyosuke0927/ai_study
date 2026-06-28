from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.prompt import build_prompt_package
from app.renderer import render_pptx_to_images, images_to_base64_dict
from app.pptx_parser import parse_pptx
from app.azure_ai_service import call_review

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
async def review_pptx(
    file: UploadFile = File(...),
    overall_intended_message: str = Form(""),
    per_slide_intended_messages: str = Form(""),
) -> dict:
    """
    PowerPointのスライドと伝えたい内容をもとにAIがレビューを行い結果を返す
    """
    # ファイル形式を検証
    if not file.filename or not file.filename.lower().endswith(".pptx"):
        raise HTTPException(status_code=400, detail=".pptx ファイルを指定してください。")

    # ファイル読み込み
    file_bytes = await file.read()
    # ファイルのサイズが取得できなかった場合
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

    # プロンプトパッケージを構築してAIレビューを実行
    prompt_package = build_prompt_package(parsed)

    try:
        review_result = call_review(prompt_package)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AIレビューに失敗しました: {exc}") from exc

    return review_result
