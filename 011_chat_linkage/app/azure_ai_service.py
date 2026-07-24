from __future__ import annotations

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
MODEL_NAME = "gpt-5.4-mini"

# Azure OpenAI クライアント用意
client = OpenAI(
    base_url=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY
)

REMINDER_SYSTEM_PROMPT = """
あなたはMattermostの投稿内容から、提出物や申請の締め切りに関するリマインドメッセージを作成するアシスタントです。
与えられた投稿内容を読み、締め切りの対象・期日を踏まえて、チャンネルに送るためのリマインド文章を日本語で1つ作成してください。
締め切りが読み取れない場合も、投稿内容にもとづいて確認を促すリマインド文章を作成してください。

以下にリマインド文章例を記載します。
```
@channel
お疲れさまです。
【提出物／申請名】 の締め切りが 【日付・時刻】 となっておりますので、ご案内申し上げます。
未提出・未申請の方におかれましては、【提出先・申請先】 より期日までにご対応いただけますと幸いです。
対応に関してご不明点があれば @【投稿者】 までお願いします。
何卒よろしくお願いいたします。

※こちらはAIによる自動投稿です。
```

前置きや説明文は付けず、チャットにそのまま貼り付けられるリマインド文章のみを出力してください。
"""


def call_generate_reminder(post_message: str, author_username: str) -> str:
    """
    投稿内容と投稿者名をもとに、Azure OpenAIでリマインド文章を生成する

    Args
    -----------------
    - post_message: str,      リマインド対象のMattermost投稿内容
    - author_username: str,   元投稿の投稿者ユーザー名

    Returns
    -----------------
    - reminder: str,          生成されたリマインド文章

    """
    user_content = f"投稿者: {author_username}\n投稿内容:\n{post_message}"
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": REMINDER_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    )
    return response.choices[0].message.content.strip()
