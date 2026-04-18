import os
import uuid

import aiofiles
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from models.schemas import GenerateRequest, GenerateResponse
from services.gemini_analyzer import analyze_video_with_gemini
from services.manual_generator import generate_html_manual
from services.video_processor import extract_keyframes

router = APIRouter()

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "outputs")
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB


@router.post("/upload")
async def upload_video(video_file: UploadFile = File(...)):
    """動画ファイルを受け取り、uploads/ に保存する"""
    allowed_types = {"video/mp4", "video/quicktime", "video/x-msvideo", "video/webm", "video/avi"}
    if video_file.content_type and video_file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"サポートされていない動画形式です: {video_file.content_type}")

    ext = os.path.splitext(video_file.filename or "video.mp4")[1] or ".mp4"
    unique_filename = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(UPLOAD_DIR, unique_filename)

    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # ストリーミングで保存（大容量対応）
    total_size = 0
    async with aiofiles.open(save_path, "wb") as f:
        while True:
            chunk = await video_file.read(1024 * 1024)  # 1MB chunks
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > MAX_FILE_SIZE:
                await f.close()
                os.remove(save_path)
                raise HTTPException(status_code=413, detail="ファイルサイズが500MBを超えています")
            await f.write(chunk)

    return {"filename": unique_filename, "size": total_size}


@router.post("/generate", response_model=GenerateResponse)
async def generate_manual(request: GenerateRequest):
    """マニュアル生成パイプラインを実行する"""
    video_path = os.path.join(UPLOAD_DIR, request.video_filename)
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail=f"動画ファイルが見つかりません: {request.video_filename}")

    manual_id = uuid.uuid4().hex

    # フレーム抽出ディレクトリ
    frames_dir = os.path.join(OUTPUT_DIR, manual_id, "frames")
    os.makedirs(frames_dir, exist_ok=True)

    try:
        # Step 1: キーフレーム抽出
        threshold = float(os.getenv("SCENE_THRESHOLD", "0.3"))
        frame_paths = extract_keyframes(video_path, frames_dir, threshold)

        # Step 2: Gemini AI解析
        manual = analyze_video_with_gemini(video_path, frame_paths)

        # Step 3: HTMLマニュアル生成
        generate_html_manual(manual, frame_paths, OUTPUT_DIR, manual_id)

    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"マニュアル生成中にエラーが発生しました: {str(e)}")

    return GenerateResponse(
        status="success",
        manual_id=manual_id,
        manual_html_url=f"/api/manual/{manual_id}/html",
        manual_json=manual,
    )


@router.get("/manual/{manual_id}/html", response_class=HTMLResponse)
async def get_manual_html(manual_id: str):
    """生成済みHTMLマニュアルを返す"""
    html_path = os.path.join(OUTPUT_DIR, manual_id, "manual.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="マニュアルが見つかりません")

    async with aiofiles.open(html_path, "r", encoding="utf-8") as f:
        content = await f.read()
    return HTMLResponse(content=content)


@router.get("/manual/{manual_id}/download")
async def download_manual(manual_id: str):
    """HTMLファイルをダウンロードする"""
    html_path = os.path.join(OUTPUT_DIR, manual_id, "manual.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="マニュアルが見つかりません")

    return FileResponse(
        path=html_path,
        media_type="text/html",
        filename="manual.html",
        headers={"Content-Disposition": "attachment; filename=manual.html"},
    )
