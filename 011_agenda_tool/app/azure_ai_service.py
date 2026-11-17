from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# 環境変数(.env)を読み込む
if getattr(sys, "frozen", False):
    _env_path = Path(sys.executable).resolve().parent / ".env"
else:
    _env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_env_path)

## Azure OpenAI の接続情報を環境変数から取得
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY", "")
# デプロイしたモデルの名称
MODEL_NAME = "gpt-6-luna"

# Azure OpenAI クライアント用意
client = OpenAI(
    base_url=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY
)

AGENDA_SYSTEM_PROMPT = """
あなたは社内の部署定例会で使うアジェンダの「全体共有事項」の欄を作成するアシスタントです。
複数のMattermost投稿・GROUPSESSION記事の内容が与えられます。それぞれの内容を簡潔にまとめ、
指定されたJSONスキーマに従って、アジェンダの1項目ずつを "items" の要素として出力してください。

この会話の前半には、過去に実際に部会で使ったアジェンダの実例(入力と、人が書いた出力)があります。
後ろの実例ほど新しく、よりよい手本です。要約の粒度・残す情報の選び方・文体・言い回しは、
実例(特に新しいもの)に合わせてください。

入力の各要素には "index"(0始まりの番号)があります。出力の各項目の "source_indexes" には、
その項目の元になった入力の "index" を入れてください。元の投稿・記事へのリンクはアプリ側で
"source_indexes" をもとに見出しへ付けるため、見出しにリンクを付けてはいけません。

各フィールドの意味は以下のとおりです。
- "title": 項目の見出し(タイトルや要件)。元の投稿・記事のタイトルをもとに、短く簡潔にしてください。
- "title_note": 見出しの後ろに添える一言(例: "期限：11/30(日)"、"実施日：4/25(金)12:00～")。
  補足が1つだけで短い場合に使い、無ければ空文字にしてください。
- "details": 見出しの下に箇条書きで書く補足情報を1行ずつ。
    - "text": 補足情報の本文
    - "children": その補足情報をさらに細かく説明する行(無ければ空の配列)

以下のルールに従ってください。
- 締め切り・実施日時・参加条件・提出先など、重要な情報は省略せず残してください。
- メンバーに作業を依頼している項目では、何を・いつまでに行えばよいかがわかるようにしてください。
  元の投稿・記事から読み取れない手順や情報を、推測や一般的な知識で補ってはいけません。
- 入力の投稿・記事は、いずれかの項目の "source_indexes" に必ず含めてください。
  関連する内容であればまとめても構いません(その場合 "source_indexes" に複数の index を入れてください)が、
  無関係な項目は分けて記載してください。
- 見出しの先頭の "- " などのMarkdownの箇条書き記号は付けないでください(アプリ側で付けます)。
- 本文中でURLを使う場合は、元の投稿・記事に書かれているURLをそのまま使ってください。
  元の投稿・記事に無いURLを書いてはいけません。
"""

# AIの出力形式(Structured Outputs の JSON スキーマ)。
# strict モードでは全プロパティを required にし、additionalProperties を false にする必要がある
AGENDA_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_indexes": {"type": "array", "items": {"type": "integer"}},
                    "title": {"type": "string"},
                    "title_note": {"type": "string"},
                    "details": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "children": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["text", "children"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["source_indexes", "title", "title_note", "details"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def _build_input_payload(items: list[dict]) -> str:
    """
    AIへの入力(投稿・記事の一覧)をJSON文字列にする

    Args
    -----------------
    - items: list[dict],  投稿・記事一覧(各要素は "message", "username" を持つ)

    Returns
    -----------------
    - payload: str,  [{"index", "message", "username"}] のJSON文字列。
                     URLはAIに渡さず、index で元の投稿・記事を参照させる

    """
    return json.dumps(
        [
            {"index": i, "message": item["message"], "username": item.get("username", "")}
            for i, item in enumerate(items)
        ],
        ensure_ascii=False,
    )


def _build_example_messages(examples: list[dict]) -> list[dict]:
    """
    過去アジェンダの手本を、few-shot用の会話(入力 → 出力の組)に変換する

    Args
    -----------------
    - examples: list[dict],  手本の一覧(古い順)。各要素は {"page", "items": [{"input", "output"}]}
                              (agenda_examples.json の形式)

    Returns
    -----------------
    - messages: list[dict],  user(入力)/ assistant(出力)を交互に並べたメッセージ一覧

    """
    messages: list[dict] = []
    for example in examples:
        # アジェンダ1回分を、1組の入力・出力にする(項目の順番がそのまま index になる)
        inputs = [item["input"] for item in example["items"]]
        outputs = [
            {"source_indexes": [i], **item["output"]}
            for i, item in enumerate(example["items"])
        ]
        messages.append({"role": "user", "content": _build_input_payload(inputs)})
        messages.append({"role": "assistant", "content": json.dumps({"items": outputs}, ensure_ascii=False)})
    return messages


def call_generate_agenda(items: list[dict], examples: list[dict] | None = None) -> list[dict]:
    """
    投稿・記事の一覧をもとに、Azure OpenAIで部署定例会アジェンダの
    「全体共有事項」欄の内容を構造化データ(JSON)として生成する

    Args
    -----------------
    - items: list[dict],            アジェンダに含める投稿・記事一覧
                                     (各要素は "message", "username", "source", "url" を持つ)
    - examples: list[dict] | None,  few-shotで渡す過去アジェンダの手本(古い順)。None・空なら手本なしで生成する

    Returns
    -----------------
    - agenda_items: list[dict],  アジェンダの項目一覧(AGENDA_RESPONSE_SCHEMA の "items")。
                                  各要素は "source_indexes", "title", "title_note", "details" を持つ

    """
    # システムプロンプト → 過去の手本(入力・出力の組)→ 今回の入力 の順に並べる
    messages = [
        {"role": "system", "content": AGENDA_SYSTEM_PROMPT},
        *_build_example_messages(examples or []),
        {"role": "user", "content": _build_input_payload(items)},
    ]

    # Structured Outputs(JSONスキーマ指定)でAIを呼び出す
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "agenda_items",
                "strict": True,
                "schema": AGENDA_RESPONSE_SCHEMA,
            },
        },
    )

    # 応答を検証する(安全上の理由で応答が拒否された場合・JSONでない場合はエラーにする)
    message = response.choices[0].message
    if getattr(message, "refusal", None):
        raise ValueError(f"AIが応答を拒否しました: {message.refusal}")
    try:
        result = json.loads(message.content or "")
    except json.JSONDecodeError as exc:
        raise ValueError("AIの応答をJSONとして読み取れませんでした") from exc

    return result.get("items", [])
