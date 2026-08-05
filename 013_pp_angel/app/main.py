from __future__ import annotations

import asyncio
import base64
import json
import tempfile
from io import BytesIO
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import uvicorn
from PIL import Image
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.prompt import LAYOUT_GUIDANCE_SUFFIX
from app.azure_ai_service import call_chat, call_image_generate, call_image_edit, analyze_pptx_style
from app.pptx_utils import render_pptx_first_slide_to_png


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    history: list[ChatMessage]


class SlidePlanItem(BaseModel):
    slide_number: int
    title: str
    description: str


class SlideGenerateRequest(BaseModel):
    slide_plan: list[SlidePlanItem]
    style_image_b64: str


class SlideRevision(BaseModel):
    slide_number: int
    image_b64: str
    instruction: str = ""


class SlideReviseRequest(BaseModel):
    slides: list[SlideRevision]


class SlideExportItem(BaseModel):
    slide_number: int
    image_b64: str


class SlideExportPdfRequest(BaseModel):
    slides: list[SlideExportItem]


# フロントエンドのHTMLパス
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
# アイコン等の画像素材ディレクトリ
IMAGES_DIR = BASE_DIR.parent / "images"


# アプリケーション実行
app = FastAPI(title="AI Chat Prototype", version="1.0.0")

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
app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")


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


@app.post("/api/chat")
def chat(request: ChatRequest) -> dict:
    """
    チャット履歴を受け取り、AIのヒアリング状況を表す構造化レスポンスを返す

    AIがスタイル案（style_proposals）を提示した場合、この時点では画像生成は行わず、
    案（label/image_prompt）のみを返す。画像の生成はフロントエンドが
    /api/chat/style-images を呼び出すことで別リクエストとして進行させ、
    チャットの発言をすぐに表示できるようにする（体感速度の改善のため）。
    """
    if not request.history:
        raise HTTPException(status_code=400, detail="チャット内容がありません。")

    history = [m.model_dump() for m in request.history]
    try:
        result = call_chat(history)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AIとの通信に失敗しました: {exc}") from exc

    return {
        "message": result.get("message", ""),
        "options": result.get("options") or [],
        "style_proposals": result.get("style_proposals") or [],
        "ready_to_generate": bool(result.get("ready_to_generate")),
        "slide_plan": result.get("slide_plan"),
    }


class StyleProposal(BaseModel):
    label: str
    image_prompt: str


class StyleImagesRequest(BaseModel):
    style_proposals: list[StyleProposal]


async def _stream_style_images(style_proposals: list[StyleProposal]):
    """
    スタイル案ごとの画像生成を並列実行し、完了したものから順にSSE形式でyieldする
    """
    total = len(style_proposals)
    yield f"data: {json.dumps({'type': 'start', 'total': total})}\n\n"

    loop = asyncio.get_running_loop()

    async def _run(executor: ThreadPoolExecutor, index: int, proposal: StyleProposal) -> dict:
        try:
            image_bytes = await loop.run_in_executor(executor, call_image_generate, proposal.image_prompt)
            return {"type": "style_image_done", "index": index, "image_b64": base64.b64encode(image_bytes).decode()}
        except Exception as exc:
            detail = getattr(exc, "detail", str(exc))
            return {"type": "style_image_error", "index": index, "detail": detail}

    # スタイル案は少数（通常3件）なので、案の数だけ並列実行して待ち時間を短縮する
    with ThreadPoolExecutor(max_workers=max(1, total)) as executor:
        tasks = [_run(executor, i, p) for i, p in enumerate(style_proposals)]
        for coro in asyncio.as_completed(tasks):
            payload = await coro
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    yield f"data: {json.dumps({'type': 'done'})}\n\n"


@app.post("/api/chat/style-images")
async def generate_style_images(request: StyleImagesRequest) -> StreamingResponse:
    """
    スタイル案ごとの画像を生成し、完了したものから順にSSE形式でストリーミング返却する
    """
    if not request.style_proposals:
        raise HTTPException(status_code=400, detail="スタイル案がありません。")

    return StreamingResponse(
        _stream_style_images(request.style_proposals),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/style/analyze-pptx")
async def analyze_pptx_style_endpoint(file: UploadFile = File(...)) -> dict:
    """
    アップロードされたpptxの1枚目のスライドを画像化し、AIでスタイルを分析する

    分析結果の説明文は、チャット履歴上のユーザ発言としてフロントエンドから送信され、
    以降のstyle_proposals生成時に参考資料のスタイルを踏襲するために使われる
    """
    if not (file.filename or "").lower().endswith(".pptx"):
        raise HTTPException(status_code=400, detail="pptxファイルをアップロードしてください。")

    pptx_bytes = await file.read()
    if not pptx_bytes:
        raise HTTPException(status_code=400, detail="ファイルの内容を読み込めませんでした。")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = Path(tmpdir)
            preview_bytes = await asyncio.to_thread(render_pptx_first_slide_to_png, pptx_bytes, work_dir)
            style_description = await asyncio.to_thread(analyze_pptx_style, preview_bytes)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"資料のスタイル解析に失敗しました: {exc}") from exc

    return {
        "style_description": style_description,
        "preview_image_b64": base64.b64encode(preview_bytes).decode(),
    }


def _build_slide_instruction(title: str, description: str) -> str:
    """
    スライドのタイトル・記載内容から、画像生成/編集AI向けの指示文を組み立てる
    """
    return f"スライドタイトル: {title}\n記載内容: {description}\n{LAYOUT_GUIDANCE_SUFFIX}"


