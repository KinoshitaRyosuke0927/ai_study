"""過去のアジェンダ(GROWI)から、アジェンダ生成の手本(few-shot)にする
「元の投稿・記事 → アジェンダの項目」の組を集め、agenda_examples.json に出力する。

- GROWIの過去アジェンダ(月ごとのページ)の「全体共有事項」から、見出しにリンクが付いた項目を抜き出す
- リンク先(Mattermostのパーマリンク / GROUPSESSIONのスレッドURL)から元の投稿・記事の本文を取得する
- 取得できた組を、ページ(アジェンダ1回分)ごとにまとめて保存する

GROWI・Mattermost・GROUPSESSIONとも読み取りのみで、書き込みは行わない。

実行方法(011_agenda_tool ディレクトリ直下で):
    python -m app.agenda_examples.collect_agenda_examples
    (GROUPSESSIONのID・パスワードを聞かれる。メモリ上でのみ使い、保存はしない)
"""

from __future__ import annotations

import argparse
import getpass
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app import groupsession_service as gs
from app import growi_service as growi
from app import mattermost_service as mm

# 過去アジェンダの親ページのパス(この下に "年/月" のページがある)
DEFAULT_ROOT_PATH = "/2000_開発者向け/2000_開発者向け/2YYY_組織/AIビジネス研究室/100_AIM"
# 手本にするアジェンダの開始年月(これより前のアジェンダは書き方が異なるため使わない)
EXAMPLES_SINCE = (2025, 4)
# 出力先(agenda_template.txt と同じ階層)
OUTPUT_PATH = Path(__file__).resolve().parents[2] / "agenda_examples.json"

# 月ごとのページのパス(末尾が "/YYYY/MM")
MONTHLY_PAGE_RE = re.compile(r"/(\d{4})/(\d{2})$")
# Markdownリンク・箇条書き
LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")
BULLET_RE = re.compile(r"^( *)[-*] (.*)$")
# Mattermostのパーマリンク(https://chat.../{team}/pl/{post_id})
MM_PERMALINK_RE = re.compile(r"^https?://chat\.[^/]+/[^/]+/pl/([a-z0-9]{26})")
# 旧書式(「全体共有事項」が箇条書き)で、全体共有事項の範囲の終わりとみなす別セクション名
OTHER_SECTIONS = ("役員会", "進捗報告", "豆知識", "その他プロジェクト", "第二部")
# 全角・半角の空白
SPACES = " 　"
# 手本から除く補足行(部会の後に追記された対応状況など、元の投稿・記事からは書けない行)
EXCLUDE_DETAIL_PATTERNS = (
    re.compile(r"対応済"),
    re.compile(r"^未対応"),
)
URL_RE = re.compile(r"https?://[^\s)\]>]+")


def clean_details(details: list[dict], message: str) -> list[dict]:
    """
    手本の補足行から、元の投稿・記事からは書けない行を除く

    - 部会の後に追記された対応状況の行(EXCLUDE_DETAIL_PATTERNS)
    - 元の投稿・記事に含まれないURLを含む行(後から作成されたwikiページへのリンクなど)

    Args
    -----------------
    - details: list[dict],  補足行の一覧([{"text", "children"}])
    - message: str,         元の投稿・記事の本文

    Returns
    -----------------
    - cleaned: list[dict],  除外後の補足行の一覧

    """
    def is_writable(text: str) -> bool:
        # 対応状況の行は除く
        if any(p.search(text) for p in EXCLUDE_DETAIL_PATTERNS):
            return False
        # 本文に無いURLを含む行は除く
        return all(url in message for url in URL_RE.findall(text))

    cleaned = []
    for detail in details:
        if not is_writable(detail["text"]):
            continue
        children = [c for c in detail["children"] if is_writable(c)]
        cleaned.append({"text": detail["text"], "children": children})
    return cleaned


