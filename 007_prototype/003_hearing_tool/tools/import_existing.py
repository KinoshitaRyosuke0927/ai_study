"""002_hearing_supporter の既存資料から、ツールの CSV を作る。

使い方（003_hearing_tool フォルダで実行）：
    .venv\\Scripts\\python.exe -m tools.import_existing

何度でもやり直せる。やり直すと data フォルダの CSV を作り直すため、
前の内容は data/backups に保存してから上書きする。
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

from app.config import TOOL_ROOT, load_config
from app.storage import TABLES, backup, data_dir, new_id, now_text, write_table

# 取り込み元のフォルダ
SOURCE_DIR = TOOL_ROOT.parent / "002_hearing_supporter"

# 対象者ごとのファイル名（文字起こしと計画書で共通の名前）
PEOPLE = {
    "isahai": "砂盃さん",
    "ishii": "石井さん",
}

# 聞き手の表記（資料では A、B と書いていたものを、ツールでは名前で表示する）
INTERVIEWERS = {
    "A": "浅野間",
    "B": "木下",
}

# 計画書の「課題の仮説」に付ける仮のテーマ（横断表示でまとめる単位。画面から変更できる）
ISSUE_THEMES = {
    "作業時間の見積もりがずれ、計画が崩れる": "作業時間の見積もり",
    "作業時間の見積もりがずれる": "作業時間の見積もり",
    "毎日の時間配分を考える負担が大きい": "時間の使い方",
    "遅れに気づくのが遅い": "進み具合の把握",
    "連絡の確認と作業の整理に時間がかかる": "連絡の確認",
    "定例の宿題の確認に手間がかかる": "定例の準備と記録",
    "企画書の相談タイミングを判断しにくい": "判断の基準",
    "調査情報の収集と整理が重い": "調査",
    "サービスの異常確認に時間がかかる": "監視・保守",
    "コストの消し忘れに気づきにくい": "監視・保守",
    "ライブラリ更新の確認が負担": "監視・保守",
    "設計情報の共有に手間がかかる": "作業の引き渡し",
}

# 対象者ごとの聞き手用のメモ（計画書の「当日の注意」から要点を取り出したもの）
PERSON_NOTES = {
    "砂盃さん": "提案先の矢野さんは上長で、聞き手は部下にあたる。発言の扱いに配慮し、"
              "能力ではなく判断の材料や仕組みに話を向ける。",
    "石井さん": "会議が苦手なため時間を延ばさない。「属人化」という言葉を避ける。"
              "第1回の通勤、喫煙、食事の話は課題として扱わない。",
}

# 文字起こしで誤認識されやすい表記（第1回の文字起こしで実際に出たもの）
MISRECOGNITIONS = {
    "砂盃さん": "イサイ;伊沢",
    "石井さん": "井上",
    "caitayo": "書いてある",
    "MemMen": "メンメン;MemMem",
}

# 用語集の分類に使うサービス名
SERVICE_TERMS = {"Mattermost", "AI自動入力", "MemMen", "レビューサービス", "caitayo", "データアナリストのサイト"}

# 全員に共通の質問（どの回にも追加できる部品）
COMMON_QUESTIONS = [
    ("◎", "前回のお話を画面のように整理しました。ずれている点はありますか？", "前提の修正", "0"),
    ("◎", "先週の作業で、一番なくしたかったものは何ですか？", "本人の課題", "0"),
    ("◎", "その作業の予定や実際にかかった時間、結果の記録は、どこかに残っていますか？ どのくらい前の分までありますか？",
     "データの有無", "1"),
    ("◎", "今日の話を整理すると、○○が大きいと理解しました。合っていますか？ 一つだけなくせるなら、どれをなくしたいですか？",
     "優先順位", "0"),
    ("◎", "今日のお話に関連する記録や資料で、機密を除いて共有いただけるものはありますか？", "データの提供可否", "0"),
]


class Importer:
    """既存資料を読み込み、テーブルごとの行を組み立てる。"""

    def __init__(self, source: Path, user: str) -> None:
        """取り込みの準備をする。

        Args:
            source: 取り込み元のフォルダ（002_hearing_supporter）。
            user: 各行の updated_by に記録する名前。

        Returns:
            None
        """
        self.source = source
        self.user = user
        self.stamp = now_text()
        self.tables: dict[str, list[dict]] = {t: [] for t in TABLES}
        self.persons: dict[str, dict] = {}
        self.messages: list[str] = []

    # ---------------------------------------------------------------- 共通の処理

    def add(self, table: str, values: dict) -> dict:
        """行を追加する。

        Args:
            table: テーブル名。
            values: 列の値。

        Returns:
            dict: 追加した行。
        """
        # 全列を空で用意し、IDと更新情報を付ける
        key, cols = TABLES[table]
        row = {c: "" for c in cols}
        row.update(values)
        row[key] = row[key] or new_id()
        row["updated_by"] = self.user
        row["updated_at"] = self.stamp
        self.tables[table].append(row)
        return row

    def read(self, relative: str) -> str:
        """取り込み元のファイルを読む。

        Args:
            relative: 取り込み元フォルダからの相対パス。

        Returns:
            str: ファイルの内容。なければ空文字。
        """
        path = self.source / relative
        if not path.exists():
            self.messages.append(f"見つからないため飛ばしました：{relative}")
            return ""
        return path.read_text(encoding="utf-8").replace("\r\n", "\n")

    # ---------------------------------------------------------------- 用語集

    def import_terms(self) -> dict[str, str]:
        """terms.md から用語集を作る。

        Returns:
            dict[str, str]: 用語ごとの説明（対象者の役割に使う）。
        """
        descriptions = {}
        for line in self.read("terms.md").splitlines():
            # 「用語：説明」の行だけを取り出す
            if "：" not in line or line.startswith("#"):
                continue
            name_part, description = line.split("：", 1)

            # 「堀口さん、重松さん」や「A, B」は1人ずつに分ける
            names = [n.strip() for n in re.split(r"[、,]", name_part) if n.strip()]
            if not all(n.endswith("さん") or n in ("A", "B") for n in names):
                names = [name_part.strip()]

            for name in names:
                # 聞き手は A、B ではなく名前で登録する
                name = INTERVIEWERS.get(name, name)
                descriptions[name] = description.strip()
                self.add("terms", {
                    "term": name,
                    "category": self._term_category(name, description),
                    "description": description.strip(),
                    "misrecognitions": MISRECOGNITIONS.get(name, ""),
                })
        return descriptions

    @staticmethod
    def _term_category(name: str, description: str) -> str:
        """用語の分類を決める。

        Args:
            name: 用語。
            description: 説明。

        Returns:
            str: "人名"、"サービス"、"部署"、"その他" のいずれか。
        """
        if name.endswith("さん") or name in ("A", "B") or name in INTERVIEWERS.values():
            return "人名"
        if name in SERVICE_TERMS:
            return "サービス"
        if name == "AIB" or "事業部" in name:
            return "部署"
        return "その他"

    # ---------------------------------------------------------------- 第1回（文字起こし）

    def import_first_sessions(self, descriptions: dict[str, str]) -> None:
        """文字起こしから、対象者と第1回の回、発言を作る。

        Args:
            descriptions: 用語ごとの説明（対象者の役割に使う）。

        Returns:
            None
        """
        for key, name in PEOPLE.items():
            # 対象者を作る
            person = self.add("persons", {
                "name": name,
                "role": descriptions.get(name, ""),
                "note": PERSON_NOTES.get(name, ""),
            })
            self.persons[key] = person

            # 文字起こしの見出しから音声の長さを取り出す
            text = self.read(f"hearing/{key}.md")
            length = re.search(r"音声の長さ：([\d:]+)", text)

            # 音声があれば data/audio に複製する
            audio_name = ""
            audio_src = self.source / "hearing" / f"{key}.mp3"
            if audio_src.exists():
                audio_name = f"{key}_round1.mp3"
                shutil.copy2(audio_src, data_dir() / "audio" / audio_name)

            # 第1回の回を作る
            session = self.add("sessions", {
                "person_id": person["person_id"],
                "round": "1",
                "interviewers": "、".join(INTERVIEWERS.values()),
                "duration_min": "30",
                "status": "整理済み",
                "purpose": "普段の1日の流れと、平均的な業務内容を知る。",
                "audio_file": audio_name,
                "memo": f"音声の長さ：{length.group(1)}" if length else "",
            })
            person["first_session_id"] = session["session_id"]

            # 発言を取り込む
            utterances = self._parse_transcript(text)
            excluded_from = self._excluded_start(key, utterances)
            for i, (speaker, body) in enumerate(utterances, start=1):
                excluded = excluded_from is not None and excluded_from <= i - 1 < len(utterances) - 1
                self.add("utterances", {
                    "session_id": session["session_id"],
                    "order": str(i),
                    "speaker": INTERVIEWERS.get(speaker, speaker),
                    "text": body,
                    "review_status": "推敲済み",
                    "excluded": "1" if excluded else "0",
                })

    @staticmethod
    def _parse_transcript(text: str) -> list[tuple[str, str]]:
        """文字起こしの Markdown を、発言者と発言の組に分ける。

        「A：」「石井さん：」のように、発言者だけが書かれた行を区切りとみなす。

        Args:
            text: 文字起こしの内容。

        Returns:
            list[tuple[str, str]]: (発言者, 発言) の一覧。
        """
        speaker_line = re.compile(r"^(A|B|\S+さん)\s*[：；:;]\s*$")
        result: list[tuple[str, str]] = []
        speaker, lines = None, []
        for line in text.splitlines():
            # 発言者の行が来たら、それまでの発言を確定する
            match = speaker_line.match(line.strip())
            if match:
                if speaker and "\n".join(lines).strip():
                    result.append((speaker, "\n".join(lines).strip()))
                speaker, lines = match.group(1), []
            elif speaker:
                lines.append(line)
        # 最後の発言を確定する
        if speaker and "\n".join(lines).strip():
            result.append((speaker, "\n".join(lines).strip()))
        return result

    @staticmethod
    def _excluded_start(key: str, utterances: list[tuple[str, str]]) -> int | None:
        """分析の対象外にする発言の始まりを返す。

        石井さんの第1回は、通勤の質問以降が私的な話題のため対象外にする（最後のお礼は残す）。

        Args:
            key: 対象者のファイル名。
            utterances: 発言の一覧。

        Returns:
            int | None: 対象外にする最初の発言の位置。なければ None。
        """
        if key != "ishii":
            return None
        return next((i for i, (_, body) in enumerate(utterances) if "通勤に時間がかかる" in body), None)

    # ---------------------------------------------------------------- 第2回（進行資料）

    def import_second_sessions(self) -> None:
        """進行資料と計画書から、第2回の回、仮説、区切り、質問を作る。

        Returns:
            None
        """
        overview = self.read("question/2nd_hearing_overview.md")
        sections = split_sections(overview, "## ")

        # 全員に共通の目的と、聞き手用のメモを取り出す
        purpose = sections.get("第2回の目的", "").strip()
        memo_parts = []
        for title in ("第1回からの変更点", "当日の進め方", "もし手に入ればモデル作成に使えそうな情報"):
            if sections.get(title, "").strip():
                memo_parts.append(f"【{title}】\n{sections[title].strip()}")
        memo = "\n\n".join(memo_parts)

        # 仮説を対象者ごとに取り出す
        hypothesis_sections = split_sections(sections.get("深掘りしたい課題の仮説", ""), "### ")

        for key, name in PEOPLE.items():
            person = self.persons[key]
            plan = self.read(f"question/{key}_2nd_plan.md")
            plan_sections = split_sections(plan, "## ")

            # 第2回の回を作る
            session = self.add("sessions", {
                "person_id": person["person_id"],
                "round": "2",
                "interviewers": "、".join(INTERVIEWERS.values()),
                "duration_min": "30",
                "status": "準備中",
                "purpose": purpose,
                "request_message": first_code_block(section_starting(plan_sections, "3.")),
                "memo": memo,
            })

            # 仮説を作る
            hyps = self._import_hypotheses(hypothesis_sections.get(name, ""), person, session)

            # タイムテーブル、要約、質問を作る
            person_section = split_sections(sections.get(f"{name}：タイムテーブルと質問", ""), "### ")
            summary = first_code_block(next((v for k, v in person_section.items() if k.endswith("の要約")), ""))
            session["screen_summary"] = summary
            segments = self._import_segments(person_section.get("タイムテーブル", ""), session, hyps)
            self._import_questions(person_section.get("質問", ""), session, segments)

            # 計画書の解決策の候補と評価の観点を取り込む
            self._import_solutions(section_starting(plan_sections, "7."), person)
            self._import_criteria(section_starting(plan_sections, "10."))

    def _import_hypotheses(self, text: str, person: dict, session: dict) -> dict[str, dict]:
        """仮説の節から仮説を作る。

        Args:
            text: 対象者の仮説の節。
            person: 対象者の行。
            session: 第2回の行。

        Returns:
            dict[str, dict]: 表示名（仮説1、補足など）ごとの仮説の行。
        """
        result = {}
        # 「**仮説1：見出し**」で区切る
        blocks = re.split(r"^\*\*(.+?)：(.+?)\*\*\s*$", text, flags=re.M)
        for i in range(1, len(blocks) - 2, 3):
            label, title, content = blocks[i].strip(), blocks[i + 1].strip(), blocks[i + 2]

            # 本文と「お聞きしたいことの例」を分ける
            body, _, example_text = content.partition("お聞きしたいことの例：")
            examples = [line[2:].strip() for line in example_text.splitlines() if line.startswith("- ")]
            result[label] = self.add("hypotheses", {
                "person_id": person["person_id"],
                "session_id": session["session_id"],
                "label": label,
                "title": title,
                "body": body.strip(),
                "examples": "\n".join(examples),
                "status": "未確認",
                "source": "第1回の発言と聞き手の推測（別メンバーの仮説を含む）",
                "visibility": "聞き手のみ",
            })
        return result

    def _import_segments(self, text: str, session: dict, hyps: dict[str, dict]) -> list[dict]:
        """タイムテーブルの表から区切りを作る。

        Args:
            text: タイムテーブルの節。
            session: 第2回の行。
            hyps: 表示名ごとの仮説。

        Returns:
            list[dict]: 作った区切りの一覧。
        """
        segments = []
        for order, cells in enumerate(parse_table(text), start=1):
            # 「5〜14分」から開始と終了を取り出す
            times = re.findall(r"\d+", cells[0])
            title = strip_bold(cells[1])

            # 見出しの「仮説1」などから仮説をひも付ける（打ち合わせの区切りは「補足」の仮説）
            linked = [h["hypothesis_id"] for label, h in hyps.items() if label in title]
            if "打ち合わせ" in title and "補足" in hyps:
                linked.append(hyps["補足"]["hypothesis_id"])

            segments.append(self.add("segments", {
                "session_id": session["session_id"],
                "order": str(order),
                "start_min": times[0] if times else "",
                "end_min": times[1] if len(times) > 1 else "",
                "title": title,
                "aim": strip_bold(cells[2]) if len(cells) > 2 else "",
                "hypothesis_ids": ";".join(linked),
            }))
        return segments

    def _import_questions(self, text: str, session: dict, segments: list[dict]) -> None:
        """質問の節から質問を作る。

        Args:
            text: 質問の節。
            session: 第2回の行。
            segments: この回の区切り。

        Returns:
            None
        """
        # 「**見出し（2〜5分）**」で区切る
        blocks = re.split(r"^\*\*(.+?)（(\d+)〜(\d+)分）\*\*\s*$", text, flags=re.M)
        for i in range(1, len(blocks) - 3, 4):
            start, end, table = blocks[i + 1], blocks[i + 2], blocks[i + 3]

            # 時間が一致する区切りを探す
            segment = next((s for s in segments if s["start_min"] == start and s["end_min"] == end), None)
            if segment is None:
                self.messages.append(f"区切りが見つからない質問のまとまりがあります：{blocks[i]}")

            # 表の行ごとに質問を作る
            for order, cells in enumerate(parse_table(table), start=1):
                priority, label, question, check = (cells + ["", "", "", ""])[:4]
                check = strip_bold(check)
                self.add("questions", {
                    "session_id": session["session_id"],
                    "segment_id": segment["segment_id"] if segment else "",
                    "order": str(order),
                    "label": "" if label.strip() in ("-", "") else label.strip(),
                    "priority": priority.strip(),
                    "text": strip_bold(question),
                    "check_point": check,
                    "is_data_question": "1" if "データの有無" in check else "0",
                    "hypothesis_ids": segment["hypothesis_ids"] if segment else "",
                    "asked": "未",
                })

    def _import_solutions(self, text: str, person: dict) -> None:
        """計画書の解決策の仮説の表から、課題カード（候補）と解決策の候補を作る。

        Args:
            text: 計画書の第7章。
            person: 対象者の行。

        Returns:
            None
        """
        for cells in parse_table(text):
            if len(cells) < 5:
                continue
            # 課題の仮説を、状態「候補」の課題カードにする
            issue = self.add("issues", {
                "person_id": person["person_id"],
                "session_ids": person["first_session_id"],
                "title": strip_bold(cells[0]),
                "theme": ISSUE_THEMES.get(strip_bold(cells[0]), ""),
                "certainty": "印象のみ",
                "status": "候補",
                "visibility": "聞き手のみ",
            })
            # 生成AI以外の候補を、解決策の候補にする
            self.add("solutions", {
                "issue_ids": issue["issue_id"],
                "method": strip_bold(cells[1]),
                "uses_genai": "0",
                "required_data": strip_bold(cells[2]),
                "concern": strip_bold(cells[4]),
            })

    def _import_criteria(self, text: str) -> None:
        """計画書の候補の評価の表から、評価の観点を作る（重複は除く）。

        Args:
            text: 計画書の第10章。

        Returns:
            None
        """
        known = {c["criterion"] for c in self.tables["criteria"]}
        for cells in parse_table(split_sections(text, "### ").get("候補の評価", "")):
            if len(cells) < 2 or cells[0] in known:
                continue
            known.add(cells[0])
            self.add("criteria", {
                "criterion": cells[0],
                "question": cells[1],
                "order": str(len(self.tables["criteria"]) + 1),
            })

    # ---------------------------------------------------------------- 共通の質問

    def import_common_questions(self) -> None:
        """全員に共通の質問を作る。

        Returns:
            None
        """
        for order, (priority, text, check, is_data) in enumerate(COMMON_QUESTIONS, start=1):
            self.add("questions", {
                "session_id": "",
                "order": str(order),
                "priority": priority,
                "text": text,
                "check_point": check,
                "is_data_question": is_data,
                "asked": "未",
            })


# -------------------------------------------------------------------- Markdown の解析


def split_sections(text: str, marker: str) -> dict[str, str]:
    """見出しごとに本文を分ける。

    Args:
        text: Markdown の文字列。
        marker: 見出しの記号（"## " や "### "）。

    Returns:
        dict[str, str]: 見出しの文字列ごとの本文。
    """
    result = {}
    current, lines = None, []
    in_code = False
    for line in text.splitlines():
        # コードブロックの中の「#」は見出しとして扱わない
        if line.startswith("```"):
            in_code = not in_code
        if not in_code and line.startswith(marker):
            if current is not None:
                result[current] = "\n".join(lines)
            current, lines = line[len(marker):].strip(), []
        elif current is not None:
            lines.append(line)
    if current is not None:
        result[current] = "\n".join(lines)
    return result


def section_starting(sections: dict[str, str], prefix: str) -> str:
    """見出しが指定の文字で始まる節を返す。

    Args:
        sections: split_sections の結果。
        prefix: 見出しの先頭（例："7."）。

    Returns:
        str: 節の本文。なければ空文字。
    """
    return next((body for title, body in sections.items() if title.startswith(prefix)), "")


def first_code_block(text: str) -> str:
    """最初のコードブロックの中身を返す。

    Args:
        text: Markdown の文字列。

    Returns:
        str: コードブロックの中身。なければ空文字。
    """
    match = re.search(r"```[a-z]*\n(.*?)\n```", text, flags=re.S)
    return match.group(1).strip() if match else ""


def parse_table(text: str) -> list[list[str]]:
    """Markdown の表の行を、セルの一覧として返す（見出しと区切りの行は除く）。

    Args:
        text: 表を含む Markdown の文字列。

    Returns:
        list[list[str]]: 行ごとのセルの一覧。
    """
    rows = []
    header_seen = False
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            # 表が終わったら、次の表に備えて見出しの状態を戻す
            header_seen = False
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        # 区切りの行（|---|）は飛ばす
        if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
            continue
        # 最初の行は見出しなので飛ばす
        if not header_seen:
            header_seen = True
            continue
        rows.append(cells)
    return rows


def strip_bold(text: str) -> str:
    """太字の記号を取り除き、「仮説1： 」のような余分な空白を詰める。

    Args:
        text: 文字列。

    Returns:
        str: 記号を除いた文字列。
    """
    return re.sub(r"：\s+", "：", text.replace("**", "")).strip()


# -------------------------------------------------------------------- 実行


def main() -> int:
    """取り込みを実行する。

    Returns:
        int: 終了コード（0 は成功）。
    """
    parser = argparse.ArgumentParser(description="既存のヒアリング資料から CSV を作る")
    parser.add_argument("--source", type=Path, default=SOURCE_DIR, help="取り込み元のフォルダ")
    parser.add_argument("--yes", action="store_true", help="既存のデータがあっても確認せずに作り直す")
    args = parser.parse_args()

    # 既存のデータがあれば、確認してからバックアップする
    target = data_dir()
    existing = [p for p in target.glob("*.csv") if p.stat().st_size > 0]
    if existing:
        if not args.yes:
            answer = input(f"{target} の CSV を作り直します。ツールで編集した内容は消えます（バックアップは残ります）。続けますか？ [y/N] ")
            if answer.strip().lower() != "y":
                print("中止しました。")
                return 1
        print(f"バックアップしました：{backup('reimport')}")

    # 資料を読み込んで行を組み立てる
    importer = Importer(args.source, load_config()["user_name"])
    descriptions = importer.import_terms()
    importer.import_first_sessions(descriptions)
    importer.import_second_sessions()
    importer.import_common_questions()

    # すべてのテーブルを書き出す（空のテーブルも見出しだけ書く）
    for table, rows in importer.tables.items():
        write_table(table, rows)

    # 結果を表示する
    for table, rows in importer.tables.items():
        print(f"{table:>13}: {len(rows)}件")
    for message in importer.messages:
        print(f"注意：{message}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
