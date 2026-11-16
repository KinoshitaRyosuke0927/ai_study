"""Azure OpenAI の呼び出し(リマインド投稿に使う要約の作成)。

接続情報(AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_KEY)と、デプロイ名(AZURE_OPENAI_DEPLOYMENT、
省略時は gpt-5.4-mini)は、Azure Functionsのアプリケーション設定(環境変数)から読み込む。

AIにはリマインド投稿の文面全体を書かせず、元の投稿から「種類(依頼/お知らせ)」「表題」「依頼されている作業」「注意点」「期日」だけを
JSONで抜き出させる。文面の定型部分・期日の曜日・元の投稿のURLは、プログラム側(watcher.py)で組み立てる
(AIに曜日やURLを書かせると誤りが入りやすいため)。
"""

from __future__ import annotations

import json
from datetime import datetime

from openai import OpenAI

from app import config

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """
    Azure OpenAI クライアントを返す(初回呼び出し時に作成し、以降は使い回す)

    Args
    -----------------
    - なし

    Returns
    -----------------
    - client: OpenAI,  Azure OpenAI(v1 API)クライアント

    """
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=config.get_required("AZURE_OPENAI_ENDPOINT"),
            api_key=config.get_required("AZURE_OPENAI_KEY"),
        )
    return _client


REMINDER_SUMMARY_SYSTEM_PROMPT = """
あなたは社内チャット(Mattermost)や社内掲示板(GROUPSESSION)の投稿から、リマインド投稿に使う情報を抜き出すアシスタントです。
与えられた投稿を読み、以下の項目を持つJSONオブジェクトだけを出力してください(前置きや説明文は付けないでください)。

- "kind": 投稿の種類。次のどちらかの文字列にしてください。
          "request": 投稿内に、読み手の各人が「提出する提出物がある」または「実施する作業がある」と明確に書かれている内容
                     例: 書類の提出、各種申請、アンケートへの回答、日程調整ツールへの日程登録、受診予約
          "notice":  上記に当たらないアナウンス。例: システム障害の発生・復旧、停電・建物工事・メンテナンスの予定、
                     避難訓練の案内、イベントや新サービスの紹介、制度の周知
                     (各人が行う作業が明確に書かれていない場合は、迷ったら "notice" にしてください)
- "title": 投稿内容を表す短い表題(20文字程度まで)。例: "年末調整実施について"、"Microsoft 365障害のお知らせ"
- "task": kind が "request" の場合は、各人が行う作業を表す名詞句。「{task}の依頼が来ております。」という文に
          当てはめて自然になるようにしてください。例: "年末調整の実施"、"懇親会の日程登録"、"勤務表の提出"
          kind が "notice" の場合は、お知らせの件名を表す名詞句。「{task}のお知らせが来ております。」という文に
          当てはめて自然になるようにしてください。例: "Microsoft 365の障害発生"、"法定停電の実施"
          (お知らせを無理に作業の依頼の形にしないでください)
- "notes": kind が "request" で、かつ作業に関する注意事項(原本の提出が必要、提出先の指定など)が投稿内に
           明記されている場合のみ、その注意事項を1文で。作業内容の言い換えや補足説明は書かないでください。
           それ以外(kind が "notice" の場合や、注意事項が明記されていない場合)は必ず空文字 "" にしてください。
           ほとんどの投稿では空文字になるはずです。
- "deadline": kind が "request" で、かつ作業の期日(締め切り)が投稿内に明記されている場合のみ、その期日を "YYYY-MM-DD" 形式で。
              投稿に年が書かれていない場合は、投稿日時をもとに最も自然な年を補ってください(締め切りは通常、投稿日時以降です)。
              期日が複数ある場合は、読み手全員に関係する最も早い期日を選んでください。
              作業の開始日・公開日・イベントの開催日は期日ではありません。
              それ以外(kind が "notice" の場合や、期日が明記されていない場合)は null にしてください。
- "deadline_time": 上記の期日に時刻が書かれている場合は "HH:MM" 形式で(例: "17:00")。書かれていない場合は null にしてください。

注意:
- 投稿に書かれていない情報を想像で補わないでください(年の補完を除く)。
- 期日の曜日は出力しないでください。
"""


def call_summarize_for_reminder(post_message: str, author_username: str, posted_at: datetime) -> dict:
    """
    投稿内容から、リマインド投稿に使う表題・依頼作業・注意点・期日をAzure OpenAIで抜き出す

    Args
    -----------------
    - post_message: str,      リマインド対象の投稿・記事の内容
    - author_username: str,   元投稿の投稿者ユーザー名
    - posted_at: datetime,    元投稿の投稿日時(期日の年を補うために使う)

    Returns
    -----------------
    - summary: dict,  {"kind"("request" または "notice"), "title", "task", "notes", "deadline"("YYYY-MM-DD" または None),
                       "deadline_time"("HH:MM" または None)}

    """
    # 投稿日時・投稿者・本文をまとめてモデルに渡す
    user_content = (
        f"投稿日時: {posted_at.strftime('%Y-%m-%d %H:%M')}\n"
        f"投稿者: {author_username}\n"
        f"投稿内容:\n{post_message}"
    )

    # JSON形式で出力させる
    response = _get_client().chat.completions.create(
        model=config.get_str("AZURE_OPENAI_DEPLOYMENT", config.DEFAULT_AZURE_OPENAI_DEPLOYMENT),
        messages=[
            {"role": "system", "content": REMINDER_SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or ""

    # JSONとして読み取り、必須項目がそろっているか確認する(不正な場合は例外にして再試行の対象にする)
    summary = json.loads(content)
    if not isinstance(summary, dict) or not summary.get("title") or not summary.get("task"):
        raise ValueError(f"AIの出力に title / task がありません: {content}")
    return {
        # 種類が読み取れない場合は依頼として扱う
        "kind": "notice" if summary.get("kind") == "notice" else "request",
        "title": str(summary.get("title") or ""),
        "task": str(summary.get("task") or ""),
        "notes": str(summary.get("notes") or ""),
        "deadline": summary.get("deadline") or None,
        "deadline_time": summary.get("deadline_time") or None,
    }