def extract_agenda_items(body: str) -> list[dict]:
    """
    アジェンダ本文の「全体共有事項」から項目を抜き出す。
    新書式(「#### 全体共有事項」の見出し)・旧書式(「- 全体共有事項」の箇条書き)の両方に対応する

    Args
    -----------------
    - body: str,  アジェンダページの本文(Markdown)

    Returns
    -----------------
    - items: list[dict],  項目一覧。各要素は {"heading": 見出し行の文字列,
                           "details": [{"text", "children": [str]}]}

    """
    lines = body.splitlines()

    # 「全体共有事項」の行を探す(無ければ項目なし)
    start = next((i for i, line in enumerate(lines) if "全体共有事項" in line), None)
    if start is None:
        return []

    items: list[dict] = []
    for line in lines[start + 1:]:
        # 見出しが来たら「全体共有事項」の範囲は終わり
        if line.lstrip().startswith("#"):
            break
        m = BULLET_RE.match(line)
        if not m:
            continue
        indent, text = len(m.group(1)), m.group(2).rstrip()
        # 旧書式で別セクションの箇条書きが来たら終わり
        if indent == 0 and text.startswith(OTHER_SECTIONS):
            break

        # 直前の項目よりインデントが深くなければ新しい項目とみなす
        # (旧書式では項目が4、新書式では0。2025/09のように混在していても扱えるようにする)
        if not items or indent <= items[-1]["indent"]:
            items.append({"indent": indent, "heading": text, "details": []})
            continue

        # 項目より1段深い行は補足情報、2段以上深い行は直前の補足情報の詳細とする
        depth = (indent - items[-1]["indent"]) // 4
        details = items[-1]["details"]
        if depth <= 1 or not details:
            details.append({"text": text, "children": []})
        else:
            details[-1]["children"].append(text)

    return [{"heading": it["heading"], "details": it["details"]} for it in items]


def heading_to_output(heading: str) -> dict | None:
    """
    項目の見出し行を、AIの出力形式(title / title_note)とリンクURLに分解する

    Args
    -----------------
    - heading: str,  見出し行(例: "[PC棚卸について](https://...)　期限：11/30(日)")

    Returns
    -----------------
    - parsed: dict | None,  {"title", "title_note", "url"}。リンクが無い見出しは None

    """
    m = LINK_RE.search(heading)
    if not m:
        return None
    # リンクの表示文字列を見出し、リンクの前後の文字列を見出しの後ろの補足(期限など)とする
    rest = (heading[:m.start()] + heading[m.end():]).strip(SPACES)
    return {"title": m.group(1).strip(), "title_note": rest, "url": m.group(2)}


def parse_groupsession_url(url: str) -> tuple[int, int] | None:
    """
    GROUPSESSIONのスレッドURLからフォーラムID・スレッドIDを取り出す

    Args
    -----------------
    - url: str,  スレッドURL(ログイン画面経由で遷移するURL)

    Returns
    -----------------
    - ids: tuple[int, int] | None,  (forum_sid, thread_sid)。GROUPSESSIONのスレッドURLでなければ None

    """
    parsed = urlparse(url)
    if not parsed.netloc.startswith("gs."):
        return None
    # ログイン画面のURLの場合は、url パラメータ(遷移先)の中にスレッドのパラメータがある
    query = parse_qs(parsed.query)
    if "url" in query:
        query = parse_qs(urlparse(query["url"][0]).query)
    try:
        return int(query["bbs010forumSid"][0]), int(query["threadSid"][0])
    except (KeyError, ValueError):
        return None


def collect_pages(root_path: str) -> list[dict]:
    """
    GROWIから手本の対象期間の月ごとのアジェンダを取得し、リンク付きの項目を抜き出す

    Args
    -----------------
    - root_path: str,  過去アジェンダの親ページのパス

    Returns
    -----------------
    - pages: list[dict],  [{"page": "YYYY/MM", "items": [{"title", "title_note", "url", "details"}]}](古い順)

    """
    pages = []
    for path in sorted(growi.list_descendant_paths(root_path)):
        # 月ごとのページ(議事録などの子ページは除く)で、手本の対象期間のものだけを使う
        m = MONTHLY_PAGE_RE.search(path)
        if not m or (int(m.group(1)), int(m.group(2))) < EXAMPLES_SINCE:
            continue
        body = growi.get_page_body(path)
        if body is None:
            continue

        # リンク付きの項目だけを残す(リンクの無い項目は元の投稿・記事をたどれないため)
        items = []
        for item in extract_agenda_items(body):
            parsed = heading_to_output(item["heading"])
            if parsed:
                items.append({**parsed, "details": item["details"]})
        pages.append({"page": f"{m.group(1)}/{m.group(2)}", "items": items})
        print(f"  {m.group(1)}/{m.group(2)}: リンク付きの項目 {len(items)}件")
    return pages


