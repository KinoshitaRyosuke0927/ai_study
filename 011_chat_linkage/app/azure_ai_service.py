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
あなたはMattermostの投稿内容から、リマインドメッセージを作成するアシスタントです。
与えられた投稿内容を読み、以下のいずれかに該当するかを判断したうえで、チャンネルに送るための
リマインド文章を日本語で1つ作成してください。

1. 提出物や申請など、期日までの対応・回答が必要な内容の場合
   締め切りの対象・期日を踏まえたリマインド文章を作成してください。締め切りが読み取れない場合も、
   投稿内容にもとづいて確認を促すリマインド文章を作成してください。
   文章例:
   ```
   @channel
   お疲れさまです。
   【提出物／申請名】 の締め切りが 【日付・時刻】 となっておりますので、ご案内申し上げます。
   未提出・未申請の方におかれましては、【提出先・申請先】 より期日までにご対応いただけますと幸いです。
   対応に関してご不明点があれば @【投稿者】 までお願いします。
   何卒よろしくお願いいたします。
   ```

2. 避難訓練・建物工事によるインターネット遮断・停電・システムメンテナンスなど、提出物は不要だが
   予定を調整したり注意する必要がある内容の場合
   提出や回答を求める文面にはせず、実施日時と、注意すべき内容・影響範囲を知らせる文章を作成してください。
   実施日時は必ず投稿内容に記載されている日付・曜日・時刻をそのまま転記してください(年・月・日・
   曜日・時刻のうち投稿内容に含まれるものは省略せず、想像で補ったり書き換えたりしないでください)。
   「記事にてご確認ください」のように日時の確認を読み手に委ねる表現は使わないでください。投稿内容に
   実施日時の記載が本当に無い場合のみ、その旨を明記したうえで確認を促す文章にしてください。
   文章例:
   ```
   @channel
   お疲れさまです。
   【件名】について、下記の通りお知らせいたします。
   実施日時：【投稿内容に記載された日付・曜日・時刻をそのまま転記】
   【注意事項・影響範囲など】
   お手数をおかけしますが、ご対応・ご注意のほどよろしくお願いいたします。
   ```

前置きや説明文は付けず、チャットにそのまま貼り付けられるリマインド文章のみを出力してください。
"""

# 元記事のURLをAIに書かせるとURLを誤って生成する恐れがあるため、
# 一旦このプレースホルダーを出力させ、後で実際のURLに置換する
ARTICLE_URL_PLACEHOLDER = "{{ARTICLE_URL}}"

REMINDER_SYSTEM_PROMPT_WEB = f"""
あなたは社内Webページ(GROUPSESSION)のアナウンス記事から、リマインドメッセージを作成するアシスタントです。
与えられた記事内容を読み、以下のいずれかに該当するかを判断したうえで、チャンネルに送るための
リマインド文章を日本語で1つ作成してください。

1. 提出物や申請など、期日までの対応・回答が必要な内容の場合
   締め切りの対象・期日を踏まえたリマインド文章を作成してください。締め切りが読み取れない場合も、
   記事内容にもとづいて確認を促すリマインド文章を作成してください。
   文章例:
   ```
   @channel
   お疲れさまです。
   【提出物／申請名】 の締め切りが 【日付・時刻】 となっておりますので、ご案内申し上げます。
   未提出・未申請の方におかれましては、【提出先・申請先】 より期日までにご対応いただけますと幸いです。
   対応に関してご不明点があれば [GROUP SESSION]({ARTICLE_URL_PLACEHOLDER}) をご確認お願いいたします。
   何卒よろしくお願いいたします。
   ```

2. 避難訓練・建物工事によるインターネット遮断・停電・システムメンテナンスなど、提出物は不要だが
   予定を調整したり注意する必要がある内容の場合
   提出や回答を求める文面にはせず、実施日時と、注意すべき内容・影響範囲を知らせる文章を作成してください。
   実施日時は必ず記事内容に記載されている日付・曜日・時刻をそのまま転記してください(年・月・日・
   曜日・時刻のうち記事内容に含まれるものは省略せず、想像で補ったり書き換えたりしないでください)。
   「記事にてご確認ください」のように日時の確認を読み手に委ねる表現は使わないでください。記事内容に
   実施日時の記載が本当に無い場合のみ、その旨を明記したうえで確認を促す文章にしてください。
   文章例:
   ```
   @channel
   お疲れさまです。
   【件名】について、下記の通りお知らせいたします。
   実施日時：【記事内容に記載された日付・曜日・時刻をそのまま転記】
   【注意事項・影響範囲など】
   詳細は [GROUP SESSION]({ARTICLE_URL_PLACEHOLDER}) をご確認ください。
   お手数をおかけしますが、ご対応・ご注意のほどよろしくお願いいたします。
   ```

いずれの場合も、GROUP SESSIONへのリンクを記載する箇所は、必ず例の通り "{ARTICLE_URL_PLACEHOLDER}" という
文字列をそのまま出力してください(実際のURLには書き換えないでください)。
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
