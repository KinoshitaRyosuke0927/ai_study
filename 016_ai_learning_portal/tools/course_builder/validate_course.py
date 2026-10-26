"""講座フォルダを、アプリの取り込み処理で検証する(DB には書き込まない)。

backend の仮想環境で実行する:
    backend/.venv/Scripts/python.exe tools/course_builder/validate_course.py content/<講座フォルダ>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# backend/ を import できるようにする
BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app.services.notebook_import import parse_notebook, parse_quiz  # noqa: E402


def main(course_dir: Path) -> None:
    """
    講座フォルダの単元・小テストを解析し、演習と問題の一覧を表示する

    Args
    -----------------
    - course_dir: Path,                 講座フォルダ

    """
    meta = json.loads((course_dir / "course.json").read_text(encoding="utf-8"))
    total = 0
    # 単元ごとにセルの内訳と演習を表示
    for entry in meta["units"]:
        unit = parse_notebook(course_dir / entry["file"])
        exercises = [ex for kind, _, ex in unit.cells if kind == "exercise"]
        md = sum(1 for kind, _, _ in unit.cells if kind == "markdown")
        code = sum(1 for kind, _, _ in unit.cells if kind == "code")
        total += len(exercises)
        print(f"{entry['file']}: {unit.title} / 目標{len(unit.goals)} 説明{md} 例題{code} 演習{len(exercises)}")
        for ex in exercises:
            if hasattr(ex, "grading"):
                print(f"   - {ex.title} [code/{ex.grading}]")
            else:
                print(f"   - {ex.title} [{ex.answer_format}] 正解: {ex.correct_answer}")
    # 小テストの問題を表示
    questions = parse_quiz(course_dir / meta["quiz"])
    print(f"quiz: {len(questions)}問")
    for no, q in enumerate(questions, start=1):
        print(f"   問{no} [{q.answer_format}] 単元{q.unit_position} 正解: {q.correct_answer}")
    print(f"演習 合計 {total} 問")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
