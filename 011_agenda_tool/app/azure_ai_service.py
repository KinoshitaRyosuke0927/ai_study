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
- 文章は基本的に「です・ます」調で記載してください(「〜すること」「〜が必要」「〜を選択」のような
  言い切り・体言止めの文は「〜してください」「〜が必要です」「〜を選択します」のように書き換えてください)。
  ただし、リンクの見出し([タイトルや要件]の部分)と、「実施期間：7/1(水)～7/31(金)」のような
  「項目名：値」形式の行は、です・ます調にせずそのままで構いません。

メンバーに作業(申請・提出・回答・ソフトウェアの更新・設定変更など)を依頼している項目では、
お知らせの内容に加えて、メンバーが「何を・いつまでに・どうやって」行えばよいかが
アジェンダを読むだけでわかるように、次のルールで記載してください。
- 作業が必要であることと期日を、ネストした箇条書きの先頭に「【要対応】」を付けて記載してください。
- 元の投稿・記事に作業の手順や方法(操作する画面・メニュー、実行するコマンド、提出先、
  記入する内容など)が書かれている場合は、その手順をネストした箇条書きで
  具体的に記載してください。手順が複数ある場合は、さらにネストして順番に記載してください。
- 元の投稿・記事から具体的な手順が読み取れない場合は、手順を推測して書いてはいけません。
  一般的な知識(例: 一般的なソフトウェアの更新方法)で補うことも禁止です。
  その場合は「【要対応】」の行(作業が必要であることと期日)のみを記載し、手順は書かないでください。
- 作業の依頼が無い、単なるお知らせの項目には「【要対応】」を付けないでください。

以下に出力のサンプルを記載します(実際にはurl_placeholderの文字列がそのまま(...)内に入ります)。
```
- 勤怠・交通費申請 　期限：7/2(木)
- [健康診断実施について]({{URL_1}})
    - 【要対応】検診実施後に、Excel上に受診日を記入してください
- [ストレスチェック]({{URL_2}})
    - 各自のメールアドレス宛に案内が届きます
    - 実施期間：7/1(水)～7/31(金)
- [ウイルス対策ソフトの更新について]({{URL_3}})
    - 【要対応】7/10(金)までに、各自のPCでウイルス対策ソフトを最新版に更新してください
        - タスクトレイのウイルス対策ソフトのアイコンを右クリックし、「更新の確認」を選択します
        - 更新が完了したら、PCを再起動します
        - 「バージョン情報」画面で、バージョンが 12.3 以上になっていることを確認します
- [VPNクライアントの更新について]({{URL_4}})
    - 【要対応】7/17(金)までに、VPNクライアントの更新が必要です
- [親睦旅行について]({{URL_5}})
    - 実施期間：9/1(火)～11/30(月)
    - 予算：￥20,000/人（＋交通費：￥3,000）
    - 実施までの流れ
```
"""

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
