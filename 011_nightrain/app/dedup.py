"""同じ内容の投稿を二重にリマインドしないための処理。

元の投稿の投稿者が、同じ依頼・お知らせを何度も投稿(再掲・催促・返信など)した場合に、そのたびにリマインドしないよう、
リマインド対象の投稿をAIで要約するときに「最近リマインドした内容の一覧」を渡し、同じ内容かどうかも判定させる
(app/azure_ai_service.py の same_as)。同じ内容と判定された投稿はリマインドしない。

- 最近リマインドした内容: リマインドの投稿先チャンネル(REMIND_CHANNEL)にある、このサービス自身のリマインド投稿
  (スレッドへの返信は除く)を読み取り、テンプレートの文面から種類・表題・作業・期日を取り出す
  - 期日つき: 期日を過ぎていないもの
  - 期日なし: リマインドしてから DEDUP_NO_DEADLINE_DAYS 日(既定14日)以内のもの
- 同じ依頼で期日だけが変わった場合は、1回目のリマインドのスレッドに「期日が変更されました」と返信し、
  再リマインドの予定も新しい期日で組み直す(変更後の期日は state_store の "deadline_changes" に保存し、
  以後の判定ではそちらを使う)
- 同じ依頼・お知らせに、前回のリマインドに無い新しい注意事項・指示(提出先・必要書類など)が補足された場合は、
  1回目のリマインドのスレッドに「補足の連絡が来ております。」と補足の内容を返信する(AIの supplement)。
  返信した補足は、以後の判定で前回のリマインドの注意点として扱う(同じ補足を繰り返し返信しないため)
- お知らせの状況が変わった続報(障害の発生 → 復旧、工事の予定 → 中止など)で、元のお知らせが明確に分かる場合は、
  元のお知らせのリマインドへのスレッド返信としてリマインドを投稿する(AIの follow_up_of)
- AIが「同じ」と言い切れない場合や、一覧の取得・判定に失敗した場合は、これまでどおりリマインドする(取りこぼし防止を優先)

動作確認用に REMIND_DM_USERNAME を設定している場合も、一覧は REMIND_CHANNEL から作る。
このとき「期日が変更されました」の返信は、REMIND_DM_USERNAME とのDMに(確認用の親投稿を作ってそのスレッドに)投稿する。
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone

from app import followup
from app import mattermost_service as mm
from app import state_store

logger = logging.getLogger(__name__)

# 日付の判定に使うタイムゾーン(Azure Functions上はUTCで動くため、固定オフセットのJSTを使う)
JST = timezone(timedelta(hours=9), "JST")

# このサービスが投稿したメッセージに付ける目印(watcher.NIGHTRAIN_PROP_KEY と同じ値)
NIGHTRAIN_PROP_KEY = "from_nightrain"

# 変更後の期日を保存するキー
DEADLINE_CHANGES_KEY = "deadline_changes"

# リマインドした投稿の要点(AIの key_points)を保存するキー
# (リマインドの文面には要点を載せないため、同じ内容かどうかの判定用に別に保存しておく)
KEY_POINTS_KEY = "reminder_key_points"

# リマインド投稿の文面(テンプレート)から項目を読み取るためのパターン
_REQUEST_LINE = re.compile(r"^(?P<task>.+)の依頼が来ております。$")
_NOTICE_LINE = re.compile(r"^(?P<task>.+)のお知らせが来ております。$")
_DEADLINE_LINE = re.compile(r"^\*\*期日：(?P<month>\d{1,2})/(?P<day>\d{1,2})\(.\)(?: (?P<time>\d{2}:\d{2}))?\*\*$")

# リマインドの文面の定型の行(注意点の行と区別するため)
_STAMP_LINE_PREFIX = "作業完了しましたら、"

# 補足の返信の目印になる一文(この次の行が補足の内容)
SUPPLEMENT_LINE = "補足の連絡が来ております。"


def parse_reminder_post(message: str, reminded_on: date) -> dict | None:
    """
    このサービスのリマインド投稿の文面から、種類・表題・作業・注意点・期日を読み取る

    Args
    -----------------
    - message: str,       リマインド投稿の本文
    - reminded_on: date,  リマインドを投稿した日(期日の年を補うために使う)

    Returns
    -----------------
    - reminder: dict | None,  {"kind", "title", "task", "notes", "deadline"("YYYY-MM-DD"/None), "deadline_time"}。
                              テンプレートの形でない投稿(再リマインドなど)は None

    """
    kind = title = task = deadline = deadline_time = None
    notes = ""
    lines = [line.strip() for line in message.splitlines()]

    # 1行ずつ、見出し・依頼/お知らせの一文・注意点・期日の行を探す
    for i, line in enumerate(lines):
        if line.startswith("#### ") and title is None:
            title = line[5:].strip()
        elif (m := _REQUEST_LINE.match(line)) and kind is None:
            kind, task = "request", m.group("task")
            # 依頼の一文の次の行が、スタンプの案内でも空行でもなければ注意点
            following = lines[i + 1] if i + 1 < len(lines) else ""
            if following and not following.startswith(_STAMP_LINE_PREFIX):
                notes = following
        elif (m := _NOTICE_LINE.match(line)) and kind is None:
            kind, task = "notice", m.group("task")
        elif m := _DEADLINE_LINE.match(line):
            deadline = _infer_deadline_year(int(m.group("month")), int(m.group("day")), reminded_on)
            deadline_time = m.group("time")

    if not title or not kind:
        return None
    return {
        "kind": kind,
        "title": title,
        "task": task,
        "notes": notes,
        "deadline": deadline.isoformat() if deadline else None,
        "deadline_time": deadline_time,
    }


def parse_supplement_reply(message: str) -> str | None:
    """
    このサービスの補足の返信から、補足の内容を読み取る

    Args
    -----------------
    - message: str,  返信の本文

    Returns
    -----------------
    - supplement: str | None,  補足の内容。補足の返信でなければ None

    """
    lines = [line.strip() for line in message.splitlines()]
    if SUPPLEMENT_LINE in lines:
        i = lines.index(SUPPLEMENT_LINE)
        return lines[i + 1] if i + 1 < len(lines) and lines[i + 1] else None
    return None


def _infer_deadline_year(month: int, day: int, reminded_on: date) -> date | None:
    """
    年の無い期日(月/日)に、リマインドした日をもとに年を補う
    (リマインドに表示する期日は元の投稿日以降のため、リマインドした日より大きく前になる場合は翌年とみなす)

    Args
    -----------------
    - month: int,         期日の月
    - day: int,           期日の日
    - reminded_on: date,  リマインドを投稿した日

    Returns
    -----------------
    - deadline: date | None,  年を補った期日(存在しない日付なら None)

    """
    try:
        deadline = date(reminded_on.year, month, day)
        # 元の投稿が数日前(夜間・休日の投稿など)の場合を考え、7日より前なら翌年とみなす
        if deadline < reminded_on - timedelta(days=7):
            deadline = date(reminded_on.year + 1, month, day)
        return deadline
    except ValueError:
        return None


def load_recent_reminders(channel_id: str, now: datetime, settings: dict) -> list[dict]:
    """
    リマインドの投稿先チャンネルから、二重リマインドの判定に使う「最近リマインドした内容」の一覧を作る

    Args
    -----------------
    - channel_id: str,   リマインドの投稿先チャンネル(REMIND_CHANNEL)のID
    - now: datetime,     現在時刻
    - settings: dict,    config.load_watch_settings() の戻り値

    Returns
    -----------------
    - reminders: list[dict],  [{"ref"("R1"など), "post_id", "thread_root_id", "channel_id", "kind", "title", "task", "notes"(補足を含む),
                               "key_points"(保存した要点。無ければ空文字), "deadline", "deadline_time", "reminded_on"}, ...](古い順)

    """
    today = now.astimezone(JST).date()
    now_ms = int(now.timestamp() * 1000)
    start_ms = now_ms - settings["dedup_lookback_days"] * 24 * 60 * 60 * 1000
    changes = state_store.load_json(DEADLINE_CHANGES_KEY)
    key_points = state_store.load_json(KEY_POINTS_KEY)

    # このサービス自身の投稿だけを使う
    posts = [p for p in mm.get_channel_posts_in_range(channel_id, start_ms, now_ms) if (p.get("props") or {}).get(NIGHTRAIN_PROP_KEY)]

    # 補足の返信の内容を、返信先(スレッドの親)のリマインドごとにまとめる(以後の判定で、伝え済みの補足として扱うため)
    supplements: dict[str, list[str]] = {}
    for post in posts:
        supplement = parse_supplement_reply(post["message"]) if post.get("root_id") else None
        if supplement:
            supplements.setdefault(post["root_id"], []).append(supplement)

    reminders = []
    for post in posts:
        # リマインドの文面として読み取れるものだけを使う
        # (スレッドへの返信のうち、続報のお知らせはテンプレートの形なので含まれ、再リマインド・期日変更・補足の返信は除かれる)
        reminded_on = datetime.fromtimestamp(post["create_at"] / 1000, tz=JST).date()
        reminder = parse_reminder_post(post["message"], reminded_on)
        if reminder is None:
            continue

        # 補足の返信があれば、注意点に加える
        if supplements.get(post["id"]):
            reminder["notes"] = " ".join([reminder["notes"], *supplements[post["id"]]]).strip()

        # リマインドしたときに保存した要点を加える(要点の保存を始める前のリマインドには無い)
        reminder["key_points"] = (key_points.get(post["id"]) or {}).get("key_points", "")

        # 期日が変更されていれば、変更後の期日を使う
        if post["id"] in changes:
            reminder["deadline"] = changes[post["id"]].get("deadline")
            reminder["deadline_time"] = changes[post["id"]].get("deadline_time")

        # 期日つきは期日を過ぎていないもの、期日なしは一定日数以内のものだけを対象にする
        if reminder["deadline"]:
            if date.fromisoformat(reminder["deadline"]) < today:
                continue
        elif reminded_on < today - timedelta(days=settings["dedup_no_deadline_days"]):
            continue

        # スレッドに返信するときの親投稿(続報の返信なら、その返信が属するスレッドの親)も記録する
        reminders.append({
            **reminder,
            "post_id": post["id"],
            "thread_root_id": post.get("root_id") or post["id"],
            "channel_id": channel_id,
            "reminded_on": reminded_on.isoformat(),
        })

    # AIに渡すための番号を振る
    for i, reminder in enumerate(reminders, start=1):
        reminder["ref"] = f"R{i}"
    return reminders


def add_recent_reminder(
    reminders: list[dict],
    post_id: str,
    channel_id: str,
    summary: dict,
    deadline: date | None,
    now: datetime,
    thread_root_id: str | None = None,
) -> None:
    """
    今回の実行で投稿したリマインドを一覧に加える(同じ実行の中で届いた同じ内容の投稿も判定できるようにするため)

    Args
    -----------------
    - reminders: list[dict],      load_recent_reminders() の一覧(この関数で追加する)
    - post_id: str,               投稿したリマインドのID
    - channel_id: str,            リマインドを投稿したチャンネルのID
    - summary: dict,              AIによる要約結果
    - deadline: date | None,      リマインドに表示した期日
    - now: datetime,              現在時刻
    - thread_root_id: str | None, 続報としてスレッドに返信した場合は、そのスレッドの親投稿のID

    Returns
    -----------------
    - None

    """
    reminders.append({
        "ref": f"R{len(reminders) + 1}",
        "post_id": post_id,
        "thread_root_id": thread_root_id or post_id,
        "channel_id": channel_id,
        "kind": summary.get("kind"),
        "title": summary.get("title"),
        "task": summary.get("task"),
        "notes": summary.get("notes") or "",
        "key_points": summary.get("key_points") or "",
        "deadline": deadline.isoformat() if deadline else None,
        "deadline_time": summary.get("deadline_time") if deadline else None,
        "reminded_on": now.astimezone(JST).date().isoformat(),
    })


def save_key_points(post_id: str, key_points: str, now: datetime, settings: dict) -> None:
    """
    リマインドした投稿の要点を保存する(以後の、同じ内容かどうかの判定で一覧に載せるため)。
    リマインドは投稿済みのため、保存に失敗しても例外にはせずログだけ残す(再試行で二重に投稿しないため)

    Args
    -----------------
    - post_id: str,     投稿したリマインド(続報の返信を含む)のID
    - key_points: str,  AIが出力した元の投稿の要点
    - now: datetime,    現在時刻
    - settings: dict,   config.load_watch_settings() の戻り値

    Returns
    -----------------
    - None

    """
    if not post_id or not key_points:
        return
    try:
        # 一覧の取得期間より前にリマインドしたものは、判定に使わないので削除する
        oldest = (now.astimezone(JST).date() - timedelta(days=settings["dedup_lookback_days"])).isoformat()
        data = {k: v for k, v in state_store.load_json(KEY_POINTS_KEY).items() if v.get("reminded_on", "") >= oldest}

        # 今回のリマインドの要点を加えて保存する
        data[post_id] = {"key_points": key_points, "reminded_on": now.astimezone(JST).date().isoformat()}
        state_store.save_json(KEY_POINTS_KEY, data)
    except Exception:
        logger.exception("リマインドの要点の保存に失敗しました(リマインド投稿ID: %s)", post_id)


def find_same_reminder(summary: dict, reminders: list[dict]) -> dict | None:
    """
    AIが「同じ内容」と判定したリマインドを一覧から探す

    Args
    -----------------
    - summary: dict,          AIによる要約結果(same_as を使う)
    - reminders: list[dict],  最近リマインドした内容の一覧

    Returns
    -----------------
    - reminder: dict | None,  同じ内容のリマインド。該当しない(一覧に無い番号を含む)場合は None

    """
    return _find_by_ref(summary.get("same_as"), reminders)


def find_related_notice(summary: dict, reminders: list[dict]) -> dict | None:
    """
    AIが「状況が変わった続報」と判定した、元のお知らせのリマインドを一覧から探す

    Args
    -----------------
    - summary: dict,          AIによる要約結果(kind, follow_up_of を使う)
    - reminders: list[dict],  最近リマインドした内容の一覧

    Returns
    -----------------
    - reminder: dict | None,  元のお知らせのリマインド。今回の投稿がお知らせでない、
                              元がお知らせでない、一覧に無い番号の場合は None(通常どおり新しくリマインドする)

    """
    if summary.get("kind") != "notice":
        return None
    reminder = _find_by_ref(summary.get("follow_up_of"), reminders)
    if reminder is None or reminder.get("kind") != "notice":
        return None
    return reminder


def _find_by_ref(ref: str | None, reminders: list[dict]) -> dict | None:
    """一覧の番号("R1"など)に当たるリマインドを返す(無ければ None)"""
    if not ref:
        return None
    return next((r for r in reminders if r["ref"] == ref), None)


def handle_same_reminder(
    reminder: dict,
    summary: dict,
    new_deadline: date | None,
    url: str,
    now: datetime,
    settings: dict,
) -> bool:
    """
    同じ内容と判定された投稿について、期日の変更や新しい補足があれば、前回のリマインドのスレッドに返信する。
    期日が変わっていれば、再リマインドの予定も組み直す(どちらも無ければ何もしない)

    Args
    -----------------
    - reminder: dict,             同じ内容と判定された、最近のリマインド
    - summary: dict,              今回の投稿のAIによる要約結果(deadline_time, supplement を使う)
    - new_deadline: date | None,  今回の投稿の期日(リマインドに表示できる期日。無ければ None)
    - url: str,                   今回の投稿のURL(補足を返信する場合に添える)
    - now: datetime,              現在時刻
    - settings: dict,             config.load_watch_settings() の戻り値

    Returns
    -----------------
    - replied: bool,  スレッドに返信した場合は True

    """
    # 期日の変更: 依頼で、今回の投稿に期日があり、それが前回のリマインドの期日と違う場合だけ扱う
    # (今回の投稿に期日が書かれていないだけの場合は、変更とはみなさない)
    is_request = reminder.get("kind") == "request" and summary.get("kind") != "notice"
    deadline_changed = bool(is_request and new_deadline and reminder.get("deadline") != new_deadline.isoformat())

    # 補足: 前回のリマインド(と過去の補足)に無い、新しい注意事項・指示がある場合だけ扱う
    supplement = " ".join(str(summary.get("supplement") or "").split())
    if not deadline_changed and not supplement:
        return False

    # スレッドに返信する(動作確認時はDMに投稿する)
    message = render_same_reminder_reply(
        new_deadline.isoformat() if deadline_changed else None, summary.get("deadline_time"),
        reminder.get("deadline"), reminder.get("deadline_time"),
        supplement, url, reminder.get("kind") == "request",
        settings["remind_mention"], settings["followup_emoji"],
    )
    purpose = "期日変更の返信" if deadline_changed else "補足の返信"
    destination, _ = followup.post_thread_reply(
        reminder["channel_id"], reminder.get("thread_root_id") or reminder["post_id"], message, reminder.get("title", ""),
        settings["remind_dm_username"], purpose,
    )
    logger.info("%sを%sに投稿しました(リマインド投稿ID: %s, 期日: %s → %s, 補足: %s)", purpose, destination,
                reminder["post_id"], reminder.get("deadline"), new_deadline if deadline_changed else "変更なし", supplement or "なし")

    # 同じ実行の中で同じ補足を繰り返さないよう、一覧の注意点に加える(次回以降は返信の文面から読み取る)
    if supplement:
        reminder["notes"] = " ".join([reminder.get("notes") or "", supplement]).strip()
    if not deadline_changed:
        return True

    # 変更後の期日を保存する(以後の二重リマインドの判定・再リマインドで使う)
    changes = state_store.load_json(DEADLINE_CHANGES_KEY)
    changes[reminder["post_id"]] = {
        "deadline": new_deadline.isoformat(),
        "deadline_time": summary.get("deadline_time"),
    }
    state_store.save_json(DEADLINE_CHANGES_KEY, _drop_old_changes(changes, now, settings))
    reminder["deadline"] = new_deadline.isoformat()
    reminder["deadline_time"] = summary.get("deadline_time")

    # 再リマインドの予定を新しい期日で組み直す(期日まで日がない場合は予定を取り消す)
    followup_date = followup.register_followup(
        reminder["post_id"], reminder["channel_id"], {**summary, "title": reminder.get("title")},
        new_deadline, now, settings["followup_business_days_before"],
    )
    logger.info("再リマインドの予定を組み直しました(リマインド投稿ID: %s, 再リマインド日: %s)",
                reminder["post_id"], followup_date or "なし")
    return True


def _drop_old_changes(changes: dict, now: datetime, settings: dict) -> dict:
    """期日が一覧の取得期間より前に過ぎた、変更後の期日の記録を削除する"""
    oldest = now.astimezone(JST).date() - timedelta(days=settings["dedup_lookback_days"])
    return {k: v for k, v in changes.items() if v.get("deadline") and date.fromisoformat(v["deadline"]) >= oldest}


def render_same_reminder_reply(
    new_deadline: str | None,
    new_deadline_time: str | None,
    old_deadline: str | None,
    old_deadline_time: str | None,
    supplement: str,
    url: str,
    is_request: bool,
    mention: str,
    emoji_name: str,
) -> str:
    """
    期日の変更・補足を知らせる返信のメッセージを作る

    Args
    -----------------
    - new_deadline: str | None,       変更後の期日("YYYY-MM-DD")。期日の変更が無ければ None
    - new_deadline_time: str | None,  変更後の期日の時刻("HH:MM")
    - old_deadline: str | None,       変更前の期日("YYYY-MM-DD"。前回のリマインドに期日が無かった場合は None)
    - old_deadline_time: str | None,  変更前の期日の時刻
    - supplement: str,                補足の内容(無ければ空文字)
    - url: str,                       今回の投稿のURL(補足がある場合に添える)
    - is_request: bool,               元のリマインドが依頼の場合は True(スタンプの案内を付ける)
    - mention: str,                   先頭に付けるメンション(空なら付けない)
    - emoji_name: str,                完了を表すスタンプ名

    Returns
    -----------------
    - message: str,  投稿するメッセージ(Markdown)

    """
    # 期日の表示は1回目のリマインドと同じ形式にする(循環importを避けるため、ここでimportする)
    from app.watcher import format_deadline

    lines = [mention] if mention else []

    # 期日の変更・補足の一文
    if new_deadline:
        lines.append("期日が変更されました。" if old_deadline else "期日が案内されました。")
    if supplement:
        lines += [SUPPLEMENT_LINE, supplement]
    if is_request or new_deadline:
        lines.append(f"作業完了しましたら、上のリマインド投稿に :{emoji_name}: スタンプを押してください。")

    # 変更後(と変更前)の期日
    if new_deadline:
        lines += ["", f"**期日：{format_deadline(new_deadline, new_deadline_time)}**"]
        if old_deadline:
            lines.append(f"(変更前：{format_deadline(old_deadline, old_deadline_time)})")

    # 補足がある場合は、補足の元になった投稿のURLを添える
    if supplement and url:
        lines += ["", url]
    return "\n".join(lines)