def fetch_sources(pages: list[dict], skip_groupsession: bool) -> None:
    """
    各項目のリンク先から元の投稿・記事を取得し、項目に "input" として設定する(取得できない項目は None)

    Args
    -----------------
    - pages: list[dict],         collect_pages() の戻り値(この関数内で更新する)
    - skip_groupsession: bool,   True のとき GROUPSESSION の記事は取得しない

    Returns
    -----------------
    - None

    """
    # GROUPSESSIONのスレッドはフォーラムごとにまとめて取得するため、先に必要なIDを集める
    gs_targets: dict[int, set[int]] = {}
    for page in pages:
        for item in page["items"]:
            ids = parse_groupsession_url(item["url"])
            if ids:
                gs_targets.setdefault(ids[0], set()).add(ids[1])

    # GROUPSESSIONの記事を取得する(対象期間の少し前から現在までのスレッド一覧から探す)
    gs_threads: dict[tuple[int, int], dict] = {}
    if gs_targets and not skip_groupsession:
        since_ms = int(datetime(EXAMPLES_SINCE[0] - 1, 1, 1).timestamp() * 1000)
        until_ms = int(datetime.now().timestamp() * 1000)
        for forum_sid, thread_sids in gs_targets.items():
            found = gs.get_threads_by_sids(forum_sid, thread_sids, since_ms, until_ms)
            gs_threads.update({(forum_sid, sid): t for sid, t in found.items()})
            print(f"  GROUPSESSION フォーラム{forum_sid}: {len(found)}/{len(thread_sids)}件 取得")

    # 各項目に元の投稿・記事を設定する
    for page in pages:
        for item in page["items"]:
            item["input"] = None
            mm_match = MM_PERMALINK_RE.match(item["url"])
            gs_ids = parse_groupsession_url(item["url"])
            if mm_match:
                post = mm.get_post(mm_match.group(1))
                if post:
                    item["input"] = {**post, "source": "mattermost"}
            elif gs_ids and gs_ids in gs_threads:
                item["input"] = {**gs_threads[gs_ids], "source": "web"}


def main() -> None:
    """過去アジェンダから手本を集めて agenda_examples.json に保存する"""
    parser = argparse.ArgumentParser(description="過去のアジェンダからアジェンダ生成の手本を集める")
    parser.add_argument("--root", default=DEFAULT_ROOT_PATH, help="過去アジェンダの親ページのパス")
    parser.add_argument("--skip-groupsession", action="store_true", help="GROUPSESSIONの記事を取得しない")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="出力先のファイルパス")
    args = parser.parse_args()

    # GROUPSESSIONにログインする(ID・パスワードはメモリ上でのみ使う)
    if not args.skip_groupsession:
        username = input("GROUPSESSIONのID: ")
        password = getpass.getpass("GROUPSESSIONのパスワード: ")
        gs.login(username, password)

    # 過去アジェンダの項目を抜き出し、元の投稿・記事を取得する
    print("GROWIから過去のアジェンダを取得します")
    pages = collect_pages(args.root)
    print("元の投稿・記事を取得します")
    fetch_sources(pages, args.skip_groupsession)

    # 元の投稿・記事を取得できた項目だけを手本として残す(項目が0件のページは除く)
    examples = []
    for page in pages:
        items = [
            {
                "input": item["input"],
                "output": {
                    "title": item["title"],
                    "title_note": item["title_note"],
                    "details": clean_details(item["details"], item["input"]["message"]),
                },
                "url": item["url"],
            }
            for item in page["items"]
            if item["input"]
        ]
        if items:
            examples.append({"page": page["page"], "items": items})

    # 保存する
    args.output.write_text(json.dumps(examples, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(len(p["items"]) for p in pages)
    used = sum(len(p["items"]) for p in examples)
    print(f"保存しました: {args.output}(ページ {len(examples)}件、項目 {used}/{total}件)")


if __name__ == "__main__":
    main()
