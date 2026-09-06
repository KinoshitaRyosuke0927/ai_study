"""「Trello 情報解析」の AI 処理(2 段)。

1. list_team_themes(): ボード名・リスト名・カードタイトルから、このチームの作業テーマを洗い出す
   (1 コール、任意)。2 段目に共通コンテキストとして渡す。
2. analyze_account(): 1 アカウントについて、ボード横断の活動(担当カード・コメント・操作)を渡し、
   担当している作業・コメントの傾向・関わる工程・他メンバーとの連携 などを分析する(並列)。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI

from config.settings import Settings

logger = logging.getLogger(__name__)

MODEL_NAME = "gpt-5.4-mini"

THEMES_SYSTEM_PROMPT = """\
チームの Trello ボード(ボード名・リスト名・カードタイトルのサンプル)が与えられます。
このチームが実際に進めている作業テーマを、日本語の短い名詞句で 30 個以内に洗い出してください。

- カードタイトルに現れる具体的な案件・機能・作業・障害・イベントなどを挙げる。
- 一般語(「対応」「確認」など)だけの項目は避け、できるだけ具体的にする。
- 前置きや説明は付けず、次の形式の JSON オブジェクトのみを出力してください:
  {"themes": ["...", "..."]}
"""

ACCOUNT_SYSTEM_PROMPT = """\
1 人のアカウントについて、複数ボードにまたがる Trello の活動(担当カード、書いたコメント、
行った操作の要約)と活動統計が与えられます。このアカウントがチームでどのような作業・活動を
しているかを、与えられた内容だけを根拠に日本語で分析してください。

観点(該当するもののみ):
- 担当・推進している作業や案件(どのボード/リストのカードか)
- コメントの傾向(指示・報告・レビュー・質問・相談 など)
- よく関わるボード・リスト(≒担当している工程)
- 他メンバーとの連携(誰と同じカードで動くか、依頼/引き継ぎ など)
- 目立った貢献・意思決定
- 気になる点(停滞カード、担当の偏り、期限超過 など)

ルール:
- 与えられた活動・統計に無いことを推測で補わないでください。
- sections は見出し(heading)と本文(body)の配列です。body は箇条書きを含む
  プレーンテキストで記述してください(Markdown 記法は使わない)。
- 前置きや説明は付けず、次の形式の JSON オブジェクトのみを出力してください:
  {"overview": "1〜2文の要約", "sections": [{"heading": "...", "body": "..."}]}
"""


class TrelloAnalysisError(Exception):
    """Azure OpenAI 未設定、または AI 応答を解析できなかった場合。"""


def _build_client(settings: Settings) -> OpenAI:
    return OpenAI(
        base_url=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
    )


def _strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def _call_chat(settings: Settings, system_prompt: str, user_prompt: str, label: str = "") -> Any:
    client = _build_client(settings)
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        logger.error("Trello 分析の AI 呼び出しに失敗 [%s]: %s", label or "-", exc)
        raise TrelloAnalysisError(f"AI 呼び出しに失敗しました: {exc}") from exc

    usage = getattr(response, "usage", None)
    if usage is not None:
        logger.info(
            "Trello 分析 AI トークン [%s] prompt=%s completion=%s total=%s",
            label or "-",
            getattr(usage, "prompt_tokens", "?"),
            getattr(usage, "completion_tokens", "?"),
            getattr(usage, "total_tokens", "?"),
        )

    raw = _strip_code_fence(response.choices[0].message.content or "")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Trello 分析 応答の JSON 解析に失敗 [%s]: %s / raw=%s", label or "-", exc, raw[:500])
        raise TrelloAnalysisError("AI 応答を解析できませんでした") from exc


# ----------------------------------------------------------------------
# 1 段目: チームの作業テーマ(任意)
# ----------------------------------------------------------------------
def list_team_themes(
    settings: Settings, cards: list[dict[str, Any]], max_cards: int = 200
) -> list[str]:
    """ボード/リスト/カードタイトルから作業テーマを洗い出す。失敗時は []。"""
    if not settings.ai_enabled or not cards:
        return []
    by_board: dict[str, dict[str, list[str]]] = {}
    for c in cards[:max_cards]:
        by_board.setdefault(c["board_name"], {}).setdefault(c["list_name"], []).append(c["name"])
    payload = {
        "boards": [
            {"name": b, "lists": [{"name": ln, "cards": titles[:20]} for ln, titles in lists.items()]}
            for b, lists in by_board.items()
        ]
    }
    try:
        parsed = _call_chat(
            settings, THEMES_SYSTEM_PROMPT, json.dumps(payload, ensure_ascii=False), label="1段目:テーマ"
        )
    except TrelloAnalysisError:
        return []
    raw = parsed.get("themes", []) if isinstance(parsed, dict) else []
    return [str(x).strip() for x in raw if str(x).strip()][:30]


# ----------------------------------------------------------------------
# 2 段目: アカウント単位の分析
# ----------------------------------------------------------------------
def analyze_account(
    settings: Settings, account: dict[str, Any], themes: list[str]
) -> dict[str, Any]:
    """1 アカウントについて、ボード横断の活動から担当作業・傾向・連携を分析する。

    Returns
    -----------------
    - {"overview": str, "sections": [{"heading", "body"}]}

    Raises
    -----------------
    - TrelloAnalysisError: Azure OpenAI 未設定、AI 呼び出し失敗、応答解析失敗
    """
    if not settings.ai_enabled:
        raise TrelloAnalysisError(
            "Azure OpenAI が未設定です(.env の AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY を確認してください)"
        )

    name = account.get("full_name") or account.get("username", "")
    user_prompt = (
        f"アカウント: {account.get('username', '')}"
        + (f"({name})" if name and name != account.get("username") else "")
        + "\n"
        f"活動統計: {json.dumps(account.get('stats', {}), ensure_ascii=False)}\n"
        + (f"チームの作業テーマ(参考): {', '.join(themes)}\n" if themes else "")
        + "\n=== このアカウントの活動(ボード横断)===\n"
        + (account.get("context") or "(活動なし)")
    )
    parsed = _call_chat(
        settings, ACCOUNT_SYSTEM_PROMPT, user_prompt, label=f"2段目:{account.get('username', '?')}"
    )
    if not isinstance(parsed, dict):
        raise TrelloAnalysisError("AI 応答の形式が想定と異なります")

    sections: list[dict[str, str]] = []
    for sec in parsed.get("sections", []) or []:
        if not isinstance(sec, dict):
            continue
        heading = str(sec.get("heading", "")).strip()
        body = str(sec.get("body", "")).strip()
        if not heading and not body:
            continue
        sections.append({"heading": heading or "(見出しなし)", "body": body})

    return {
        "overview": str(parsed.get("overview", "")).strip(),
        "sections": sections,
    }
