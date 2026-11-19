"""Azure OpenAI の呼び出し(リマインド投稿に使う要約の作成)。

接続情報(AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_KEY)と、デプロイ名(AZURE_OPENAI_DEPLOYMENT、
省略時は gpt-5.4-mini)は、Azure Functionsのアプリケーション設定(環境変数)から読み込む。

AIにはリマインド投稿の文面全体を書かせず、元の投稿から「種類(依頼/お知らせ)」「表題」「依頼されている作業」「注意点」「期日」だけを
JSONで抜き出させる。文面の定型部分・期日の曜日・元の投稿のURLは、プログラム側(watcher.py)で組み立てる
(AIに曜日やURLを書かせると誤りが入りやすいため)。

最近リマインドした内容の一覧を渡すと、同じ呼び出しの中で「そのいずれかと同じ依頼・お知らせか」も判定させる
(同じ内容の再掲を二重にリマインドしないため。判定結果の扱いは app/dedup.py を参照)。
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

- "relation": 入力に「最近リマインドした内容」の一覧がある場合に、この投稿と一覧との関係を次の3つから1つ選んでください。
              一覧が無い場合は "none" にしてください。
              "follow_up": この投稿が "notice" で、一覧のいずれかの「お知らせ」と同じ対象(同じシステム・同じ建物・同じ工事など)について、
                           状況が変わったことを伝える続報である場合。
                           例: 障害の発生 → 障害の復旧・原因の報告、工事・メンテナンスの予定 → 中止・延期・延長・終了・完了
                           (復旧・終了・中止・延期などを伝えるお知らせは、元のお知らせと表題が似ていても "same" ではなく "follow_up" です)
              "same":      一覧のいずれかと同じ依頼・同じお知らせであると言い切れる場合。
                           - 同じ提出物・同じ作業についての再掲・催促・補足・締め切り間近の案内(書き方や投稿者・投稿場所が違っても同じ)
                           - 同じ依頼で、期日だけが延長・変更されたもの
                           - 同じお知らせの単なる再掲(状況に変化がないもの)
                           同じ種類でも対象が違う依頼(例: 11月分の勤務表の提出と12月分の勤務表の提出、別のアンケート)は "same" ではありません。
              "none":      上記以外。"follow_up" か "same" か "none" か迷う場合も "none" にしてください。
- "related_to": "relation" が "follow_up" または "same" の場合は、関係する一覧の番号(例: "R3")。"none" の場合は null にしてください。
- "supplement": "relation" が "same" で、かつこの投稿に、一覧の該当するリマインドの内容・注意点に含まれていない
                新しい注意事項・指示(提出先・提出方法・必要書類・原本の要否・対象者・手順の変更など)が明記されている場合だけ、
                その内容を2文までで(注意事項・指示が複数ある場合は、大事なものから順に含めてください)。単なる催促・再掲・期日の繰り返し・期日の変更だけの場合は補足ではないので、必ず空文字 "" にしてください。
                "relation" が "same" 以外の場合も空文字 "" にしてください。

注意:
- 投稿に書かれていない情報を想像で補わないでください(年の補完を除く)。
- 期日の曜日は出力しないでください。
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
                                            ([{"ref"("R1"など), "kind", "title", "task", "notes", "deadline", "reminded_on"}, ...])

    Returns
    -----------------
    - summary: dict,  {"kind"("request" または "notice"), "title", "task", "notes", "deadline"("YYYY-MM-DD" または None),
                       "deadline_time"("HH:MM" または None), "same_as"(同じ内容の一覧の番号 または None),
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
                f" / 注意点={r.get('notes') or 'なし'}"
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
        # 同じ内容と判定した一覧の番号(一覧に無い番号は dedup 側で無視する)
        "same_as": related_to if relation == "same" else None,
        # 同じ内容の場合に、前回のリマインドに無い新しい注意事項・指示(無ければ空文字)
        "supplement": str(summary.get("supplement") or "") if relation == "same" and related_to else "",
        # 状況が変わった続報と判定したお知らせの番号(同上)
        "follow_up_of": related_to if relation == "follow_up" else None,
    }
