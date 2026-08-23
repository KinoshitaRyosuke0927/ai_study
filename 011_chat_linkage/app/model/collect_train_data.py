"""Mattermostの指定チャンネル・期間の投稿を取得し、
リマインド判定モデルの学習用ラベル付けCSV(train_data.csvと同じ形式)を作成するスクリプト。

接続情報は .env・settings.ini を参照する(mattermost_service.py と同じ設定)。
出力CSVの pickup_flag 列は空欄で出力するので、Excel等で 0/1 を入力してラベル付けすること。
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path

# このファイルは "app/model/" 配下にあるため、"011_chat_linkage" を
# sys.path に追加してから "app" パッケージを import する
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import mattermost_service as mm  # noqa: E402

# ===== 実行前にここを設定する =====
START_DATE = "2025-01-01"  # 取得開始日 (YYYY-MM-DD)
END_DATE = "2026-08-23"  # 取得終了日 (YYYY-MM-DD、この日を含む)
CHANNEL_DISPLAY_NAMES = ["AIビジネス連絡事項", "AIC 連絡事項", "JBD社員全体のお知らせ", "JBD全体のお知らせ"]  # 取得対象チャンネルの表示名(複数指定可)
OUTPUT_CSV = Path(__file__).resolve().parent / "train_data" / "collected_posts.csv"
# ================================


def date_str_to_epoch_ms(date_str: str, end_of_day: bool = False) -> int:
    """
    "YYYY-MM-DD" 形式の日付文字列を、エポックミリ秒に変換する

    Args
    -----------------
    - date_str: str,       変換対象の日付文字列 ("YYYY-MM-DD")
    - end_of_day: bool,    Trueの場合、その日の最後の瞬間(23:59:59.999)に変換する

    Returns
    -----------------
    - epoch_ms: int,       変換後のエポックミリ秒

    """
    # 日付文字列をdatetimeに変換
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    # 日末指定の場合は、翌日0時の1ミリ秒前(23:59:59.999)にする
    if end_of_day:
        dt = dt + timedelta(days=1) - timedelta(milliseconds=1)
    # エポックミリ秒に変換して返す
    return int(dt.timestamp() * 1000)


def find_channel_id_by_display_name(display_name: str) -> str:
    """
    参加している全チームを横断し、表示名が一致するチャンネルのIDを返す

    Args
    -----------------
    - display_name: str,   検索対象のチャンネル表示名

    Returns
    -----------------
    - channel_id: str,     一致したチャンネルのID(複数チームで一致した場合は最初のもの)

    """
    # 参加している全チーム横断のチャンネル一覧を取得
    channels = mm.list_my_channels()
    # 表示名が一致するチャンネルを抽出
    matches = [c for c in channels if c["name"] == display_name]
    # 一致するチャンネルが1件も見つからなかった場合はエラー
    if not matches:
        available = ", ".join(c["name"] for c in channels)
        raise ValueError(
            f"チャンネル '{display_name}' が見つかりません。参加チャンネル一覧: {available}"
        )
    # 複数のチームで同名チャンネルが見つかった場合は警告を出す
    if len(matches) > 1:
        teams = ", ".join(c["team_name"] for c in matches)
        print(
            f"[警告] 表示名 '{display_name}' に一致するチャンネルが複数のチームで見つかりました "
            f"(チーム: {teams})。最初に見つかったものを使用します。"
        )
    # 最初に見つかったチャンネルのIDを返す
    return matches[0]["id"]


def main() -> None:
    """
    CHANNEL_DISPLAY_NAMES で指定した各チャンネルの、START_DATE〜END_DATE の投稿を取得し、
    ラベル付け用CSV(OUTPUT_CSV)に出力する
    """
    # 取得期間の開始・終了日時をエポックミリ秒に変換
    start_ts = date_str_to_epoch_ms(START_DATE, end_of_day=False)
    end_ts = date_str_to_epoch_ms(END_DATE, end_of_day=True)
    # 開始日が終了日より後の場合はエラー
    if start_ts > end_ts:
        raise ValueError("取得開始日は取得終了日より前にしてください")

    # 入れ物用意
    all_posts = []
    # 指定した全チャンネルについて処理
    for channel_name in CHANNEL_DISPLAY_NAMES:
        # チャンネル表示名からチャンネルIDを取得
        channel_id = find_channel_id_by_display_name(channel_name)
        # 該当チャンネルの指定期間内の投稿を取得
        posts = mm.get_channel_posts_in_range(channel_id, start_ts, end_ts)
        print(f"'{channel_name}': {len(posts)}件の投稿を取得しました。")
        # 取得した投稿を全体のリストに追加
        all_posts.extend(posts)

    # 出力先ディレクトリが存在しない場合は作成
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    # ラベル付け用CSVに書き出す(pickup_flag列は手動でラベル付けするため空欄のまま出力する)
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["pickup_flag", "user", "text"])
        for post in all_posts:
            writer.writerow(["", post["username"], post["message"]])

    print(
        f"合計{len(all_posts)}件の投稿を {OUTPUT_CSV} に出力しました。"
        f"pickup_flag列に 0/1 を入力してラベル付けしてください。"
    )


if __name__ == "__main__":
    main()
