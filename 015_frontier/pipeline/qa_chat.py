"""「Q&A」画面のチャット応答(エージェントループ)。

このプロジェクトで DB に蓄積された分析結果(設計書/コード分析、実装差分、KPT、暗黙知、
アクティビティ分析)や元データを pipeline/qa_tools.py の Tool Calling 経由で検索し、その
結果を踏まえて回答する。1 回の質問で情報が揃わない場合、AI は複数回ツールを呼び出せる。

会話履歴はサーバー側で保持せず、画面から送られてきた history をそのまま messages に
変換して呼び出す(ステートレス)。ツール呼び出しのやり取りはこの 1 リクエスト内で完結する。
画面へは最終的な回答本文に加えて、根拠にしたファイル/分析結果(citations)も返し、
Q&A画面の右エリアに「回答の根拠」として表示できるようにする。
"""

from __future__ import annotations

import json
import logging

from openai import OpenAI

from config.settings import Settings
from pipeline import qa_tools

logger = logging.getLogger(__name__)

MODEL_NAME = "gpt-5.4-mini"
MAX_TOOL_ITERATIONS = 6  # ツール呼び出しの往復回数の上限(無限ループ防止)

SYSTEM_PROMPT = """\
あなたは開発プロジェクト支援ツール「Frontier」の Q&A アシスタントです。
プロジェクトメンバーからの質問に、このプロジェクトで蓄積された分析結果を検索した上で、
具体的かつ簡潔に日本語で回答してください。

方針:
- 質問に答えるために必要な情報は、まず与えられたツールを使って調べてください。
  推測や一般論だけで即答せず、関連しそうなツールを積極的に呼び出してください。
- 検索は次の優先順で行ってください:
  1. まず分析結果を検索する(search_design_code / search_spec_diff / search_kpt /
     search_tacit_knowledge / search_user_activity)。これらは既に要約・整理された情報です。
  2. 分析結果だけでは情報が不十分、具体性に欠ける、または該当が見つからないと判断した場合は、
     search_raw_data で元データ(Mattermost投稿・Trelloカード・コード変更履歴・GitHub活動)を
     直接検索してください。
  3. 仕様の原文そのもの(設計書の文言、コードの実装)を確認する必要がある場合は、
     search_design_code の refs(file_path・start_line・end_line)を使って read_repo_file で
     実ファイルを直接読んでください。要約(overview/sections)だけで断定せず、重要な仕様
     判断の根拠にする場合は原文を確認することを優先してください。
- 「誰が詳しいか」「担当者は誰か」といった、人を特定する質問には find_experts を使ってください。
  結果は日本語の表示名で返るので、そのまま回答に使えます(アルファベットのアカウント名を
  勝手に人名として使わないでください)。
- 「機能追加/変更の影響範囲」「他にどこを直す必要があるか」といった影響度調査の質問には
  assess_impact を使ってください。まず search_design_code で対象機能の仕様・設計上の
  影響を説明し、その上で assess_impact が返すコードファイル(直接の影響範囲・
  co-change候補)を使って、具体的に触る可能性があるファイルを挙げてください。
- 1 回のツール呼び出しで十分な情報が得られない場合は、キーワードを変えたり、
  別のツールを試したりして、複数回検索して構いません。
- ツールで調べても十分な情報が見つからない場合は、正直にその旨を伝えてください。
  分からないことを推測で断定しないでください。
- 質問があいまいで、何を検索すればよいか判断できない場合は、検索を試みた上で、
  回答の代わりに具体的な確認の質問を返しても構いません。
- 回答文中に「根拠:」「参照した情報:」のような形で出典を逐一列挙する必要はありません。
  何を調べて回答したかは、ユーザーから明示的に聞かれた場合にだけ答えてください。
  普段は結論と説明だけを簡潔に述べてください。

図・画像について:
- ユーザーが「図で示して」等、視覚的な説明を求めている場合や、処理の流れ・関係性が
  文章より図の方が伝わりやすいと判断した場合は、回答本文に Mermaid 記法のコードブロック
  (```mermaid で始まるコードブロック)を含めてください。画面が自動的に図として描画します。
  フローチャート・シーケンス図・ER図など、Mermaidの記法に沿った正しい構文で書いてください。
- 実写・イラスト風の説明画像など、Mermaidでは表現しにくい画像が必要な場合は
  generate_image を使ってください(gpt-image-2 による生成)。
- 「コードにするとどうなりますか」といったコード例を求める質問には、回答本文に
  通常のコードブロック(```言語名)で例を示してください。

フォローアップの提案について(重要):
- 「必要なら次に、○○を調べます」「他にも□□を探せます」のような、次の一手を案内する文章を
  本文中(通常の文章や箇条書き)に書くことは禁止します。次の一手を提案したい場合は、
  必ず ```suggestions というコードブロックの中に、1 行につき 1 つ書いてください
  (見出しや箇条書き記号・番号・前置きの文章は付けない。文言そのものだけを書く)。
  画面側でボタンとして表示され、クリックするとその文言がそのまま「ユーザー自身の次の発言」
  として送信されます。
- そのため、各行は必ずユーザー自身が言う/尋ねるセリフとして書いてください
  (例: "CSV変換の本来の実装箇所も確認して" / "他にProblemはある?")。
  「〜しますか?」「〜できます」のように、あなた(アシスタント)からユーザーへの問いかけや
  提案の言い回しにしないでください(クリックした本人が自分自身に問いかける形になり不自然です)。
- 提案したい内容が無ければ、本文でもほのめかさず、suggestions ブロックも省略してください。
"""


class QaChatError(Exception):
    """Azure OpenAI 未設定、または応答の取得に失敗した場合。"""


