from __future__ import annotations

import asyncio
import base64
import json
import uvicorn
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any
from concurrent.futures import ThreadPoolExecutor

from PIL import Image
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.prompt import (
    LAYOUT_GUIDANCE_SUFFIX,
    build_anticipated_questions_prompt_package,
    build_change_description_prompt_package,
    build_overall_per_type_prompt_packages_by_type,
    build_overall_per_type_summarize_prompt_package,
    build_revision_findings_text,
    build_slide_edit_plan_prompt_package,
    list_review_point_settings,
    update_review_point_settings,
)
from app.renderer import render_pptx_to_images, images_to_base64_dict
from app.azure_ai_service import call_image_edit, call_qa, call_review
from app.share_service import create_share, get_share


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


class ReviewPointItem(BaseModel):
    source: str
    row_index: int
    perspective_type: str
    perspective_label: str
    role: str | None = None
    apply_flag: bool
    detail: str


class ReviewPointUpdateItem(BaseModel):
    source: str
    row_index: int
    apply_flag: bool


class ReviewPointUpdateRequest(BaseModel):
    updates: list[ReviewPointUpdateItem]

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
    "composition": "レイアウト構成",
    "character":   "文字表現",
    "colors":      "配色",
    "figures":     "図表・画像",
    "sentence":    "文章表現",
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


def _build_review_point_items() -> list[ReviewPointItem]:
    """
    CSVから読み込んだ観点設定一覧を、日本語ラベル付きのレスポンス形式に変換する
    """
    items = []
    for row in list_review_point_settings():
        ptype = row["perspective_type"]
        items.append(ReviewPointItem(
            source=row["source"],
            row_index=row["row_index"],
            perspective_type=ptype,
            perspective_label=PTYPE_LABELS.get(ptype, ptype),
            role=row["role"],
            apply_flag=row["apply_flag"],
            detail=row["detail"],
        ))
    return items


@app.get("/api/review-points")
def get_review_points() -> dict:
    """
    レビュー観点設定（CSVに記載された観点とapply_flagの状態）の一覧を返す
    """
    return {"items": [item.model_dump() for item in _build_review_point_items()]}


@app.post("/api/review-points")
def update_review_points(request: ReviewPointUpdateRequest) -> dict:
    """
    レビュー観点設定のapply_flagを更新し、CSVファイルへ書き戻す
    """
    if not request.updates:
        raise HTTPException(status_code=400, detail="更新内容がありません。")
    try:
        update_review_point_settings([u.model_dump() for u in request.updates])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"観点設定の更新に失敗しました: {exc}") from exc
    return {"items": [item.model_dump() for item in _build_review_point_items()]}


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


@app.post("/api/anticipated-questions")
async def anticipated_questions(request: ReviewRequest) -> dict:
    """
    スライド画像と伝えたい内容をもとに、AI技術者・アプリケーションエンジニア視点での想定質問をAIが提案する
    """
    # スライド情報が読み取れなかった場合
    if not request.slides:
        raise HTTPException(status_code=400, detail="スライドデータがありません。")

    data = request.model_dump()
    package = build_anticipated_questions_prompt_package(data)

    try:
        result = await asyncio.to_thread(call_qa, package)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AIによる想定質問の生成に失敗しました: {exc}") from exc

    return {"questions": result.get("questions", [])}


def _plan_slide_edits(slides: list[dict], findings_text: str) -> dict[int, str]:
    """
    全スライド画像と指摘事項から、資料全体を見渡してスライドごとの編集指示を一括で決定する（同期処理）

    Returns
    -----------------
    - plans: dict[int, str],   slide_number をキーとする編集指示の辞書（該当なしのスライドは含まれない）

    """
    plan_package = build_slide_edit_plan_prompt_package(slides, findings_text)
    try:
        plan_result = call_review(plan_package)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AIレビュー（修正方針の一括決定）に失敗しました: {exc}") from exc

    plans: dict[int, str] = {}
    for entry in plan_result.get("slide_plans", []):
        instruction = (entry.get("instruction") or "").strip()
        if not instruction:
            continue
        slide_number = entry.get("slide_number")
        if isinstance(slide_number, int):
            plans[slide_number] = instruction
    return plans


