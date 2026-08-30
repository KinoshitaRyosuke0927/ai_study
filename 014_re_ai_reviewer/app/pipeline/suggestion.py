from __future__ import annotations

import asyncio
import base64
import json
from concurrent.futures import ThreadPoolExecutor

from app.core.azure_client import call_image_edit, call_structured
from app.prompts.suggestion_prompts import (
    LAYOUT_GUIDANCE_SUFFIX,
    NATURALNESS_GUIDANCE_SUFFIX,
    build_change_description_prompt_package,
    build_findings_text_by_slide,
    build_slide_edit_plan_prompt_package,
)


def _plan_slide_edits(slides: list[dict], findings: list[dict]) -> dict[int, str]:
    """
    指摘事項があるスライドについて、画像編集AI向けの具体的な指示文を一括で決定する（同期処理）

    010_ai_reviewer と異なり、Findingがすでにslide_numberを持っているため「どのスライドに
    該当するか」をAIに判断させる必要はなく、指摘事項テキストを具体的な編集指示に変換する
    ことだけをAIに依頼する（該当スライドがないものはそもそもプロンプトに含めない）。

    Returns
    -----------------
    - plans: dict[int, str],   slide_number をキーとする編集指示の辞書（該当なしのスライドは含まれない）

    """
    findings_text_by_slide = build_findings_text_by_slide(findings)
    if not findings_text_by_slide:
        return {}

    target_slides = [s for s in slides if s["slide_number"] in findings_text_by_slide]
    if not target_slides:
        return {}

    package = build_slide_edit_plan_prompt_package(target_slides, findings_text_by_slide)
    plan_result = call_structured(package)

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
    1枚のスライドについて、割り当てられた編集指示をもとに画像編集AIで修正後スライド画像と
    修正内容説明を生成する（同期処理、010_ai_reviewerと同一ロジック）
    """
    slide_number = slide["slide_number"]
    original_image_b64 = slide["image_png_b64"]

    edit_instruction = f"{edit_instruction}\n{LAYOUT_GUIDANCE_SUFFIX}\n{NATURALNESS_GUIDANCE_SUFFIX}"

    edited_image_bytes = call_image_edit(edit_instruction, base64.b64decode(original_image_b64))
    edited_image_b64 = base64.b64encode(edited_image_bytes).decode()

    description_package = build_change_description_prompt_package(slide_number, original_image_b64, edited_image_b64)
    description_result = call_structured(description_package)

    return {
        "slide_number": slide_number,
        "edited_image_b64": edited_image_b64,
        "description": description_result.get("description", ""),
    }


async def stream_slide_suggestions(slides: list[dict], findings: list[dict]):
    """
    指摘事項があるスライドを画像編集AIで並列に修正し、完了したものから順にSSE形式でyieldする
    （非同期ジェネレータ、010_ai_reviewerと同一の並列化・エラーハンドリング方針）
    """
    total = len(slides)
    yield f"data: {json.dumps({'type': 'start', 'total': total})}\n\n"

    loop = asyncio.get_running_loop()

    try:
        plans = await loop.run_in_executor(None, _plan_slide_edits, slides, findings)
    except Exception as exc:
        for slide in slides:
            error_payload = {"type": "slide_error", "slide_number": slide["slide_number"], "detail": str(exc)}
            yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    async def _run(executor: ThreadPoolExecutor, slide: dict) -> dict:
        slide_number = slide["slide_number"]
        instruction = plans.get(slide_number)
        if not instruction:
            return {
                "type": "slide_skipped",
                "slide_number": slide_number,
                "image_png_b64": slide["image_png_b64"],
            }
        try:
            result = await loop.run_in_executor(executor, _suggest_revision_for_slide, slide, instruction)
            return {"type": "slide_done", **result}
        except Exception as exc:
            return {"type": "slide_error", "slide_number": slide_number, "detail": str(exc)}

    # gpt-image-2/gpt-image-2-2 の2デプロイに振り分けるため, 最大同時実行数を4にする（010_ai_reviewerと同じ）
    with ThreadPoolExecutor(max_workers=4) as executor:
        tasks = [_run(executor, slide) for slide in slides]
        for coro in asyncio.as_completed(tasks):
            payload = await coro
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    yield f"data: {json.dumps({'type': 'done'})}\n\n"
