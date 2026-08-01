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

# 元記事のURLをAIに書かせるとURLを誤って生成する恐れがあるため、
# 一旦このプレースホルダーを出力させ、後で実際のURLに置換する
ARTICLE_URL_PLACEHOLDER = "{{ARTICLE_URL}}"

REMINDER_SYSTEM_PROMPT_WEB = f"""
あなたは社内Webページ(GROUPSESSION)のアナウンス記事から、提出物や申請の締め切りに関するリマインドメッセージを作成するアシスタントです。
与えられた記事内容を読み、締め切りの対象・期日を踏まえて、チャンネルに送るためのリマインド文章を日本語で1つ作成してください。
締め切りが読み取れない場合も、記事内容にもとづいて確認を促すリマインド文章を作成してください。

以下にリマインド文章例を記載します。
```
@channel
お疲れさまです。
【提出物／申請名】 の締め切りが 【日付・時刻】 となっておりますので、ご案内申し上げます。
未提出・未申請の方におかれましては、【提出先・申請先】 より期日までにご対応いただけますと幸いです。
対応に関してご不明点があれば [GROUP SESSION]({ARTICLE_URL_PLACEHOLDER}) をご確認お願いいたします。
何卒よろしくお願いいたします。

※こちらはAIによる自動投稿です。
```

「対応に関してご不明点があれば」の行は、必ず例の通り "{ARTICLE_URL_PLACEHOLDER}" という文字列をそのまま出力してください(実際のURLには書き換えないでください)。
前置きや説明文は付けず、チャットにそのまま貼り付けられるリマインド文章のみを出力してください。
"""

AGENDA_SYSTEM_PROMPT = """
あなたは社内の部署定例会で使うアジェンダの「全体共有事項」の欄を作成するアシスタントです。
複数のMattermost投稿・GROUPSESSION記事の内容が与えられます。それぞれの内容を簡潔にまとめ、
Markdownの箇条書き(先頭に "- ")で1項目ずつ記載してください。

入力の各項目には "url_placeholder" というキーがあります。これは元となったMattermost投稿・
GROUPSESSION記事へのリンク先を表すプレースホルダー文字列です(実際のURLは後で別処理により
置換されるため、あなたはこの文字列の中身を書き換えたり、実際のURLを想像して出力したりしては
いけません)。

以下のルールに従ってください。
- 締め切り・実施日時・参加条件・提出先など、重要な情報は省略せず残してください。
- "url_placeholder" が null でない項目は、見出しを [タイトルや要件](url_placeholder) の形式の
  Markdownリンクにしてください。このとき "url_placeholder" の文字列は一切変更せず、与えられた
  ものをそのまま "(" と ")" の間に埋め込んでください。
- "url_placeholder" が null の項目は、タイトルや要件のみのテキストにしてください(リンクは付けないでください)。
- 必要に応じて、箇条書きの下にネストした箇条書き(半角スペース4つでインデント)で補足情報(期間・場所・金額など)を追加してください。
- 項目同士は関連する内容であればまとめても構いませんが、無関係な項目は分けて記載してください。
- 前置きや説明文、見出し(##や####など)は付けず、箇条書きの本文のみを出力してください。

以下に出力のサンプルを記載します(実際にはurl_placeholderの文字列がそのまま(...)内に入ります)。
```
- 勤怠・交通費申請 　期限：7/2(木)
- [健康診断実施について]({{URL_1}})
    - 検診実施後には、Excel上に受診日を記入すること
- [ストレスチェック]({{URL_2}})
    - メールアドレス宛に案内が届く
    - 実施期間：7/1(水)～7/31(金)
- [親睦旅行について]({{URL_3}})
    - 実施期間：9/1(火)～11/30(月)
    - 予算：￥20,000/人（＋交通費：￥3,000）
    - 実施までの流れ
```
"""

FILTER_SYSTEM_PROMPT = """
あなたはMattermostの投稿一覧から、リマインドが必要な投稿を判定するアシスタントです。
「期日が設定されている提出物や申請」「回答する必要がある」内容の投稿のみを対象とし、
それ以外の雑談・情報共有・お礼・完了報告などは対象外としてください。

入力は投稿のリスト(id, message)を含むJSONです。
出力は次の形式のJSONオブジェクトのみを返してください。前置きや説明文は不要です。
{"ids": ["対象となる投稿のidのリスト"]}
該当する投稿がない場合は {"ids": []} を返してください。
"""


def call_generate_reminder(post_message: str, author_username: str, source_url: str | None = None) -> str:
    """
    投稿内容と投稿者名をもとに、Azure OpenAIでリマインド文章を生成する

    Args
    -----------------
    - post_message: str,          リマインド対象の投稿・記事の内容
    - author_username: str,       元投稿の投稿者ユーザー名
    - source_url: str | None,     元記事のURL(GROUPSESSION記事の場合のみ指定する)

    Returns
    -----------------
    - reminder: str,          生成されたリマインド文章

    """
    if source_url:
        system_prompt = REMINDER_SYSTEM_PROMPT_WEB
        user_content = f"投稿者: {author_username}\n記事内容:\n{post_message}"
    else:
        system_prompt = REMINDER_SYSTEM_PROMPT
        user_content = f"投稿者: {author_username}\n投稿内容:\n{post_message}"

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    reminder = response.choices[0].message.content.strip()

    if source_url:
        reminder = reminder.replace(ARTICLE_URL_PLACEHOLDER, source_url, 1)

    return reminder


def call_generate_agenda(items: list[dict]) -> str:
    """
    投稿・記事の一覧をもとに、Azure OpenAIで部署定例会アジェンダの
    「全体共有事項」欄の文章(Markdown箇条書き)を生成する

    Args
    -----------------
    - items: list[dict],  アジェンダに含める投稿・記事一覧
                           (各要素は "message", "username", "source", "url" を持つ)

    Returns
    -----------------
    - agenda_body: str,   生成された「全体共有事項」欄の文章

    """
    # URLをAIに直接書かせるとURLを誤って生成・改変する恐れがあるため、
    # 一旦プレースホルダーを出力させ、後で実際のURLに置換する
    placeholder_urls: dict[str, str] = {}
    payload_items = []
    for i, item in enumerate(items):
        url = item.get("url")
        placeholder = f"{{{{URL_{i}}}}}" if url else None
        if placeholder:
            placeholder_urls[placeholder] = url
        payload_items.append({
            "message": item["message"],
            "username": item.get("username", ""),
            "url_placeholder": placeholder,
        })

    payload = json.dumps(payload_items, ensure_ascii=False)
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": AGENDA_SYSTEM_PROMPT},
            {"role": "user", "content": payload},
        ],
    )
    agenda_body = response.choices[0].message.content.strip()

    for placeholder, url in placeholder_urls.items():
        agenda_body = agenda_body.replace(placeholder, url)

    return agenda_body


def call_filter_reminder_posts(posts: list[dict]) -> set[str]:
    """
    投稿一覧から、期日のある提出物・申請や回答が必要な投稿のみをAIで判定し、
    該当する投稿の id 集合を返す

    Args
    -----------------
    - posts: list[dict],  判定対象の投稿一覧 (各要素は "id", "message" を持つ)

    Returns
    -----------------
    - ids: set[str],      リマインド対象と判定された投稿idの集合

    """
    if not posts:
        return set()

    payload = json.dumps(
        [{"id": p["id"], "message": p["message"]} for p in posts],
        ensure_ascii=False,
    )
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": FILTER_SYSTEM_PROMPT},
            {"role": "user", "content": payload},
        ],
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    data = json.loads(content)
    return set(data.get("ids", []))
