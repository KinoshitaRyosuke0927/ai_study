"""Azure OpenAI Realtime API との接続処理。

ブラウザ ⇔ Azure の音声は WebRTC で直接流し、バックエンドは
「セッション設定付きのエフェメラルキー発行」と「SDP の中継」だけを担う。
これにより API キーとシステム指示文をブラウザに渡さずに済む。
"""

import httpx

from .config import Settings

# 発話区間の検出設定
# 発話の区切り（ユーザ発話の確定）は検出するが、応答は自動生成しない。
# 応答するかどうかはフロントエンドがターン判定（turn_taking.py）の結果で決める。
# AI の発話中にユーザが話し始めた場合は、従来どおり AI の発話を止める。
TURN_DETECTION = {
    "type": "semantic_vad",
    "eagerness": "auto",
    "create_response": False,
    "interrupt_response": True,
}


def build_session_config(settings: Settings, instructions: str, voice: str) -> dict:
    """Realtime セッションの設定を組み立てる。

    Args:
        settings: アプリ設定。
        instructions: システム指示文。
        voice: AI の声の種類。

    Returns:
        dict: client_secrets API に渡す session オブジェクト。
    """
    return {
        "type": "realtime",
        "model": settings.realtime_deployment,
        "instructions": instructions,
        "output_modalities": ["audio"],
        "audio": {
            "input": {
                # ユーザ発話の文字起こし（会話ログ・後続の感情推定に使用）
                "transcription": {"model": settings.transcribe_model, "language": "ja"},
                "noise_reduction": {"type": "near_field"},
                "turn_detection": TURN_DETECTION,
            },
            "output": {"voice": voice},
        },
    }


async def create_client_secret(settings: Settings, session: dict) -> str:
    """セッション設定を埋め込んだエフェメラルキーを発行する。

    Args:
        settings: アプリ設定。
        session: build_session_config で作成したセッション設定。

    Returns:
        str: 短時間のみ有効なエフェメラルキー。
    """
    # API キーで client_secrets を呼び出し、セッション設定を確定させる
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.post(
            f"{settings.azure_endpoint}/realtime/client_secrets",
            headers={"api-key": settings.azure_key},
            json={"session": session},
        )
    res.raise_for_status()
    return res.json()["value"]


async def exchange_sdp(settings: Settings, ephemeral_key: str, offer_sdp: str) -> str:
    """ブラウザの SDP オファーを Azure に中継し、アンサーを取得する。

    Args:
        settings: アプリ設定。
        ephemeral_key: create_client_secret で発行したキー。
        offer_sdp: ブラウザが生成した SDP オファー。

    Returns:
        str: Azure から返された SDP アンサー。
    """
    # エフェメラルキーで WebRTC 接続を確立する
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.post(
            f"{settings.azure_endpoint}/realtime/calls",
            headers={"Authorization": f"Bearer {ephemeral_key}", "Content-Type": "application/sdp"},
            content=offer_sdp,
        )
    res.raise_for_status()
    return res.text