def _suggest_revision_for_slide(slide: dict, edit_instruction: str) -> dict:
    """
    1枚のスライドについて、割り当てられた編集指示をもとに画像編集AIで修正後スライド画像と修正内容説明を生成する（同期処理）
    """
    slide_number = slide["slide_number"]
    original_image_b64 = slide["image_png_b64"]

    # AIの出力内容によらず、余白確保のガイダンスを必ず付加する
    edit_instruction = f"{edit_instruction}\n{LAYOUT_GUIDANCE_SUFFIX}"

    # Step1: 画像編集AIで元スライド画像を修正
    try:
        edited_image_bytes = call_image_edit(edit_instruction, base64.b64decode(original_image_b64))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI画像修正に失敗しました: {exc}") from exc
    edited_image_b64 = base64.b64encode(edited_image_bytes).decode()

    # Step2: 修正前後の画像を比較し、実際に施した修正内容の説明を生成
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


async def _stream_slide_suggestions(slides: list[dict], findings_text: str):
    """
    資料全体を見渡してスライドごとの編集方針を決定し、その方針にもとづく修正をスライドごとに並列実行して、
    完了したものから順にSSE形式でyieldする（非同期ジェネレータ）

    Args
    -----------------
    - slides: list[dict],       スライドデータのリスト
    - findings_text: str,       観点別レビュー結果（指摘事項）のテキスト

    """
    total = len(slides)
    yield f"data: {json.dumps({'type': 'start', 'total': total})}\n\n"

    loop = asyncio.get_running_loop()

    # Step1: 全スライドを見渡して、スライドごとの編集方針を一括決定する
    try:
        plans = await loop.run_in_executor(None, _plan_slide_edits, slides, findings_text)
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        for slide in slides:
            error_payload = {"type": "slide_error", "slide_number": slide["slide_number"], "detail": detail}
            yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    async def _run(executor: ThreadPoolExecutor, slide: dict) -> dict:
        # 該当する指摘がないスライドは画像編集自体をスキップし、修正前の画像をそのまま返す
        slide_number = slide["slide_number"]
        instruction = plans.get(slide_number)
        if not instruction:
            return {
                "type": "slide_skipped",
                "slide_number": slide_number,
                "image_png_b64": slide["image_png_b64"],
            }

        # 1スライド分の処理を実行し、失敗しても他スライドの処理を止めないようエラーを結果として返す
        try:
            result = await loop.run_in_executor(executor, _suggest_revision_for_slide, slide, instruction)
            return {"type": "slide_done", **result}
        except Exception as exc:
            detail = getattr(exc, "detail", str(exc))
            return {"type": "slide_error", "slide_number": slide_number, "detail": detail}

    # gpt-image-2/gpt-image-2-2 の2デプロイに振り分けるため, 最大同時実行数を4にする
    with ThreadPoolExecutor(max_workers=4) as executor:
        tasks = [_run(executor, slide) for slide in slides]
        for coro in asyncio.as_completed(tasks):
            payload = await coro
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    yield f"data: {json.dumps({'type': 'done'})}\n\n"


@app.post("/api/suggest")
async def suggest_revision(request: SuggestionRequest) -> StreamingResponse:
    """
    観点別レビュー結果とスライド画像をもとに、AIがスライドごとの修正方針を提案する
    完了したスライドから順にSSE形式でストリーミング返却する
    """
    # スライド情報が読み取れなかった場合
    if not request.slides:
        raise HTTPException(status_code=400, detail="スライドデータがありません。")
    # レビュー結果が存在しない場合
    if not request.perspectives:
        raise HTTPException(status_code=400, detail="レビュー結果がありません。先にAIレビューを実行してください。")

    data = request.model_dump()
    findings_text = build_revision_findings_text(data["perspectives"])

    return StreamingResponse(
        _stream_slide_suggestions(data["slides"], findings_text),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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


@app.post("/api/share")
async def create_share_link(payload: dict[str, Any]) -> dict:
    """
    現在のレビュー結果一式をBlob Storageに保存し、共有用URLを発行する
    """
    try:
        meta = await asyncio.to_thread(create_share, payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"共有リンクの作成に失敗しました: {exc}") from exc

    return {
        "share_id": meta["share_id"],
        "url": f"/share/{meta['share_id']}",
        "expires_at": meta["expires_at"],
    }


@app.get("/api/share/{share_id}")
async def get_share_data(share_id: str) -> dict:
    """
    共有されたレビュー結果一式を取得する（期限切れ・存在しない場合は404）
    """
    record = await asyncio.to_thread(get_share, share_id)
    if record is None:
        raise HTTPException(status_code=404, detail="共有リンクが見つからないか、有効期限が切れています。")
    return record


@app.get("/share/{share_id}")
def share_page(share_id: str) -> FileResponse:
    """
    共有結果の閲覧専用ページ（share.html）を返す
    """
    return FileResponse(
        STATIC_DIR / "share.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


# exe起動用
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