def _build_client(settings: Settings) -> OpenAI:
    return OpenAI(base_url=settings.azure_openai_endpoint, api_key=settings.azure_openai_api_key)


def _tool_call_to_message(tool_call) -> dict:
    """SDK の tool_call オブジェクトを、次回リクエストに含める dict へ変換する。"""
    return {
        "id": tool_call.id,
        "type": "function",
        "function": {"name": tool_call.function.name, "arguments": tool_call.function.arguments},
    }


# ツール結果 1 件から、画面の右エリアに「根拠」として表示できる形を抜き出す。
# ツールごとに結果の形が違うため、citation の type ごとに必要な項目だけ拾う。
def _extract_citations(tool_name: str, args: dict, result: dict) -> list[dict]:
    if not isinstance(result, dict) or result.get("error"):
        return []

    if tool_name == "read_repo_file" and result.get("content"):
        return [{
            "type": "file",
            "label": result.get("file_path") or args.get("file_path", ""),
            "file_path": result.get("file_path"),
            "start_line": result.get("start_line"),
            "end_line": result.get("end_line"),
            "content": result.get("content"),
        }]

    if tool_name == "generate_image" and result.get("image_base64"):
        return [{
            "type": "image",
            "label": (args.get("prompt") or result.get("prompt") or "生成画像")[:60],
            "prompt": result.get("prompt"),
            "mime": result.get("mime", "image/png"),
            "image_base64": result.get("image_base64"),
        }]

    if tool_name == "search_design_code":
        return [
            {
                "type": "feature",
                "label": it.get("name") or "",
                "kind": it.get("kind"),
                "overview": it.get("overview"),
                "refs": it.get("refs") or [],
            }
            for it in result.get("items", [])
        ]

    if tool_name == "search_spec_diff":
        return [
            {
                "type": "spec_diff",
                "label": it.get("feature_name") or "",
                "severity": it.get("severity"),
                "summary": it.get("summary"),
            }
            for it in result.get("items", [])
        ]

    if tool_name == "search_tacit_knowledge":
        return [
            {
                "type": "tacit",
                "label": it.get("title") or "",
                "source": it.get("source"),
                "rating": it.get("rating"),
                "content": it.get("content"),
            }
            for it in result.get("items", [])
        ]

    if tool_name == "search_raw_data":
        return [
            {
                "type": "raw_data",
                "label": f'{it.get("source_label") or it.get("source")}',
                "source": it.get("source"),
                "ref": it.get("ref"),
                "content": it.get("text"),
            }
            for it in result.get("items", [])
        ]

    if tool_name == "assess_impact":
        return [
            {"type": "file_ref", "label": f.get("file_path") or "", "file_path": f.get("file_path")}
            for f in result.get("impacted_files_direct", [])
        ]

    return []  # search_kpt / search_user_activity / find_experts は「根拠ファイル」を持たないため対象外


def _dedupe_citations(citations: list[dict], limit: int = 20) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for c in citations:
        key = (c.get("type"), c.get("label"), c.get("start_line"), c.get("end_line"))
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
        if len(out) >= limit:
            break
    return out


def call_chat(settings: Settings, history: list[dict[str, str]]) -> dict:
    """会話履歴(history: [{"role": "user"|"assistant", "content": ...}])から応答を返す。

    必要に応じて pipeline/qa_tools.py のツールを複数回呼び出しながら回答を組み立てる。

    Returns:
        {"message": 回答本文, "citations": 根拠にしたファイル/分析結果のリスト}
    """
    if not settings.ai_enabled:
        raise QaChatError(
            "Azure OpenAI が未設定です(.env の AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY を確認してください)"
        )
    client = _build_client(settings)
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}, *history]
    citations: list[dict] = []

    for iteration in range(MAX_TOOL_ITERATIONS):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME, messages=messages, tools=qa_tools.TOOLS
            )
        except Exception as exc:
            logger.error("Q&A チャットの AI 呼び出しに失敗: %s", exc)
            raise QaChatError(f"AI 呼び出しに失敗しました: {exc}") from exc

        usage = getattr(response, "usage", None)
        if usage is not None:
            logger.info(
                "Q&A チャット AI トークン [iter=%d] prompt=%s completion=%s total=%s",
                iteration,
                getattr(usage, "prompt_tokens", "?"),
                getattr(usage, "completion_tokens", "?"),
                getattr(usage, "total_tokens", "?"),
            )

        msg = response.choices[0].message
        if not msg.tool_calls:
            return {"message": msg.content or "", "citations": _dedupe_citations(citations)}

        # アシスタントのツール呼び出し指示を履歴へ積む
        messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [_tool_call_to_message(tc) for tc in msg.tool_calls],
        })

        # 各ツールを実行し、結果を tool ロールで履歴へ積む(+根拠として抜き出す)
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            logger.info("Q&A ツール呼び出し [iter=%d] %s(%s)", iteration, tc.function.name, args)
            result = qa_tools.execute_tool(tc.function.name, args)
            citations.extend(_extract_citations(tc.function.name, args, result))

            # 画像の base64 本体は巨大でトークンを大きく消費するため、AI へは結果の要約だけを返す
            # (画面には citations 経由で別途フル画像を渡す)。
            if tc.function.name == "generate_image" and result.get("image_base64"):
                tool_result_for_model = {"status": "success", "note": "画像を生成し、画面(右エリア)に表示しました。"}
            else:
                tool_result_for_model = result

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(tool_result_for_model, ensure_ascii=False),
            })

    raise QaChatError("ツール呼び出しの回数が上限に達しました。質問を分けて試してください。")
