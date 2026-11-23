"""使い方ページ(app/static/help.html)の画面写真を撮り直すスクリプト。

架空のメンバー・予定を返すモックサーバをこのPCの中で起動し、ヘッドレスの Chrome(無ければ Edge)で
画面を自動操作した状態を撮影して app/static/help/*.png に保存する。

- GROUPSESSION には接続しない(ログイン・予定の取得はすべて架空のデータで置き換える)。
- 本物の config.json・data フォルダは使わない(一時フォルダに架空のラベル・モデルを作る)。
- 実際の予定が写った画面写真は使わないこと(顧客名などが写り込むため)。

使い方(004_schedule_tool フォルダで実行):
    python tools/help_screenshots.py            # 3枚すべて撮り直す
    python tools/help_screenshots.py free       # 指定した画面だけ撮り直す(login / free / status)
    python tools/help_screenshots.py --serve    # モックサーバだけ起動する(http://127.0.0.1:8765/?shot=free などで確認用)
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import date, timedelta
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = TOOL_ROOT / "app" / "static" / "help"
PORT = 8765
WINDOW_SIZE = "1440,860"
SHOTS = ["login", "free", "status"]

# 架空のメンバー・予定名(実在の人・顧客とは関係ない)
MEMBERS = [{"uid": str(i + 1), "name": n} for i, n in enumerate(
    ["佐藤 一郎", "鈴木 花子", "高橋 健", "田中 美咲", "伊藤 翔", "渡辺 由美", "山本 大輔"])]
TIMED = [("定例会議", "Blue"), ("顧客打ち合わせ", "Green"), ("資料作成", "Gray"), ("1on1", "Marine"),
         ("訪問(A社)", "Red"), ("研修", "Wine"), ("レビュー", "Cien")]
ALLDAY = [("在宅勤務", "Marine"), ("出張(大阪)", "Red"), ("午前休", "Gray"), ("休暇", "Gray"), ("提出締切", "Cien")]

# 画面を自動操作するスクリプト(?shot=... のときだけトップページに差し込む)
AUTO_SCRIPT = """
<script>
(async () => {
  const shot = new URLSearchParams(location.search).get("shot");
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const until = async (fn) => { for (let i = 0; i < 200; i++) { if (fn()) return; await wait(50); } };
  await until(() => !$("fetch-btn").disabled);
  if (shot === "login") { openLogin(); $("login-username").value = "yamada"; return; }
  if (shot === "status") document.querySelector('.mode-btn[data-mode="status"]').click();
  const [s, e] = shot === "status" ? ["2026-11-02", "2026-11-27"] : ["2026-12-07", "2026-12-18"];
  $("start-date").value = s; $("end-date").value = e;
  $("start-date").dispatchEvent(new Event("change")); $("end-date").dispatchEvent(new Event("change"));
  $("fetch-btn").click();
  if (shot === "status") {
    await until(() => document.querySelector("#ratio-table tr.rt-row"));
    await wait(300);
    document.querySelector('#ratio-table tr.rt-row[data-date="2026-11-05"]').click();
    return;
  }
  await until(() => document.querySelector(".candidate"));
  await wait(300);
  document.querySelectorAll(".candidate")[2].click();
})();
</script>
"""


def make_schedule(start: date, end: date) -> dict:
    """
    期間の架空の予定を作る(日付・メンバーごとに乱数を固定し、何度呼んでも同じ内容にする)

    Args
    -----------------
    - start: date,  期間の開始日
    - end: date,    期間の終了日

    Returns
    -----------------
    - schedule: dict,  {"days", "members", "events"}(GroupsessionClient.get_schedule と同じ形)

    """
    from app import schedule_parser

    days, events, sid = [], [], 1
    d = start
    while d <= end:
        iso = d.isoformat()
        days.append({"date": iso, "weekday": d.weekday(), "holiday": schedule_parser.is_holiday(iso)})
        if not days[-1]["holiday"]:
            for m in MEMBERS:
                rnd = random.Random(f"{iso}-{m['uid']}")
                # 時刻のない予定(在宅・出張・休みなど)
                if rnd.random() < 0.22:
                    t, c = rnd.choice(ALLDAY)
                    events.append({"sid": str(sid), "uid": m["uid"], "start_time": None, "end_time": None, "title": t,
                                   "detail": "", "color": c, "start_date": iso, "end_date": iso, "all_day": True})
                    sid += 1
                # 時刻のある予定(0〜3件)
                for _ in range(rnd.choice([0, 1, 1, 2, 2, 3])):
                    s = rnd.choice([9, 10, 11, 13, 14, 15, 16]) * 60 + rnd.choice([0, 30])
                    e = min(s + rnd.choice([30, 60, 60, 90, 120]), 18 * 60)
                    t, c = rnd.choice(TIMED)
                    events.append({"sid": str(sid), "uid": m["uid"], "start_time": f"{s // 60:02d}:{s % 60:02d}",
                                   "end_time": f"{e // 60:02d}:{e % 60:02d}", "title": t, "detail": "", "color": c,
                                   "start_date": iso, "end_date": iso, "all_day": False})
                    sid += 1
        d += timedelta(days=1)
    return {"days": days, "members": MEMBERS, "events": events}


class FakeClient:
    """GROUPSESSION の代わり(常にログイン済みで、架空のデータを返す)"""

    logged_in = True

    def login(self, username: str, password: str) -> None:
        """ログイン(何もしない)"""

    def logout(self) -> None:
        """ログアウト(何もしない)"""

    def get_my_groups(self) -> list[dict]:
        """架空のマイグループ"""
        return [{"value": "M1", "name": "サンプルグループ"}]

    def get_group_members(self, group: str) -> list[dict]:
        """架空のメンバー"""
        return MEMBERS

    def get_schedule(self, group: str, start: date, end: date) -> dict:
        """架空の予定"""
        return make_schedule(start, end)


def build_mock_app():
    """
    モックのアプリを作る(設定・データを一時フォルダに差し替え、架空のラベルで学習したモデルを用意する)

    Args
    -----------------
    - なし

    Returns
    -----------------
    - app: FastAPI,  画面写真の撮影用のアプリ

    """
    sys.path.insert(0, str(TOOL_ROOT))

    # 1. 設定・データの保存先を一時フォルダに差し替える(配布版と同じ labeling_enabled: false)
    from app import config

    tmp = Path(tempfile.mkdtemp(prefix="help_shots_"))
    config.CONFIG_FILE = tmp / "config.json"
    config.DATA_DIR = tmp / "data"
    config.CONFIG_FILE.write_text(json.dumps({**config.DEFAULTS, "labeling_enabled": False, "last_group": "M1",
                                              "last_member_ids": [m["uid"] for m in MEMBERS]}), encoding="utf-8")
    from app import status_model, status_store

    status_store.LABELS_FILE = config.DATA_DIR / "labels.json"
    status_model.MODEL_FILE = config.DATA_DIR / "office_model.joblib"
    status_model.DATA_DIR = config.DATA_DIR

    # 2. 架空の予定にルールで付けたラベルからモデルを学習する(配布版と同じく、ラベルのファイルは残さない)
    slots = status_model.build_slots("09:00", "18:00", "12:00", "13:00")
    sample = make_schedule(date(2026, 9, 1), date(2026, 10, 30))
    records = []
    for d in sample["days"]:
        if d["holiday"]:
            continue
        for m in MEMBERS:
            evs = status_model.day_events_of(sample["events"], m["uid"], d["date"])
            records.append({"uid": m["uid"], "name": m["name"], "group": "M1", "date": d["date"],
                            "slots": slots, "labels": status_model.rule_labels(evs, slots)})
    status_store.save_records(records)
    status_model.train(lambda g, s, e: make_schedule(s, e), "M1")
    status_store.LABELS_FILE.unlink()

    # 3. GROUPSESSION の代わりに架空のデータを返すようにし、?shot=... のときは自動操作を差し込む
    from fastapi.responses import HTMLResponse

    from app import main

    main.client = FakeClient()

    @main.app.middleware("http")
    async def inject_auto_script(request, call_next):
        if request.url.path == "/" and "shot" in request.query_params:
            html = (TOOL_ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
            return HTMLResponse(html.replace("</body>", AUTO_SCRIPT + "</body>"))
        return await call_next(request)

    return main.app


def find_browser() -> str:
    """
    撮影に使うブラウザ(Chrome、無ければ Edge)の場所を探す

    Returns
    -----------------
    - path: str,  ブラウザの実行ファイル(見つからなければ RuntimeError)

    """
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    for name in ("chrome", "msedge", "google-chrome"):
        if shutil.which(name):
            return shutil.which(name)
    raise RuntimeError("Chrome / Edge が見つかりません")


def capture(browser: str, shot: str) -> Path:
    """
    1枚撮影する

    Args
    -----------------
    - browser: str,  ブラウザの実行ファイル
    - shot: str,     撮る画面(login / free / status)

    Returns
    -----------------
    - path: Path,  保存した画像

    """
    out = OUT_DIR / f"{shot}.png"
    subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={WINDOW_SIZE}",
                    "--virtual-time-budget=15000", f"--screenshot={out}", f"http://127.0.0.1:{PORT}/?shot={shot}"],
                   check=True, capture_output=True, timeout=120)
    return out


def main() -> None:
    """
    モックサーバを起動して画面写真を撮り、終わったらサーバを止める

    Returns
    -----------------
    - None

    """
    import uvicorn

    args = sys.argv[1:]
    serve_only = "--serve" in args
    shots = [a for a in args if a in SHOTS] or SHOTS

    # 1. モックサーバを起動する(127.0.0.1 のみで待ち受ける)
    print("モックサーバを準備しています(架空のデータでモデルを学習します)…")
    server = uvicorn.Server(uvicorn.Config(build_mock_app(), host="127.0.0.1", port=PORT, log_level="warning"))
    if serve_only:
        print(f"http://127.0.0.1:{PORT}/?shot=free などで確認できます(Ctrl+C で終了)")
        server.run()
        return
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.2)

    # 2. 画面ごとに撮影する
    try:
        browser = find_browser()
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        for shot in shots:
            print(f"撮影しました: {capture(browser, shot)}")
    finally:
        # 3. モックサーバを止める
        server.should_exit = True
        thread.join(timeout=10)


if __name__ == "__main__":
    main()
