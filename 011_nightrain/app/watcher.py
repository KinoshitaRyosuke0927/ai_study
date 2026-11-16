"""チャット内容自動リマインドサービスの本体(1回分の監視処理)。

Azure Functionsのタイマートリガー(function_app.py)から一定間隔で呼び出され、以下を行う。

1. アプリケーション設定で指定したMattermostチャンネル・GROUPSESSIONフォーラムの新着投稿を取得する
   (前回確認した時刻から、取りこぼし防止の重なり幅だけさかのぼって取得する)
2. 学習済みモデル(011_agenda_tool と同じモデル)で各投稿のリマインド必要度をスコアリングし、
   しきい値以上のものをリマインド対象とする
3. リマインド対象1件ごとに、Azure OpenAIで投稿内容を要約(表題・依頼作業・注意点・期日)し、
   定型の文面に当てはめて指定のMattermostチャンネルへ投稿する(1つの投稿につき1回だけ)
4. どこまで確認したか・どの投稿を通知済みかを state_store に保存する
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

from app import business_calendar
from app import config
from app import groupsession_service as gs
from app import mattermost_service as mm
from app import state_store
from app.azure_ai_service import call_summarize_for_reminder
from app.model.predict import predict_reminder_scores

logger = logging.getLogger(__name__)

# 投稿の日時表示に使うタイムゾーン(Azure Functions上はUTCで動くため、固定オフセットのJSTを使う)
JST = timezone(timedelta(hours=9), "JST")

# このサービスが投稿したメッセージに付ける目印(投稿のprops)。
# 監視対象チャンネルとリマインド投稿先が同じ場合に、自分の投稿を再びリマインド対象にしないために使う
NIGHTRAIN_PROP_KEY = "from_nightrain"

# 期日の曜日表記
WEEKDAYS_JA = "月火水木金土日"

# 投稿内容を要約する関数の型(投稿本文, 投稿者名, 投稿日時) -> 要約
# 要約は {"kind"("request"/"notice"), "title", "task", "notes", "deadline"("YYYY-MM-DD"/None), "deadline_time"("HH:MM"/None)}
ReminderSummarizer = Callable[[str, str, datetime], dict]


def poll_once(
    now: datetime | None = None,
    summarize: ReminderSummarizer | None = None,
    ignore_business_hours: bool = False,
) -> None:
    """
    1回分の監視処理を行う

    Args
    -----------------
    - now: datetime | None,                   現在時刻(テスト用に指定可能。省略時は実行時刻)
    - summarize: ReminderSummarizer | None,   投稿内容の要約関数
                                              (動作確認用に差し替え可能。省略時はAzure OpenAIで要約)
    - ignore_business_hours: bool,            True の場合、営業日・営業時間の判定をせずに実行する(ローカル確認用)

    Returns
    -----------------
    - None

    """
    now = now or datetime.now(timezone.utc)
    summarize = summarize or call_summarize_for_reminder

    # 営業時間外(土日・祝日・会社独自の休日・営業時間外)は何もしない。
    # 確認位置を進めないため、この間の投稿は次の営業日の最初の実行でまとめてリマインドされる
    if not ignore_business_hours:
        reason = business_calendar.get_non_business_reason(now)
        if reason:
            logger.info("営業時間外のため処理をスキップします: %s", reason)
            return

    settings = config.load_watch_settings()

    # リマインドの投稿先を解決する(解決できない場合は、状態を進めずに今回の処理を中止する)
    channels = mm.list_my_channels()
    destination_id, destination_label = _resolve_destination(settings, channels)
    logger.info("リマインド投稿先: %s", destination_label)

    # 監視対象(Mattermostチャンネル・GROUPSESSIONフォーラム)の一覧を組み立てる
    sources = _build_sources(settings, channels)
    if not sources:
        logger.warning("監視対象が設定されていません(WATCH_MATTERMOST_CHANNELS / WATCH_GROUPSESSION_FORUM_SIDS)")
        return

    # 監視対象ごとに処理する(1つの監視対象で失敗しても、他の監視対象の処理は続ける)
    for source in sources:
        try:
            _process_source(source, settings, now, destination_id, summarize)
        except Exception:
            logger.exception("監視対象 %s の処理に失敗しました", source["label"])


def _find_channel_id(name: str, channels: list[dict]) -> str:
    """
    チャンネルの表示名(または「チーム表示名/チャンネル表示名」)からチャンネルIDを返す

    Args
    -----------------
    - name: str,              アプリケーション設定に書かれたチャンネル名
    - channels: list[dict],   mm.list_my_channels() の戻り値

    Returns
    -----------------
    - channel_id: str,  チャンネルID(見つからない・複数該当する場合はエラー)

    """
    # まず表示名の完全一致で探す
    matched = [c for c in channels if c["name"] == name]
    # 見つからなければ「チーム表示名/チャンネル表示名」の形式として探す
    if not matched:
        matched = [c for c in channels if f"{c['team_name']}/{c['name']}" == name]

    if not matched:
        raise ValueError(f"チャンネル「{name}」が見つかりません(トークンの持ち主が参加しているチャンネルか確認してください)")
    if len(matched) > 1:
        raise ValueError(
            f"チャンネル「{name}」が複数のチームに存在します。「チーム表示名/チャンネル表示名」の形式で指定してください"
        )
    return matched[0]["id"]


def _resolve_destination(settings: dict, channels: list[dict]) -> tuple[str, str]:
    """
    リマインドの投稿先チャンネルIDを解決する
    (REMIND_DM_USERNAME が設定されている場合は、動作確認用にそのユーザーとのDMを投稿先にする)

    Args
    -----------------
    - settings: dict,         config.load_watch_settings() の戻り値
    - channels: list[dict],   mm.list_my_channels() の戻り値

    Returns
    -----------------
    - destination: tuple[str, str],  (投稿先チャンネルID, ログ表示用の名前)

    """
    # 動作確認用のDM差し替えが設定されていれば、そちらを優先する
    dm_username = settings["remind_dm_username"]
    if dm_username:
        return mm.get_direct_channel_id_by_username(dm_username), f"DM:{dm_username}"

    remind_channel = settings["remind_channel"]
    if not remind_channel:
        raise RuntimeError("アプリケーション設定 REMIND_CHANNEL が設定されていません")
    return _find_channel_id(remind_channel, channels), remind_channel


def _build_sources(settings: dict, channels: list[dict]) -> list[dict]:
    """
    監視対象の一覧を組み立てる

    Args
    -----------------
    - settings: dict,         config.load_watch_settings() の戻り値
    - channels: list[dict],   mm.list_my_channels() の戻り値

    Returns
    -----------------
    - sources: list[dict],  [{"key", "label", "is_web", "fetch"(開始ms, 終了ms) -> 投稿一覧}, ...]

    """
    sources = []

    # Mattermostチャンネル(名前を解決できないものは警告を出してスキップする)
    for name in settings["watch_channels"]:
        try:
            channel_id = _find_channel_id(name, channels)
        except ValueError as exc:
            logger.warning("WATCH_MATTERMOST_CHANNELS: %s", exc)
            continue
        sources.append({
            "key": f"mattermost-{channel_id}",
            "label": f"Mattermost「{name}」",
            "is_web": False,
            # ループ変数を既定引数で束縛し、各チャンネルIDを固定する
            "fetch": lambda start, end, cid=channel_id: mm.get_channel_posts_in_range(cid, start, end),
        })

    # GROUPSESSIONフォーラム
    for forum_sid in settings["watch_forum_sids"]:
        sources.append({
            "key": f"groupsession-{forum_sid}",
            "label": f"GROUPSESSION(フォーラムID: {forum_sid})",
            "is_web": True,
            "fetch": lambda start, end, sid=forum_sid: gs.get_recent_announcements(sid, start, end),
        })

    return sources


def _process_source(
    source: dict,
    settings: dict,
    now: datetime,
    destination_id: str,
    summarize: ReminderSummarizer,
) -> None:
    """
    1つの監視対象について、新着投稿の取得・スコアリング・リマインド投稿・状態保存を行う

    Args
    -----------------
    - source: dict,                       _build_sources() の要素
    - settings: dict,                     config.load_watch_settings() の戻り値
    - now: datetime,                      現在時刻
    - destination_id: str,                リマインドの投稿先チャンネルID
    - summarize: ReminderSummarizer,      投稿内容の要約関数

    Returns
    -----------------
    - None

    """
    state = state_store.load_state(source["key"])
    notified: dict = state["notified"]
    failures: dict = state["failures"]

    # 取得期間を決める(初回は直近の重なり幅分のみ。過去の投稿をまとめてリマインドしないため)
    now_ms = int(now.timestamp() * 1000)
    overlap_ms = settings["overlap_minutes"] * 60 * 1000
    base_ms = state["cursor"] or now_ms
    start_ms = base_ms - overlap_ms

    # 新着投稿を取得する(失敗した場合は状態を進めずに例外を上げ、次回同じ期間を取り直す)
    items = source["fetch"](start_ms, now_ms)

    # このサービス自身の投稿と、通知済みの投稿は除く
    items = [i for i in items if not (i.get("props") or {}).get(NIGHTRAIN_PROP_KEY)]
    new_items = [i for i in items if i["id"] not in notified]
    logger.info("%s: 取得 %d 件 / 未通知 %d 件", source["label"], len(items), len(new_items))

    # 学習済みモデルでスコアリングし、しきい値以上のものだけをリマインド対象にする
    scores = predict_reminder_scores([i["message"] for i in new_items])
    targets = [(i, s) for i, s in zip(new_items, scores) if s >= settings["threshold"]]

    # リマインド対象1件ずつ、要約してリマインドを投稿する
    retry_floor_ms = None
    for item, score in targets:
        try:
            message = build_remind_message(item, summarize, settings["remind_mention"])
            mm.post_message(destination_id, message, props={NIGHTRAIN_PROP_KEY: True})
            notified[item["id"]] = item["create_at"]
            failures.pop(item["id"], None)
            logger.info("%s: リマインドを投稿しました(投稿ID: %s, スコア: %.2f)", source["label"], item["id"], score)
        except Exception:
            # 失敗した投稿は、上限回数まで次回以降に再試行する(上限に達したら通知済み扱いにしてあきらめる)
            count = failures.get(item["id"], 0) + 1
            if count >= settings["max_retry_count"]:
                notified[item["id"]] = item["create_at"]
                failures.pop(item["id"], None)
                logger.exception("%s: リマインドの作成・投稿に %d 回失敗したため諦めます(投稿ID: %s)", source["label"], count, item["id"])
            else:
                failures[item["id"]] = count
                retry_floor_ms = item["create_at"] if retry_floor_ms is None else min(retry_floor_ms, item["create_at"])
                logger.exception("%s: リマインドの作成・投稿に失敗しました(%d 回目、投稿ID: %s)", source["label"], count, item["id"])

    # 次回の取得開始の基準を決める(再試行する投稿があれば、その投稿が取得期間に含まれるようにする)
    cursor = now_ms if retry_floor_ms is None else min(now_ms, retry_floor_ms)

    # 古い通知済み記録と、今回の取得結果に含まれない失敗記録を削除して状態を保存する
    retention_ms = settings["notified_retention_days"] * 24 * 60 * 60 * 1000
    seen_ids = {i["id"] for i in items}
    state_store.save_state(source["key"], {
        "cursor": cursor,
        "notified": {k: v for k, v in notified.items() if v >= now_ms - retention_ms},
        "failures": {k: v for k, v in failures.items() if k in seen_ids},
    })


def build_remind_message(item: dict, summarize: ReminderSummarizer, mention: str = "@channel") -> str:
    """
    リマインド対象の投稿をAIで要約し、リマインド投稿の文面を組み立てる

    Args
    -----------------
    - item: dict,                     リマインド対象の投稿・記事
    - summarize: ReminderSummarizer,  投稿内容の要約関数
    - mention: str,                   先頭に付けるメンション(空なら付けない)

    Returns
    -----------------
    - message: str,  投稿するメッセージ(Markdown)

    """
    # 投稿日時(JST)を添えて、表題・依頼作業・注意点・期日をAIで抜き出す
    posted_at = datetime.fromtimestamp(item["create_at"] / 1000, tz=JST)
    summary = summarize(item["message"], item["username"], posted_at)
    return render_remind_message(summary, item["url"], posted_at, mention)


def render_remind_message(summary: dict, url: str, posted_at: datetime, mention: str = "@channel") -> str:
    """
    要約結果を定型の文面に当てはめて、リマインド投稿のメッセージを作る

    依頼(kind が "request")の場合のみ、注意点・:sumi: スタンプの依頼・期日を記載する。
    お知らせ(kind が "notice")の場合は、表題・お知らせの一文・元の投稿のURLだけにする。

    Args
    -----------------
    - summary: dict,      要約結果({"kind", "title", "task", "notes", "deadline", "deadline_time"})
    - url: str,           元の投稿のURL
    - posted_at: datetime,  元の投稿の投稿日時(これより前の期日は表示しない)
    - mention: str,       先頭に付けるメンション(空なら付けない)

    Returns
    -----------------
    - message: str,  投稿するメッセージ(Markdown)

    """
    # AIの出力に改行や見出し記号が混ざっても表示が崩れないよう整える
    is_request = summary.get("kind") != "notice"
    title = _one_line(summary.get("title", "")).lstrip("#").strip()
    task = _one_line(summary.get("task", ""))
    notes = _one_line(summary.get("notes", ""))

    # 期日は、投稿日より前の日付であれば表示しない(公開日・発生日などを期日と取り違えた場合の対策)
    deadline = ""
    deadline_date = _parse_date(summary.get("deadline") or "")
    if deadline_date and deadline_date >= posted_at.date():
        deadline = format_deadline(summary.get("deadline"), summary.get("deadline_time"))

    lines = []
    if mention:
        lines.append(mention)
    lines.append(f"#### {title}")

    # お知らせの場合: スタンプの依頼・注意点・日付は付けない
    if not is_request:
        lines.append(f"{task}のお知らせが来ております。")
        lines += ["", url]
        return "\n".join(lines)

    # 依頼の場合: テンプレートに当てはめる(注意点・期日が無い場合はその行を省く)
    lines.append(f"{task}の依頼が来ております。")
    if notes:
        lines.append(notes)
    lines.append("作業完了しましたら、 :sumi: スタンプを押してください。")
    if deadline:
        lines += ["", f"**期日：{deadline}**"]
    lines += ["", url]
    return "\n".join(lines)


def _parse_date(text: str):
    """"YYYY-MM-DD" を date に変換する(読み取れない場合は None)"""
    try:
        return datetime.strptime(str(text).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def format_deadline(deadline: str | None, deadline_time: str | None = None) -> str:
    """
    期日("YYYY-MM-DD")を「11/20(金)」の形式にする(曜日はAIに書かせず、ここで計算する)

    Args
    -----------------
    - deadline: str | None,       期日("YYYY-MM-DD")。None・不正な形式の場合は空文字を返す
    - deadline_time: str | None,  期日の時刻("HH:MM")。指定があれば日付の後ろに付ける

    Returns
    -----------------
    - text: str,  表示用の期日(例: "11/20(金)"、"11/20(金) 17:00")

    """
    # 日付として読み取れない場合は、期日なしとして扱う
    if not deadline:
        return ""
    try:
        day = datetime.strptime(str(deadline).strip(), "%Y-%m-%d")
    except ValueError:
        logger.warning("AIが出力した期日を日付として読み取れませんでした: %s", deadline)
        return ""

    text = f"{day.month}/{day.day}({WEEKDAYS_JA[day.weekday()]})"

    # 時刻は "HH:MM" として読み取れる場合だけ付ける
    if deadline_time:
        try:
            text += " " + datetime.strptime(str(deadline_time).strip(), "%H:%M").strftime("%H:%M")
        except ValueError:
            logger.warning("AIが出力した期日の時刻を読み取れませんでした: %s", deadline_time)
    return text


def _one_line(text: str) -> str:
    """改行を空白に置き換えて1行にする"""
    return " ".join(str(text or "").split())
