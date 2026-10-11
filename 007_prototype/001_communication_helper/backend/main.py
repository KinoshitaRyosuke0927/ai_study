"""コミュニケーション練習ツール（PoC）のバックエンド。

起動: プロジェクト直下で `python -m uvicorn backend.main:app --port 8000`
"""

import logging

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import PROJECT_ROOT, load_settings
from .emotion import EvaluateRequest, evaluate
from .personas import EMOTION_AXES, GENDERS, PERSONAS, SCENARIOS, build_instructions, initial_emotion
from .report import ReportRequest, generate_report
from .realtime_client import (
    TURN_DETECTION_PRESETS,
    build_session_config,
    create_client_secret,
    exchange_sdp,
)

logger = logging.getLogger("uvicorn.error")
settings = load_settings()
app = FastAPI(title="Communication Helper PoC")

FRONTEND_DIR = PROJECT_ROOT / "frontend"

# 選択可能な AI の声（Realtime API の組み込みボイス）と声質の目安
VOICES: dict[str, str] = {
    "marin": "女性寄り",
    "coral": "女性寄り",
    "shimmer": "女性寄り",
    "sage": "女性寄り",
    "cedar": "男性寄り",
    "ash": "男性寄り",
    "echo": "男性寄り",
    "verse": "男性寄り",
    "ballad": "男性寄り",
    "alloy": "中性的",
}


class SessionRequest(BaseModel):
    """WebRTC セッション開始リクエスト。"""

    sdp: str
    persona_id: str
    gender_id: str
    scenario_id: str
    voice: str | None = None
    vad: str = "semantic_vad"


@app.get("/api/options")
def get_options() -> dict:
    """画面の選択肢（ペルソナ・性別・シナリオ・声・VAD）を返す。

    Returns:
        dict: 選択肢一覧とセッション上限時間。
    """
    return {
        "personas": [{"id": p.id, "name": p.name, "description": p.description} for p in PERSONAS.values()],
        "genders": [{"id": g.id, "label": g.label, "default_voice": g.default_voice} for g in GENDERS.values()],
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
        "voices": [{"id": v, "label": f"{v}（{desc}）"} for v, desc in VOICES.items()],
        "vads": list(TURN_DETECTION_PRESETS.keys()),
        "session_max_minutes": settings.session_max_minutes,
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
    voice = req.voice if req.voice in VOICES else gender.default_voice

    # ペルソナ・性別・シナリオからセッション設定を作成
    session = build_session_config(settings, build_instructions(persona, gender, scenario), voice, req.vad)

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
