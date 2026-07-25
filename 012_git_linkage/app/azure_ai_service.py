from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY", "")
MODEL_NAME = "gpt-5.4-mini"

client = OpenAI(
    base_url=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY,
)

DIFF_SUMMARY_SYSTEM_PROMPT = """
あなたはGitHubのプルリクエストのdiff(コード差分)を読み、変更内容をチームメンバーに共有するための
要約メッセージを日本語で作成するアシスタントです。

以下の観点を踏まえて簡潔にまとめてください。
- 何を目的とした変更か(推測できる範囲で)
- 主な変更点(機能追加・修正・リファクタリング等の種別ごとに整理)
- 変更されたファイルの傾向(重要そうなファイルがあれば触れる)

出力形式の例:
```
【マージ通知】 #<PR番号> <PRタイトル>
マージ者: <author>
対象: <head_branch> -> <base_branch>

■ 変更概要
・(要約内容)

■ 主な変更ファイル
・(ファイル名など)
```

前置きや説明文は付けず、チャットにそのまま貼り付けられるメッセージのみを出力してください。
"""


def call_summarize_diff(
    diff_text: str,
    files_summary: list[dict],
    pr_number: int,
    pr_title: str,
    author: str,
    base_branch: str,
    head_branch: str,
) -> str:
    """PRのdiffとファイル一覧をもとに、Azure OpenAIで変更内容の要約メッセージを生成する。"""
    files_text = "\n".join(
        f"- {f['filename']} ({f['status']}, +{f['additions']}/-{f['deletions']})"
        for f in files_summary
    )
    user_content = (
        f"PR番号: #{pr_number}\n"
        f"タイトル: {pr_title}\n"
        f"マージ者: {author}\n"
        f"ブランチ: {head_branch} -> {base_branch}\n\n"
        f"変更ファイル一覧:\n{files_text}\n\n"
        f"差分(diff):\n{diff_text}"
    )
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": DIFF_SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    )
    return response.choices[0].message.content.strip()