def _generate_slide_image(slide: SlidePlanItem, style_image_bytes: bytes) -> dict:
    """
    スタイル画像をベースに、1枚のスライド画像を生成する（同期処理）
    """
    instruction = _build_slide_instruction(slide.title, slide.description)
    image_bytes = call_image_edit(instruction, style_image_bytes)
    return {"slide_number": slide.slide_number, "image_b64": base64.b64encode(image_bytes).decode()}


async def _stream_slide_generation(slide_plan: list[SlidePlanItem], style_image_b64: str):
    """
    スライド構成案をもとに、スライドごとの画像生成を並列実行し、完了したものから順にSSE形式でyieldする
    """
    total = len(slide_plan)
    yield f"data: {json.dumps({'type': 'start', 'total': total})}\n\n"

    style_image_bytes = base64.b64decode(style_image_b64)
    loop = asyncio.get_running_loop()

    async def _run(executor: ThreadPoolExecutor, slide: SlidePlanItem) -> dict:
        try:
            result = await loop.run_in_executor(executor, _generate_slide_image, slide, style_image_bytes)
            return {"type": "slide_done", **result}
        except Exception as exc:
            detail = getattr(exc, "detail", str(exc))
            return {"type": "slide_error", "slide_number": slide.slide_number, "detail": detail}

    # Azure側の通信上限があるため, 最大同時実行数を2にする
    with ThreadPoolExecutor(max_workers=2) as executor:
        tasks = [_run(executor, slide) for slide in slide_plan]
        for coro in asyncio.as_completed(tasks):
            payload = await coro
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    yield f"data: {json.dumps({'type': 'done'})}\n\n"


@app.post("/api/slides/generate")
async def generate_slides(request: SlideGenerateRequest) -> StreamingResponse:
    """
    スライド構成案と選択されたスタイル画像をもとに、スライドごとの画像を生成する
    完了したスライドから順にSSE形式でストリーミング返却する
    """
    if not request.slide_plan:
        raise HTTPException(status_code=400, detail="スライド構成がありません。")
    if not request.style_image_b64:
        raise HTTPException(status_code=400, detail="スタイル画像が選択されていません。")

    return StreamingResponse(
        _stream_slide_generation(request.slide_plan, request.style_image_b64),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _revise_slide_image(slide: SlideRevision) -> dict:
    """
    ユーザの修正指示にもとづき、1枚のスライド画像を修正する（同期処理）
    """
    instruction = f"{slide.instruction}\n{LAYOUT_GUIDANCE_SUFFIX}"
    image_bytes = call_image_edit(instruction, base64.b64decode(slide.image_b64))
    return {"slide_number": slide.slide_number, "image_b64": base64.b64encode(image_bytes).decode()}


async def _stream_slide_revision(slides: list[SlideRevision]):
    """
    カードごとの修正指示にもとづき、スライドごとの画像修正を並列実行し、完了したものから順にSSE形式でyieldする
    修正指示が空のスライドは編集自体をスキップし、元の画像をそのまま返す
    """
    total = len(slides)
    yield f"data: {json.dumps({'type': 'start', 'total': total})}\n\n"

    loop = asyncio.get_running_loop()

    async def _run(executor: ThreadPoolExecutor, slide: SlideRevision) -> dict:
        if not slide.instruction.strip():
            return {"type": "slide_skipped", "slide_number": slide.slide_number, "image_b64": slide.image_b64}
        try:
            result = await loop.run_in_executor(executor, _revise_slide_image, slide)
            return {"type": "slide_done", **result}
        except Exception as exc:
            detail = getattr(exc, "detail", str(exc))
            return {"type": "slide_error", "slide_number": slide.slide_number, "detail": detail}

    # Azure側の通信上限があるため, 最大同時実行数を2にする
    with ThreadPoolExecutor(max_workers=2) as executor:
        tasks = [_run(executor, slide) for slide in slides]
        for coro in asyncio.as_completed(tasks):
            payload = await coro
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    yield f"data: {json.dumps({'type': 'done'})}\n\n"


@app.post("/api/slides/revise")
async def revise_slides(request: SlideReviseRequest) -> StreamingResponse:
    """
    カードごとに入力された修正指示にもとづき、対象スライドの画像を一斉に修正する
    完了したスライドから順にSSE形式でストリーミング返却する
    """
    if not request.slides:
        raise HTTPException(status_code=400, detail="スライドデータがありません。")

    return StreamingResponse(
        _stream_slide_revision(request.slides),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _build_pdf_from_slides(slides: list[SlideExportItem]) -> bytes:
    """
    現在表示中のスライド画像一覧をまとめて1つのPDFファイルに変換する（同期処理）
    """
    images = [
        Image.open(BytesIO(base64.b64decode(slide.image_b64))).convert("RGB")
        for slide in slides
    ]
    buffer = BytesIO()
    images[0].save(buffer, format="PDF", save_all=True, append_images=images[1:])
    return buffer.getvalue()


@app.post("/api/slides/export-pdf")
async def export_slides_pdf(request: SlideExportPdfRequest) -> Response:
    """
    現在表示中のスライド画像一覧をまとめたPDFファイルを生成して返す
    """
    if not request.slides:
        raise HTTPException(status_code=400, detail="スライドデータがありません。")

    slides = sorted(request.slides, key=lambda s: s.slide_number)

    try:
        pdf_bytes = await asyncio.to_thread(_build_pdf_from_slides, slides)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDFファイルの生成に失敗しました: {exc}") from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="slides.pdf"'},
    )


# exe起動用
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
