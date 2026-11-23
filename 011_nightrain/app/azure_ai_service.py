"""Azure OpenAI の呼び出し(リマインド投稿に使う要約の作成)。

接続情報(AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_KEY)と、デプロイ名(AZURE_OPENAI_DEPLOYMENT、
省略時は gpt-6-luna)は、Azure Functionsのアプリケーション設定(環境変数)から読み込む。

AIにはリマインド投稿の文面全体を書かせず、元の投稿から「種類(依頼/お知らせ)」「表題」「依頼されている作業」「注意点」「期日」だけを
JSONで抜き出させる。文面の定型部分・期日の曜日・元の投稿のURLは、プログラム側(watcher.py)で組み立てる
(AIに曜日やURLを書かせると誤りが入りやすいため)。

最近リマインドした内容の一覧を渡すと、同じ呼び出しの中で「そのいずれかと同じ依頼・お知らせか」も判定させる
(同じ内容の再掲を二重にリマインドしないため。判定結果の扱いは app/dedup.py を参照)。
判定に使えるよう、リマインドしたときに元の投稿の要点(key_points)も出力させ、一覧に載せる。
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
あなたは、社内チャット(Mattermost)や社内掲示板(GROUPSESSION)に届いた連絡を読み、
チームのチャンネルへリマインドを投稿するサービスの一部として、リマインドに使う情報を抜き出す役割です。

## このサービスの目的と優先順位
1. 各人が対応しなければならない依頼(提出・申請・回答・予約など)や、知っておくべきお知らせを見逃さないよう、短くまとめて知らせる
2. 同じ依頼・お知らせが再掲・催促されるたびに何度もリマインドして、チャンネルが同じ連絡で埋まらないようにする
3. ただし、知らせるべき内容を知らせないこと(取りこぼし)は、同じ内容を2回知らせることより困る。
   判断に迷ったら、取りこぼさない側(新しい内容としてリマインドする側)を選ぶ

## 判断の軸: 投稿の主題
1つの投稿に複数の話題が書かれていることがあります。種類・表題・最近リマインドした内容との関係は、
いずれも投稿の「主題」(投稿者が読み手に一番伝えたいこと。多くは見出しや冒頭に書かれている)で判断してください。
付け足しの一文(例: 停電のお知らせの末尾の「勤務表の提出もお忘れなく」)で判断を変えないでください。

## 出力
以下の項目を持つJSONオブジェクトだけを出力してください(前置きや説明文は付けないでください)。

- "kind": 主題の種類。次のどちらか。
    "request": 読み手の各人が「提出する提出物がある」または「実施する作業がある」と明確に書かれている依頼
               (例: 書類の提出、各種申請、アンケートへの回答、日程調整ツールへの日程登録、受診予約)
    "notice":  それ以外のアナウンス(例: システム障害の発生・復旧、停電・建物工事・メンテナンスの予定、
               避難訓練の案内、イベントや新サービスの紹介、制度の周知)。各人の作業が明確でなければ "notice"
- "title": 主題を表す短い表題(20文字程度まで)。例: "年末調整実施について"、"Microsoft 365障害のお知らせ"
- "task": "request" なら各人が行う作業の名詞句で、「{task}の依頼が来ております。」に当てはめて自然なもの
          (例: "年末調整の実施"、"勤務表の提出")。
          "notice" ならお知らせの件名の名詞句で、「{task}のお知らせが来ております。」に当てはめて自然なもの
          (例: "Microsoft 365の障害発生"、"法定停電の実施")。お知らせを無理に依頼の形にしないでください
- "notes": "request" で、作業に関する注意事項(原本の提出が必要、提出先の指定など)が明記されている場合だけ、
           その注意事項を1文で。作業内容の言い換えは書かない。それ以外は空文字 ""(ほとんどの投稿では空文字になります)
- "deadline": "request" で、作業の期日(締め切り)が明記されている場合だけ "YYYY-MM-DD"。それ以外は null。
              年が無ければ投稿日時から最も自然な年を補う(締め切りは通常、投稿日時以降)。
              期日が複数あれば、読み手全員に関係する最も早いもの。作業の開始日・公開日・イベントの開催日は期日ではありません
- "deadline_time": 期日に時刻が書かれていれば "HH:MM"、無ければ null
- "key_points": 主題について、各人の対応や判断に関わる要点を2文まで(後日、同じ内容の投稿と見比べるために使います)。
                "request" なら対象者・方法・提出先や回答先・必要なもの、"notice" なら対象・日時・影響範囲など。
                URLそのものは書かず「回答フォームのURLあり」のように書いてください
- "relation": 入力に「最近リマインドした内容」の一覧がある場合に、この投稿の主題と一覧との関係を次から1つ。一覧が無ければ "none"。
    "same":      主題が一覧のいずれかと同じ依頼・同じお知らせ。再掲・催促・締め切り間近の案内・期日の変更・
                 同じ依頼への補足や途中経過の報告を含みます(書き方・投稿者・投稿場所が違っても同じ)。
                 再びリマインドすると、読み手には同じ連絡が2回届くことになるものです
    "follow_up": 主題が "notice" で、一覧のいずれかの「お知らせ」と同じ対象(同じシステム・同じ建物・同じ工事など)について、
                 状況が変わったこと(復旧・原因の報告・終了・完了・中止・延期・延長など)を伝える続報。
                 状況が変わっているので "same" ではありません
    "none":      上記以外。次のものは "none" です。
                 - 同じ種類でも対象が違う依頼(例: 11月分と12月分の勤務表の提出、別のアンケート)
                 - 主題が一覧に無い内容で、一覧の項目には付け足しで触れているだけの投稿
                   ("same" にすると、その投稿の主題が誰にも知らされなくなります)
                 - "same"・"follow_up" と言い切れない投稿
- "related_to": "same" または "follow_up" の場合は関係する一覧の番号(例: "R3")。"none" なら null
- "supplement": "same" の場合だけ使います。一覧の該当する項目の「注意点」「要点」のどちらにも無い、
                各人の対応に影響する新しい指示・注意事項(提出先・提出方法・必要書類・原本の要否・対象者・手順の変更など)が
                この投稿に明記されていれば、その内容を2文まで(大事なものから)。
                次のものは補足ではありません: 催促・再掲・期日の繰り返しや変更(期日はプログラムで扱います)、
                URL、途中経過・お礼・呼びかけ、各人の任意の情報。該当が無ければ、また "same" 以外なら空文字 ""

## 注意
- 投稿に書かれていない情報を想像で補わないでください(年の補完を除く)
- 期日の曜日は出力しないでください
"""


