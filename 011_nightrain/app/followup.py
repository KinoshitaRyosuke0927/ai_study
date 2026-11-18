"""期日が近い依頼の再リマインド。

このサービスがリマインドした投稿のうち、依頼(:sumi: スタンプで完了を知らせてもらうもの)で期日の指定があるものについて、
期日の数営業日前(既定は3営業日前)に、まだ :sumi: スタンプを押していない人へ再リマインドする。

- 対象者: リマインドの投稿先チャンネルの所属メンバーのうち、リマインド投稿に :sumi: を押していない人
          (Bot・無効化されたアカウントは除く。トークンの持ち主も対象に含める)
- 投稿方法: 1回目のリマインド投稿へのスレッド返信として、対象者をメンションする
          (対象者が一定人数以上の場合は @channel にする。全員が押していれば投稿しない)
- 再リマインド日: 期日の3営業日前。1回目のリマインドの時点で既にその日を過ぎている(当日を含む)場合は、
          1回目の翌営業日にする。ただし翌営業日が期日を過ぎる場合や、期日が1回目の当日の場合は再リマインドしない
- 再リマインドは1つのリマインドにつき1回だけ

動作確認用に FOLLOWUP_DM_USERNAME を設定すると、対象者の判定は実際のチャンネルで行ったうえで、
返信はそのユーザーとのDMに(確認用の親投稿を作ってそのスレッドに)投稿し、メンションもしない。

再リマインドの予定は state_store に次の形式で保存する。
    {
        1回目のリマインド投稿ID: {
            "channel_id": str,          # 1回目のリマインドを投稿したチャンネルのID
            "title": str,               # リマインドの表題
            "deadline": "YYYY-MM-DD",   # 期日
            "deadline_time": str|None,  # 期日の時刻("HH:MM")
            "followup_date": "YYYY-MM-DD",  # 再リマインドする日
            "failures": int,            # 再リマインドに失敗した回数
        },
        ...
    }
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from app import business_calendar
from app import mattermost_service as mm
from app import state_store

logger = logging.getLogger(__name__)

# 日付の判定に使うタイムゾーン(Azure Functions上はUTCで動くため、固定オフセットのJSTを使う)
JST = timezone(timedelta(hours=9), "JST")

# このサービスが投稿したメッセージに付ける目印(watcher.NIGHTRAIN_PROP_KEY と同じ値)
NIGHTRAIN_PROP_KEY = "from_nightrain"


def compute_followup_date(deadline: date, reminded_on: date, business_days_before: int) -> date | None:
    """
    再リマインドする日を決める

    Args
    -----------------
    - deadline: date,               期日
    - reminded_on: date,            1回目のリマインドを投稿した日(JST)
    - business_days_before: int,    期日の何営業日前に再リマインドするか

    Returns
    -----------------
    - followup_date: date | None,  再リマインドする日。再リマインドしない場合は None

    """
    # 期日が1回目のリマインドの当日(またはそれより前)なら、再リマインドしない
    if deadline <= reminded_on:
        return None

    # 原則は期日の N 営業日前。既にその日を過ぎている(当日を含む)場合は、1回目の翌営業日にする
    followup_date = business_calendar.add_business_days(deadline, -business_days_before)
    if followup_date <= reminded_on:
        followup_date = business_calendar.add_business_days(reminded_on, 1)

    # 翌営業日が期日を過ぎてしまう場合は、再リマインドしない
    if followup_date > deadline:
        return None
    return followup_date


def register_followup(
    reminder_post_id: str,
    channel_id: str,
    summary: dict,
    deadline: date,
    reminded_at: datetime,
    business_days_before: int,
) -> date | None:
    """
    1回目のリマインドを投稿したときに、再リマインドの予定を登録する

    Args
    -----------------
    - reminder_post_id: str,      1回目のリマインド投稿のID
    - channel_id: str,            1回目のリマインドを投稿したチャンネルのID
    - summary: dict,              AIによる要約結果({"title", "deadline_time", ...})
    - deadline: date,             期日
    - reminded_at: datetime,      1回目のリマインドを投稿した日時
    - business_days_before: int,  期日の何営業日前に再リマインドするか

    Returns
    -----------------
    - followup_date: date | None,  登録した再リマインド日。再リマインドしない場合は None(登録もしない)

    """
    # 再リマインド日を決める(再リマインドしない場合は登録しない)
    followup_date = compute_followup_date(deadline, reminded_at.astimezone(JST).date(), business_days_before)
    if followup_date is None:
        return None

    # 予定の一覧に追加して保存する
    followups = state_store.load_followups()
    followups[reminder_post_id] = {
        "channel_id": channel_id,
        "title": " ".join(str(summary.get("title") or "").split()).lstrip("#").strip(),
        "deadline": deadline.isoformat(),
        "deadline_time": summary.get("deadline_time"),
        "followup_date": followup_date.isoformat(),
        "failures": 0,
    }
    state_store.save_followups(followups)
    return followup_date


def run_due_followups(now: datetime, settings: dict) -> None:
    """
    再リマインド日を迎えた予定について、再リマインドを行う

    Args
    -----------------
    - now: datetime,   現在時刻
    - settings: dict,  config.load_watch_settings() の戻り値

    Returns
    -----------------
    - None

    """
    today = now.astimezone(JST).date()
    followups = state_store.load_followups()
    if not followups:
        return

    remaining = {}
    for post_id, record in followups.items():
        # 期日を過ぎたもの(障害などで再リマインドできなかったもの)は、予定から外す
        deadline = date.fromisoformat(record["deadline"])
        if deadline < today:
            logger.warning("期日を過ぎたため再リマインドをやめます(リマインド投稿ID: %s)", post_id)
            continue

        # 再リマインド日より前のものは、そのまま残す
        if date.fromisoformat(record["followup_date"]) > today:
            remaining[post_id] = record
            continue

        # 再リマインドを行う(失敗した場合は上限回数まで次回以降に再試行する)
        try:
            send_followup(post_id, record, settings)
        except Exception:
            count = record.get("failures", 0) + 1
            if count >= settings["max_retry_count"]:
                logger.exception("再リマインドに %d 回失敗したため諦めます(リマインド投稿ID: %s)", count, post_id)
            else:
                remaining[post_id] = {**record, "failures": count}
                logger.exception("再リマインドに失敗しました(%d 回目、リマインド投稿ID: %s)", count, post_id)

    # 処理した予定を除いて保存する
    state_store.save_followups(remaining)


def send_followup(reminder_post_id: str, record: dict, settings: dict) -> list[str]:
    """
    1件のリマインドについて、:sumi: を押していない人を調べて再リマインドを投稿する

    Args
    -----------------
    - reminder_post_id: str,  1回目のリマインド投稿のID
    - record: dict,           再リマインドの予定(channel_id, title, deadline, deadline_time を使う)
    - settings: dict,         config.load_watch_settings() の戻り値

    Returns
    -----------------
    - usernames: list[str],  再リマインドの対象者のユーザー名(全員が押していれば空。その場合は投稿しない)

    """
    # スタンプを押していない人を調べる(全員が押していれば何も投稿しない)
    usernames = find_unreacted_usernames(record["channel_id"], reminder_post_id, settings["followup_emoji"])
    if not usernames:
        logger.info("全員が :%s: を押しているため、再リマインドしません(リマインド投稿ID: %s)", settings["followup_emoji"], reminder_post_id)
        return []

    dm_username = settings["followup_dm_username"]
    message = render_followup_message(
        usernames,
        record.get("deadline"),
        record.get("deadline_time"),
        settings["followup_emoji"],
        settings["followup_channel_mention_min"],
        test_mode=bool(dm_username),
    )

    # 動作確認用: DMに確認用の親投稿を作り、そのスレッドに返信する(本番チャンネルには投稿しない)
    if dm_username:
        dm_channel_id = mm.get_direct_channel_id_by_username(dm_username)
        permalink = mm.build_channel_post_permalink(record["channel_id"], reminder_post_id)
        root_message = "\n".join([
            "【再リマインドの動作確認】本番では、次のリマインド投稿へのスレッド返信として投稿されます。",
            f"#### {record.get('title', '')}",
            permalink,
        ])
        root_id = mm.post_message(dm_channel_id, root_message, props={NIGHTRAIN_PROP_KEY: True})
        mm.post_message(dm_channel_id, message, props={NIGHTRAIN_PROP_KEY: True}, root_id=root_id)
        logger.info("再リマインドをDM:%sに投稿しました(リマインド投稿ID: %s, 対象 %d 名)", dm_username, reminder_post_id, len(usernames))
        return usernames

    # 本番: 1回目のリマインド投稿へのスレッド返信として投稿する
    mm.post_message(record["channel_id"], message, props={NIGHTRAIN_PROP_KEY: True}, root_id=reminder_post_id)
    logger.info("再リマインドを投稿しました(リマインド投稿ID: %s, 対象 %d 名)", reminder_post_id, len(usernames))
    return usernames


def find_unreacted_usernames(channel_id: str, post_id: str, emoji_name: str) -> list[str]:
    """
    チャンネルの所属メンバーのうち、投稿に指定のスタンプを押していない人のユーザー名を返す

    Args
    -----------------
    - channel_id: str,  リマインドを投稿したチャンネルのID
    - post_id: str,     リマインド投稿のID
    - emoji_name: str,  完了を表すスタンプ名(例: "sumi")

    Returns
    -----------------
    - usernames: list[str],  スタンプを押していない人のユーザー名(名前順)

    """
    # スタンプを押した人と、チャンネルの所属メンバーを取得する
    # (トークンの持ち主もチャンネルのメンバーとして依頼に対応するため、対象から除かない)
    reacted_ids = mm.get_reaction_user_ids(post_id, emoji_name)
    member_ids = mm.get_channel_member_ids(channel_id)

    # 押していない人のうち、Bot・無効化されたアカウントを除く
    target_ids = [uid for uid in member_ids if uid not in reacted_ids]
    users = mm.get_users_by_ids(target_ids) if target_ids else []
    usernames = [u["username"] for u in users if not u.get("is_bot") and not u.get("delete_at")]
    return sorted(usernames)


def render_followup_message(
    usernames: list[str],
    deadline: str | None,
    deadline_time: str | None,
    emoji_name: str,
    channel_mention_min: int,
    test_mode: bool = False,
) -> str:
    """
    再リマインドのメッセージを作る

    Args
    -----------------
    - usernames: list[str],     再リマインドの対象者のユーザー名
    - deadline: str | None,     期日("YYYY-MM-DD")
    - deadline_time: str | None,  期日の時刻("HH:MM")
    - emoji_name: str,          完了を表すスタンプ名
    - channel_mention_min: int, 対象者がこの人数以上なら、個別のメンションではなく @channel にする
    - test_mode: bool,          True の場合、誰にも通知が飛ばないようメンションを `` で囲み、対象者も列挙する

    Returns
    -----------------
    - message: str,  投稿するメッセージ(Markdown)

    """
    # 期日の表示は1回目のリマインドと同じ形式にする(循環importを避けるため、ここでimportする)
    from app.watcher import format_deadline

    # 対象者が一定人数以上なら @channel、それ未満なら個別にメンションする
    use_channel = len(usernames) >= channel_mention_min
    mentions = ["@channel"] if use_channel else [f"@{name}" for name in usernames]

    # 動作確認時は、メンションを `` で囲んで通知が飛ばないようにし、対象者の一覧も添える
    if test_mode:
        mention_line = " ".join(f"`{m}`" for m in mentions) + "(動作確認のためメンションしていません)"
        lines = [mention_line, f"対象者 {len(usernames)} 名: " + ", ".join(usernames), ""]
    else:
        lines = [" ".join(mentions)]

    lines.append("リマインドした依頼の期日が近づいております。")
    lines.append(f"作業完了しましたら、上のリマインド投稿に :{emoji_name}: スタンプを押してください。")
    deadline_text = format_deadline(deadline, deadline_time)
    if deadline_text:
        lines += ["", f"**期日：{deadline_text}**"]
    return "\n".join(lines)
