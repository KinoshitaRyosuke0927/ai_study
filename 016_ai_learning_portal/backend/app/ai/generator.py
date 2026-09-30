"""AI 呼び出しの流れ(呼び出し → 出力の型で検証 → 失敗時は1回だけ再試行 → 記録)。"""

from __future__ import annotations

import json
import time
from typing import TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.ai.client import AIUnavailableError, get_ai_client
from app.ai.prompts import PROMPT_VERSION
from app.models import AIGeneration

T = TypeVar("T", bound=BaseModel)

# 出力の形式が崩れていたときの再試行回数
_RETRIES = 1


class AIOutputError(Exception):
    """AI の応答が、期待する出力の形式になっていない。"""


def generate(
    session: Session,
    output_type: type[T],
    system_prompt: str,
    user_prompt: str,
    model: str,
    purpose: str,
    job_id: int | None = None,
    course_id: int | None = None,
) -> T:
    """
    AI を呼び出し、応答を出力の型で検証して返す(呼び出しはすべて ai_generations に記録する)

    Args
    -----------------
    - session: Session,                 DB セッション(記録の保存に使う)
    - output_type: type[T],             出力の型
    - system_prompt: str,               システムプロンプト
    - user_prompt: str,                 ユーザプロンプト
    - model: str,                       モデル(デプロイ名)
    - purpose: str,                     用途(outline / unit / quiz)
    - job_id: int | None,               生成ジョブ ID
    - course_id: int | None,            講座 ID

    Returns
    -----------------
    - result: T,                        検証済みの出力

    """
    client = get_ai_client()
    prompt = user_prompt
    last_error = ""
    # 初回 + 再試行
    for attempt in range(_RETRIES + 1):
        started = time.monotonic()
        text, error = "", ""
        try:
            # AI を呼び出して、出力の型で検証する
            text = client.complete_json(system_prompt, prompt, model)
            result = output_type.model_validate(json.loads(text))
        except AIUnavailableError as e:
            # 接続できない場合は再試行しない
            _record(session, purpose, model, system_prompt, prompt, text, False, str(e), started, job_id, course_id)
            raise
        except (json.JSONDecodeError, ValidationError) as e:
            # 形式が崩れていた場合は、誤りを伝えて再試行する
            error = f"出力の形式が正しくありません: {e}"
            _record(session, purpose, model, system_prompt, prompt, text, False, error, started, job_id, course_id)
            last_error = error
            prompt = (
                f"{user_prompt}\n\n# 前回の出力の誤り(直して、JSON スキーマに従う JSON だけを返してください)\n"
                f"{str(e)[:2000]}"
            )
            continue
        # 成功を記録して返却
        _record(session, purpose, model, system_prompt, prompt, text, True, "", started, job_id, course_id)
        return result
    # 再試行しても形式が直らなかった
    raise AIOutputError(last_error)


def _record(
    session: Session,
    purpose: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    response_text: str,
    success: bool,
    error: str,
    started: float,
    job_id: int | None,
    course_id: int | None,
) -> None:
    """
    AI 呼び出しの記録を保存する(呼び出し元の処理が失敗しても残るよう、その場で確定する)

    Args
    -----------------
    - session: Session,                 DB セッション
    - purpose: str,                     用途
    - model: str,                       モデル
    - system_prompt: str,               システムプロンプト
    - user_prompt: str,                 ユーザプロンプト
    - response_text: str,               応答
    - success: bool,                    成功したか
    - error: str,                       失敗の内容
    - started: float,                   呼び出し開始時刻(time.monotonic)
    - job_id: int | None,               生成ジョブ ID
    - course_id: int | None,            講座 ID

    """
    # 記録を追加して確定
    session.add(
        AIGeneration(
            job_id=job_id,
            course_id=course_id,
            purpose=purpose,
            model=model,
            prompt_version=PROMPT_VERSION,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_text=response_text,
            success=success,
            error=error,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    )
    session.commit()