def call_summarize_for_reminder(
    post_message: str,
    author_username: str,
    posted_at: datetime,
    recent_reminders: list[dict] | None = None,
) -> dict:
    """
    投稿内容から、リマインド投稿に使う表題・依頼作業・注意点・期日をAzure OpenAIで抜き出す。
    最近リマインドした内容の一覧を渡した場合は、そのいずれかと同じ内容かどうかも判定させる

    Args
    -----------------
    - post_message: str,                    リマインド対象の投稿・記事の内容
    - author_username: str,                 元投稿の投稿者ユーザー名
    - posted_at: datetime,                  元投稿の投稿日時(期日の年を補うために使う)
    - recent_reminders: list[dict] | None,  最近リマインドした内容の一覧
                                            ([{"ref"("R1"など), "kind", "title", "task", "notes", "key_points",
                                              "deadline", "reminded_on"}, ...])

    Returns
    -----------------
    - summary: dict,  {"kind"("request" または "notice"), "title", "task", "notes", "deadline"("YYYY-MM-DD" または None),
                       "deadline_time"("HH:MM" または None), "key_points"(元の投稿の要点),
                       "same_as"(同じ内容の一覧の番号 または None),
                       "supplement"(同じ内容の場合の新しい補足 または ""),
                       "follow_up_of"(続報の元になったお知らせの一覧の番号 または None)}

    """
    # 投稿日時・投稿者・本文をまとめてモデルに渡す
    user_content = (
        f"投稿日時: {posted_at.strftime('%Y-%m-%d %H:%M')}\n"
        f"投稿者: {author_username}\n"
        f"投稿内容:\n{post_message}"
    )

    # 最近リマインドした内容があれば、同じ内容かどうかの判定用に一覧を添える
    if recent_reminders:
        lines = []
        for r in recent_reminders:
            kind = "依頼" if r.get("kind") == "request" else "お知らせ"
            lines.append(
                f"{r['ref']}: 種類={kind} / 表題={r.get('title', '')} / 内容={r.get('task', '')}"
                f" / 注意点={r.get('notes') or 'なし'} / 要点={r.get('key_points') or 'なし'}"
                f" / 期日={r.get('deadline') or 'なし'} / リマインドした日={r.get('reminded_on', '')}"
            )
        user_content += "\n\n最近リマインドした内容:\n" + "\n".join(lines)

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

    # 一覧との関係(同じ内容 / 続報 / 関係なし)と、関係する一覧の番号を取り出す
    relation = str(summary.get("relation") or "none")
    related_to = str(summary["related_to"]) if summary.get("related_to") else None
    return {
        # 種類が読み取れない場合は依頼として扱う
        "kind": "notice" if summary.get("kind") == "notice" else "request",
        "title": str(summary.get("title") or ""),
        "task": str(summary.get("task") or ""),
        "notes": str(summary.get("notes") or ""),
        "deadline": summary.get("deadline") or None,
        "deadline_time": summary.get("deadline_time") or None,
        # 後日、同じ内容の投稿と見比べるための要点(リマインドの文面には使わない)
        "key_points": str(summary.get("key_points") or ""),
        # 同じ内容と判定した一覧の番号(一覧に無い番号は dedup 側で無視する)
        "same_as": related_to if relation == "same" else None,
        # 同じ内容の場合に、前回のリマインドに無い新しい注意事項・指示(無ければ空文字)
        "supplement": str(summary.get("supplement") or "") if relation == "same" and related_to else "",
        # 状況が変わった続報と判定したお知らせの番号(同上)
        "follow_up_of": related_to if relation == "follow_up" else None,
    }
