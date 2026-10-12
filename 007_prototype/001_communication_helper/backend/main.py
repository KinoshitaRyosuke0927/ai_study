"""コミュニケーション練習ツール（PoC）のバックエンド。

起動: プロジェクト直下で `python run.py`（または `python -m uvicorn backend.main:app --port 8000`）
"""

import logging

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import RESOURCE_DIR, load_settings
from .emotion import EvaluateRequest, evaluate
from .personas import EMOTION_AXES, GENDERS, PERSONAS, SCENARIOS, build_instructions, initial_emotion
from .report import ReportRequest, generate_report
from .turn_taking import (
    BACKCHANNEL_PROMPT,
    CLOSING_PROMPT,
    CLOSING_STAGES,
    IDLE_OPENING_PROMPT,
    JUDGE_INSTRUCTIONS,
    JUDGE_TOOL,
    PROACTIVE_PROMPT,
)
from .realtime_client import (
    build_session_config,
    create_client_secret,
    exchange_sdp,
)

logger = logging.getLogger("uvicorn.error")
settings = load_settings()
app = FastAPI(title="Communication Helper PoC")

FRONTEND_DIR = RESOURCE_DIR / "frontend"

class SessionRequest(BaseModel):
    """WebRTC セッション開始リクエスト。AI の声は性別ごとに固定（personas.GENDERS）。"""

    sdp: str
    persona_id: str
    gender_id: str
    scenario_id: str


@app.get("/api/options")
def get_options() -> dict:
    """画面の選択肢（ペルソナ・性別・シナリオ）と話者交代の制御設定を返す。

    Returns:
        dict: 選択肢一覧とセッション上限時間。
    """
    return {
        "personas": [{"id": p.id, "name": p.name, "description": p.description} for p in PERSONAS.values()],
        "genders": [{"id": g.id, "label": g.label} for g in GENDERS.values()],
        "scenarios": [
            {
                "id": s.id,
                "category": s.category,
                "title": s.title,
                "situation": s.situation,
                "ai_speaks_first": s.ai_speaks_first,
                "initial_emotion": initial_emotion(s),
            }
            for s in SCENARIOS.values()
        ],
        "emotion_axes": [{"id": key, "label": label} for key, label in EMOTION_AXES.items()],
        "session_max_minutes": settings.session_max_minutes,
        "turn_taking": {
            "judge_instructions": JUDGE_INSTRUCTIONS,
            "judge_tool": JUDGE_TOOL,
            "backchannel_prompt": BACKCHANNEL_PROMPT,
            "proactive_prompt": PROACTIVE_PROMPT,
            "closing_prompt": CLOSING_PROMPT,
            "closing_stages": CLOSING_STAGES,
            "idle_opening_prompt": IDLE_OPENING_PROMPT,
            "silence_sec": settings.proactive_silence_sec,
        },
    }


@app.post("/api/realtime/session", response_class=PlainTextResponse)
async def start_session(req: SessionRequest) -> str:
    """セッション設定付きで Realtime API に接続し、SDP アンサーを返す。

    Args:
        req: ブラウザの SDP オファーと選択内容。

    Returns:
        str: SDP アンサー（ブラウザの RTCPeerConnection にそのまま設定する）。
    """
    # 入力値の検証
    persona = PERSONAS.get(req.persona_id)
    gender = GENDERS.get(req.gender_id)
    scenario = SCENARIOS.get(req.scenario_id)
    if persona is None or gender is None or scenario is None:
        raise HTTPException(status_code=400, detail="不明なペルソナ・性別・シナリオです")

    # ペルソナ・性別・シナリオからセッション設定を作成
    session = build_session_config(settings, build_instructions(persona, gender, scenario), gender.default_voice)

    # エフェメラルキー発行 → SDP 交換
    try:
        ephemeral_key = await create_client_secret(settings, session)
        return await exchange_sdp(settings, ephemeral_key, req.sdp)
    except httpx.HTTPStatusError as e:
        logger.error("Realtime API エラー: %s %s", e.response.status_code, e.response.text)
        raise HTTPException(status_code=502, detail=f"Realtime API エラー: {e.response.text}") from e


@app.post("/api/emotion/evaluate")
async def evaluate_emotion(req: EvaluateRequest) -> dict:
    """ユーザ発話を受けた受け手の感情を推定する。

    Args:
        req: 会話履歴・評価対象の発話・現在の感情値。

    Returns:
        dict: 更新後の感情値・変化量・心の声・理由・良かった点/気になった点。
    """
    # 入力値の検証
    persona = PERSONAS.get(req.persona_id)
    gender = GENDERS.get(req.gender_id)
    scenario = SCENARIOS.get(req.scenario_id)
    if persona is None or gender is None or scenario is None:
        raise HTTPException(status_code=400, detail="不明なペルソナ・性別・シナリオです")

    # 評価用 LLM で推定
    try:
        return await evaluate(settings, req, persona, gender, scenario)
    except httpx.HTTPStatusError as e:
        logger.error("感情推定エラー: %s %s", e.response.status_code, e.response.text)
        raise HTTPException(status_code=502, detail="感情推定に失敗しました") from e


@app.post("/api/report")
async def create_report(req: ReportRequest) -> dict:
    """会話終了後の振り返りレポートを生成する。

    Args:
        req: 評価付きの会話ログと感情の推移。

    Returns:
        dict: 総評・相手から見た印象・良かった発言・改善したい発言・次回のポイント。
    """
    # 入力値の検証
    persona = PERSONAS.get(req.persona_id)
    gender = GENDERS.get(req.gender_id)
    scenario = SCENARIOS.get(req.scenario_id)
    if persona is None or gender is None or scenario is None:
        raise HTTPException(status_code=400, detail="不明なペルソナ・性別・シナリオです")
    if not any(t.role == "user" for t in req.turns):
        raise HTTPException(status_code=400, detail="あなたの発言がないため、レポートを作成できません")

    # 評価用 LLM でレポートを生成
    try:
        return await generate_report(settings, req, persona, gender, scenario)
    except httpx.HTTPStatusError as e:
        logger.error("レポート生成エラー: %s %s", e.response.status_code, e.response.text)
        raise HTTPException(status_code=502, detail="レポートの生成に失敗しました") from e


@app.get("/")
def index() -> FileResponse:
    """トップページを返す。

    Returns:
        FileResponse: index.html。
    """
    return FileResponse(FRONTEND_DIR / "index.html")


# JS / CSS などの静的ファイル
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
# 会話相手の表情画像（{man|woman}_{angry|laugh|smile|surprise|think}.png）
app.mount("/images", StaticFiles(directory=RESOURCE_DIR / "image"), name="images")
