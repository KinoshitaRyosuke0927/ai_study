"""
CSV形式で収集した過去レビュー指摘ログを、review_memory層が読み込むJSONL形式（review_log.jsonl）に変換するスクリプト

Args
-----------------
- 入力CSVの列: slide_summary, category, comment, severity（任意）, accepted（任意）
  ヘッダー行はこの列名・列順に従うこと（data/review_log_template.csv を参照）

使い方
-----------------
    # data/review_log_template.csv を data/review_log.jsonl に変換して追記する
    python scripts/csv_to_review_log.py data/review_log_template.csv

    # 既存の review_log.jsonl を上書きしたい場合
    python scripts/csv_to_review_log.py data/review_log_template.csv --overwrite

    # 出力先を明示的に指定する場合
    python scripts/csv_to_review_log.py data/my_export.csv --output data/review_log.jsonl
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

_VALID_SEVERITIES = {"high", "medium", "low"}
_REQUIRED_FIELDS = ("slide_summary", "category", "comment")

_DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "data" / "review_log.jsonl"


def _parse_accepted(value: str | None) -> bool | None:
    """CSVのaccepted列の文字列をbool | Noneに変換する（空欄は未確認としてNoneのまま扱う）"""
    v = (value or "").strip().upper()
    if v in ("TRUE", "1", "YES"):
        return True
    if v in ("FALSE", "0", "NO"):
        return False
    return None


def convert(csv_path: Path) -> list[dict]:
    """
    CSVを読み込み、ReviewMemoryEntryスキーマに沿った辞書のリストに変換する

    Args
    -----------------
    - csv_path: Path,   入力CSVファイルパス

    Returns
    -----------------
    - entries: list[dict],   変換後のエントリ辞書リスト（不正行はスキップ）

    """
    entries: list[dict] = []
    skipped = 0

    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row_no, row in enumerate(reader, start=2):  # ヘッダーが1行目のため2行目から
            # 必須列が欠けている行はスキップする（空行や記入漏れに対応）
            missing = [k for k in _REQUIRED_FIELDS if not (row.get(k) or "").strip()]
            if missing:
                if any((row.get(k) or "").strip() for k in row):
                    print(f"[skip] {row_no}行目: 必須列が空です ({', '.join(missing)})", file=sys.stderr)
                skipped += 1
                continue

            severity = (row.get("severity") or "").strip().lower() or "medium"
            if severity == "blocker":
                # blocker段階は廃止したため high に丸める
                severity = "high"
            if severity not in _VALID_SEVERITIES:
                print(f"[skip] {row_no}行目: severityが不正です ({severity})", file=sys.stderr)
                skipped += 1
                continue

            entries.append({
                "slide_summary": row["slide_summary"].strip(),
                "category": row["category"].strip(),
                "comment": row["comment"].strip(),
                "severity": severity,
                "accepted": _parse_accepted(row.get("accepted")),
            })

    print(f"{len(entries)}件を変換しました（スキップ: {skipped}件）")
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv_path", type=Path, help="変換元のCSVファイル")
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT, help="出力先のJSONLファイル（既定: data/review_log.jsonl）")
    parser.add_argument("--overwrite", action="store_true", help="出力先を追記ではなく上書きする")
    args = parser.parse_args()

    if not args.csv_path.exists():
        parser.error(f"CSVファイルが見つかりません: {args.csv_path}")

    entries = convert(args.csv_path)
    if not entries:
        print("変換対象の行がありませんでした。")
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if args.overwrite else "a"
    with args.output.open(mode, encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    action = "上書き" if args.overwrite else "追記"
    print(f"{args.output} に{action}しました。")


if __name__ == "__main__":
    main()
