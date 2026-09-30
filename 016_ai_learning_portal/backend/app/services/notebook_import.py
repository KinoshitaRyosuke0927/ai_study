"""Jupyter Notebook(.ipynb)から講座を取り込むモジュール。

講座フォルダの構成と、演習・小テストの書き方は docs/notebook-format.md を参照。

    <講座フォルダ>/
      course.json         講座情報と単元の並び順
      01_xxx.ipynb        単元(1ファイル = 1単元)
      quiz.ipynb          小テスト
      data/               演習で使うデータファイル(任意)
"""

from __future__ import annotations

import json
import math
import mimetypes
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import nbformat
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.constants import (
    AnswerFormat,
    CellType,
    CourseLevel,
    CourseStatus,
    Grading,
    ProblemKind,
    VerifyStatus,
)
from app.models import Cell, Course, CoursePrerequisite, Dataset, Problem, Unit, User

# 演習用のマーカー行(セルの1行目)
_STARTER = "# @starter"
_SOLUTION = "# @solution"
_TEST = "# @test"
# 解答セル先頭の設定行 例) "# @hint: ヒント文"
_DIRECTIVE = re.compile(r"^#\s*@(\w+)\s*:\s*(.*)$")
# 単元の学習目標セルの見出し
_GOALS_HEADING = re.compile(r"^##\s*学習目標\s*$")
# 小テストの問題セル先頭の設定ブロック <!-- @question ... -->
_QUESTION_META = re.compile(r"^\s*<!--\s*@question\s*\n(.*?)-->\s*", re.DOTALL)
# 箇条書きの行(選択肢)
_BULLET = re.compile(r"^\s*[-*]\s+(.+?)\s*$")


class NotebookFormatError(Exception):
    """講座フォルダやノートブックの書き方に誤りがある。"""


@dataclass
class _ParsedCode:
    """解析途中のコード問題(演習・小テスト共通)。"""

    title: str
    prompt: str
    hint: str
    starter_code: str
    solution: str
    grading: str
    expected_output: str
    test_code: str
    tolerance: float
    explanation: str


@dataclass
class _ParsedUnit:
    """解析途中の単元。"""

    title: str
    summary: str
    goals: list[str] = field(default_factory=list)
    # (セル種別, 本文, 演習) の並び
    cells: list[tuple[str, str, _ParsedCode | None]] = field(default_factory=list)


@dataclass
class _ParsedQuestion:
    """解析途中の小テストの問題。"""

    answer_format: str
    prompt: str
    choices: list[str]
    correct_answer: str
    tolerance: float
    explanation: str
    unit_position: int | None
    code: _ParsedCode | None


def _first_line(source: str) -> str:
    """
    セル本文の1行目を返す

    Args
    -----------------
    - source: str,                      セル本文

    Returns
    -----------------
    - line: str,                        前後の空白を除いた1行目

    """
    # 先頭の空行を飛ばして1行目を返却
    return source.strip().split("\n", 1)[0].strip()


def _strip_first_line(source: str) -> str:
    """
    セル本文から1行目(マーカー行)を取り除く

    Args
    -----------------
    - source: str,                      セル本文

    Returns
    -----------------
    - body: str,                        2行目以降

    """
    # 1行目以降を取り出して前後の空行を除いて返却
    parts = source.strip().split("\n", 1)
    return parts[1].strip("\n") if len(parts) > 1 else ""


def _cell_text_output(cell) -> str:
    """
    コードセルに保存されている出力(標準出力と最後の式の値)を取り出す

    Args
    -----------------
    - cell: NotebookNode,               コードセル

    Returns
    -----------------
    - text: str,                        出力テキスト

    """
    # 入れ物用意
    chunks: list[str] = []
    # 出力を順に見て、テキストとして比較できるものだけ集める
    for out in cell.get("outputs", []):
        # print() などの標準出力
        if out.get("output_type") == "stream" and out.get("name") == "stdout":
            chunks.append(out.get("text", ""))
        # セル末尾の式の値
        elif out.get("output_type") == "execute_result":
            text = out.get("data", {}).get("text/plain", "")
            chunks.append(text if text.endswith("\n") else text + "\n")
        # 実行時エラーが保存されている場合は解答として不正
        elif out.get("output_type") == "error":
            raise NotebookFormatError("解答セルの出力にエラーが含まれています")
    # 連結して返却
    return "".join(chunks).rstrip("\n")


def _parse_solution(source: str) -> tuple[dict[str, str], str]:
    """
    解答セルから設定行とコードを分離する

    Args
    -----------------
    - source: str,                      "# @solution" を除いた解答セル本文

    Returns
    -----------------
    - directives: dict[str, str],       設定(title, hint, grading, tolerance, explanation)
    - code: str,                        解答コード

    """
    # 入れ物用意
    directives: dict[str, str] = {}
    lines = source.split("\n")
    # 先頭から続く設定行を読み取る
    while lines:
        match = _DIRECTIVE.match(lines[0].strip())
        if not match:
            break
        directives[match.group(1).lower()] = match.group(2).strip()
        lines.pop(0)
    # 残りを解答コードとして返却
    return directives, "\n".join(lines).strip("\n")


def _parse_code_problem(cells: list, i: int, prompt: str, name: str) -> tuple[_ParsedCode, int]:
    """
    「# @starter」セルから始まるコード問題(初期コード・解答・任意のテスト)を解析する

    Args
    -----------------
    - cells: list,                      ノートブックのセル一覧
    - i: int,                           「# @starter」セルの位置
    - prompt: str,                      問題文
    - name: str,                        エラーメッセージ用のファイル名

    Returns
    -----------------
    - problem: _ParsedCode,             解析したコード問題
    - consumed: int,                    読み進めたセル数

    """
    # 次のセルが解答セルであることを確認
    if i + 1 >= len(cells) or _first_line(cells[i + 1].source) != _SOLUTION:
        raise NotebookFormatError(f"{name}: 「{_STARTER}」セルの次に「{_SOLUTION}」セルが必要です")
    directives, solution = _parse_solution(_strip_first_line(cells[i + 1].source))
    grading = directives.get("grading", Grading.OUTPUT)
    if grading not in Grading.ALL:
        raise NotebookFormatError(f"{name}: @grading は output か test を指定してください")
    # 採点方式が「出力一致」の場合は、解答セルに保存された出力を想定出力にする
    expected = _cell_text_output(cells[i + 1])
    if grading == Grading.OUTPUT and not expected:
        raise NotebookFormatError(f"{name}: 解答セルの出力がありません。解答セルを実行してから保存してください")
    # 任意のテストセル
    test_code = ""
    consumed = 2
    if i + 2 < len(cells) and _first_line(cells[i + 2].source) == _TEST:
        test_code = _strip_first_line(cells[i + 2].source)
        consumed = 3
    if grading == Grading.TEST and not test_code:
        raise NotebookFormatError(f"{name}: @grading: test の問題には「{_TEST}」セルが必要です")
    # 解析結果を返却
    problem = _ParsedCode(
        title=directives.get("title", ""),
        prompt=prompt,
        hint=directives.get("hint", ""),
        starter_code=_strip_first_line(cells[i].source),
        solution=solution,
        grading=grading,
        expected_output=expected,
        test_code=test_code,
        tolerance=float(directives.get("tolerance", "1e-6")),
        explanation=directives.get("explanation", ""),
    )
    return problem, consumed


def parse_notebook(path: Path) -> _ParsedUnit:
    """
    ノートブック1冊を単元として解析する

    Args
    -----------------
    - path: Path,                       .ipynb ファイルのパス

    Returns
    -----------------
    - unit: _ParsedUnit,                解析した単元

    """
    # ノートブックを読み込む
    nb = nbformat.read(str(path), as_version=4)
    cells = [c for c in nb.cells if c.source.strip()]
    # 1つ目のセルは「# 単元タイトル」で始まる Markdown でなければならない
    if not cells or cells[0].cell_type != "markdown" or not _first_line(cells[0].source).startswith("# "):
        raise NotebookFormatError(f"{path.name}: 1つ目のセルは「# 単元タイトル」で始まる Markdown にしてください")
    title = _first_line(cells[0].source)[2:].strip()
    unit = _ParsedUnit(title=title, summary=_strip_first_line(cells[0].source).strip())
    # 2つ目以降のセルを順に解析
    i = 1
    while i < len(cells):
        cell = cells[i]
        first = _first_line(cell.source)
        # 学習目標セル: 箇条書きを学習目標として取り込み、セル自体は表示しない
        if cell.cell_type == "markdown" and _GOALS_HEADING.match(first):
            unit.goals = [
                re.sub(r"^[-*]\s+", "", line.strip())
                for line in cell.source.split("\n")[1:]
                if re.match(r"^\s*[-*]\s+", line)
            ]
            i += 1
            continue
        # Markdown セル: 説明セル
        if cell.cell_type == "markdown":
            unit.cells.append((CellType.MARKDOWN, cell.source.strip(), None))
            i += 1
            continue
        # 初期コードセル: 直前の説明セルを問題文、次の解答セル(と任意のテストセル)を合わせて演習にする
        if first == _STARTER:
            if not unit.cells or unit.cells[-1][0] != CellType.MARKDOWN:
                raise NotebookFormatError(f"{path.name}: 「{_STARTER}」セルの直前に問題文の Markdown セルが必要です")
            prompt = unit.cells.pop()[1]
            exercise, consumed = _parse_code_problem(cells, i, prompt, path.name)
            unit.cells.append((CellType.EXERCISE, "", exercise))
            i += consumed
            continue
        # 対応する初期コードセルのない解答・テストセルは書き方の誤り
        if first in (_SOLUTION, _TEST):
            raise NotebookFormatError(f"{path.name}: 「{first}」セルの前に「{_STARTER}」セルが必要です")
        # それ以外のコードセル: 例題セル
        unit.cells.append((CellType.CODE, cell.source.strip("\n"), None))
        i += 1
    # 演習が1問もない単元は完了できないためエラー
    if not any(t == CellType.EXERCISE for t, _, _ in unit.cells):
        raise NotebookFormatError(f"{path.name}: 単元には演習が1問以上必要です")
    # 解析結果を返却
    return unit


def _parse_question_meta(source: str) -> tuple[dict[str, str], str] | None:
    """
    小テストの問題セルから設定ブロック(<!-- @question ... -->)と本文を取り出す

    Args
    -----------------
    - source: str,                      Markdown セルの本文

    Returns
    -----------------
    - parsed: tuple | None,             (設定, 設定ブロックを除いた本文)。問題セルでなければ None

    """
    # 設定ブロックで始まらないセルは問題セルではない
    match = _QUESTION_META.match(source)
    if not match:
        return None
    # 「キー: 値」の行を読み取る
    meta: dict[str, str] = {}
    for line in match.group(1).split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip().lower()] = value.strip()
    # 設定と本文を返却
    return meta, source[match.end() :].strip()


def parse_quiz(path: Path) -> list[_ParsedQuestion]:
    """
    小テストのノートブックを解析する

    Args
    -----------------
    - path: Path,                       quiz.ipynb のパス

    Returns
    -----------------
    - questions: list[_ParsedQuestion], 解析した問題

    """
    # ノートブックを読み込む
    nb = nbformat.read(str(path), as_version=4)
    cells = [c for c in nb.cells if c.source.strip()]
    questions: list[_ParsedQuestion] = []
    i = 0
    while i < len(cells):
        cell = cells[i]
        parsed = _parse_question_meta(cell.source) if cell.cell_type == "markdown" else None
        # 問題セル以外の Markdown(小テストの説明など)は読み飛ばす
        if cell.cell_type == "markdown" and parsed is None:
            i += 1
            continue
        # 問題セルに属さないコードセルは書き方の誤り
        if parsed is None:
            raise NotebookFormatError(f"{path.name}: コードセルは「type: code」の問題セルの直後に置いてください")
        meta, body = parsed
        qtype = meta.get("type", "")
        no = len(questions) + 1
        unit_position = int(meta["unit"]) if meta.get("unit") else None
        explanation = meta.get("explanation", "")
        # 選択式: 本文の最後の箇条書きを選択肢にする
        if qtype == AnswerFormat.CHOICE:
            lines = body.split("\n")
            end = len(lines)
            while end > 0 and not lines[end - 1].strip():
                end -= 1
            start = end
            while start > 0 and _BULLET.match(lines[start - 1]):
                start -= 1
            choices = [_BULLET.match(line).group(1) for line in lines[start:end]]  # type: ignore[union-attr]
            answer = meta.get("answer", "")
            if len(choices) < 2:
                raise NotebookFormatError(f"{path.name}: 問{no} の選択肢(箇条書き)が2つ以上必要です")
            if answer not in choices:
                raise NotebookFormatError(f"{path.name}: 問{no} の answer が選択肢に含まれていません")
            prompt = "\n".join(lines[:start]).strip()
            questions.append(
                _ParsedQuestion(AnswerFormat.CHOICE, prompt, choices, answer, 0.0, explanation, unit_position, None)
            )
            i += 1
        # 数値入力: answer を数値として保存する
        elif qtype == AnswerFormat.NUMERIC:
            try:
                value = float(meta.get("answer", ""))
            except ValueError:
                raise NotebookFormatError(f"{path.name}: 問{no} の answer は数値で指定してください")
            if not math.isfinite(value):
                raise NotebookFormatError(f"{path.name}: 問{no} の answer は有限の数値で指定してください")
            tolerance = float(meta.get("tolerance", "1e-6"))
            questions.append(
                _ParsedQuestion(
                    AnswerFormat.NUMERIC, body, [], meta["answer"], tolerance, explanation, unit_position, None
                )
            )
            i += 1
        # コード: 次のセルから初期コード・解答・(任意の)テストを読む
        elif qtype == AnswerFormat.CODE:
            if i + 1 >= len(cells) or _first_line(cells[i + 1].source) != _STARTER:
                raise NotebookFormatError(f"{path.name}: 問{no}(type: code)の次に「{_STARTER}」セルが必要です")
            code, consumed = _parse_code_problem(cells, i + 1, body, path.name)
            if not code.explanation:
                code.explanation = explanation
            questions.append(
                _ParsedQuestion(
                    AnswerFormat.CODE, body, [], "", code.tolerance, code.explanation, unit_position, code
                )
            )
            i += 1 + consumed
        else:
            raise NotebookFormatError(f"{path.name}: 問{no} の type は choice / numeric / code のいずれかにしてください")
    # 問題が1問もない小テストはエラー
    if not questions:
        raise NotebookFormatError(f"{path.name}: 小テストの問題がありません")
    # 解析結果を返却
    return questions


def _code_problem(
    course_id: int, unit_id: int | None, kind: str, position: int, title: str, code: _ParsedCode
) -> Problem:
    """
    解析したコード問題から Problem を生成する

    Args
    -----------------
    - course_id: int,                   講座 ID
    - unit_id: int | None,              単元 ID(小テストは None)
    - kind: str,                        問題の種類(ProblemKind)
    - position: int,                    並び順
    - title: str,                       タイトル
    - code: _ParsedCode,                解析したコード問題

    Returns
    -----------------
    - problem: Problem,                 生成した問題(未登録)

    """
    # 項目を移して返却(作成者自身が解答と出力を用意しているため検証済みとして扱う)
    return Problem(
        course_id=course_id,
        unit_id=unit_id,
        kind=kind,
        position=position,
        answer_format=AnswerFormat.CODE,
        title=title,
        prompt=code.prompt,
        hint=code.hint,
        starter_code=code.starter_code,
        grading=code.grading,
        expected_output=code.expected_output,
        test_code=code.test_code,
        tolerance=code.tolerance,
        explanation=code.explanation,
        author_answer=code.solution,
        verify_status=VerifyStatus.VERIFIED,
    )


def add_parsed_unit(session: Session, course_id: int, parsed: _ParsedUnit, position: int, minutes: int) -> Unit:
    """
    解析した単元を、セル・演習とあわせて講座に登録する

    Args
    -----------------
    - session: Session,                 DB セッション
    - course_id: int,                   講座 ID
    - parsed: _ParsedUnit,              解析した単元
    - position: int,                    単元の位置(1 始まり)
    - minutes: int,                     目安時間(分)

    Returns
    -----------------
    - unit: Unit,                       登録した単元

    """
    # 単元を登録
    unit = Unit(
        course_id=course_id,
        position=position,
        title=parsed.title,
        summary=parsed.summary,
        goals=parsed.goals,
        estimated_minutes=minutes,
    )
    session.add(unit)
    session.flush()
    exercise_no = 0
    # セルを順に登録
    for cell_pos, (cell_type, source, ex) in enumerate(parsed.cells, start=1):
        problem_id = None
        # 演習セルの場合は問題を登録する
        if ex is not None:
            exercise_no += 1
            problem = _code_problem(
                course_id, unit.id, ProblemKind.EXERCISE, exercise_no, ex.title or f"演習 {position}-{exercise_no}", ex
            )
            session.add(problem)
            session.flush()
            problem_id = problem.id
        session.add(Cell(unit_id=unit.id, position=cell_pos, cell_type=cell_type, source=source, problem_id=problem_id))
    session.flush()
    # 登録した単元を返却
    return unit


def import_course(
    session: Session,
    course_dir: Path,
    author: User | None = None,
    replace: bool = False,
    force_status: str | None = None,
) -> Course:
    """
    講座フォルダを読み込んで講座を登録する

    Args
    -----------------
    - session: Session,                 DB セッション
    - course_dir: Path,                 講座フォルダ
    - author: User | None,              作成者として記録するユーザ
    - replace: bool,                    同じ識別名の講座があれば置き換えるなら True
    - force_status: str | None,         course.json の status の代わりに使う公開状態(画面からの取り込みは下書き)

    Returns
    -----------------
    - course: Course,                   登録した講座

    """
    # course.json を読み込む
    meta_path = course_dir / "course.json"
    if not meta_path.exists():
        raise NotebookFormatError(f"{course_dir}: course.json がありません")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    slug = meta["slug"]
    # 値の妥当性を確認
    if meta.get("level", CourseLevel.BASIC) not in CourseLevel.ALL:
        raise NotebookFormatError(f"level は {CourseLevel.ALL} のいずれかを指定してください")
    if meta.get("status", CourseStatus.DRAFT) not in CourseStatus.ALL:
        raise NotebookFormatError(f"status は {CourseStatus.ALL} のいずれかを指定してください")
    if not meta.get("quiz"):
        raise NotebookFormatError("course.json に小テストのノートブック(quiz)を指定してください")
    # 単元と小テストのノートブックをすべて解析(DB に書く前に書き方の誤りを検出する)
    parsed_units = []
    for entry in meta["units"]:
        parsed_units.append((parse_notebook(course_dir / entry["file"]), int(entry.get("minutes", 20))))
    questions = parse_quiz(course_dir / meta["quiz"])
    for no, q in enumerate(questions, start=1):
        if q.unit_position is not None and not 1 <= q.unit_position <= len(parsed_units):
            raise NotebookFormatError(f"小テスト 問{no} の unit が単元の範囲外です")
    # 同じ識別名の講座がある場合
    existing = session.scalar(select(Course).where(Course.slug == slug))
    if existing is not None:
        if not replace:
            raise NotebookFormatError(f"講座 '{slug}' は既に登録されています(置き換える場合は --replace)")
        # 置き換え指定なら既存講座を削除(受講記録も連動して削除される)
        session.delete(existing)
        session.flush()
    # 講座を登録
    status = force_status or meta.get("status", CourseStatus.DRAFT)
    course = Course(
        slug=slug,
        title=meta["title"],
        summary=meta.get("summary", ""),
        level=meta.get("level", CourseLevel.BASIC),
        tags=meta.get("tags", []),
        outcomes=meta.get("outcomes", []),
        libraries=meta.get("libraries", []),
        status=status,
        author_id=author.id if author else None,
        published_at=datetime.now() if status == CourseStatus.PUBLISHED else None,
    )
    session.add(course)
    session.flush()
    # 前提講座を登録(未登録の講座は無視せずエラーにする)
    for pre_slug in meta.get("prerequisites", []):
        pre = session.scalar(select(Course).where(Course.slug == pre_slug))
        if pre is None:
            raise NotebookFormatError(f"前提講座 '{pre_slug}' が登録されていません")
        session.add(CoursePrerequisite(course_id=course.id, prerequisite_id=pre.id))
    # 単元・セル・演習を登録
    unit_ids: list[int] = []
    for position, (parsed, minutes) in enumerate(parsed_units, start=1):
        unit_ids.append(add_parsed_unit(session, course.id, parsed, position, minutes).id)
    # 小テストの問題を登録
    for no, q in enumerate(questions, start=1):
        related = unit_ids[q.unit_position - 1] if q.unit_position else None
        if q.code is not None:
            problem = _code_problem(course.id, None, ProblemKind.QUIZ, no, q.code.title or f"問{no}", q.code)
        else:
            problem = Problem(
                course_id=course.id,
                unit_id=None,
                kind=ProblemKind.QUIZ,
                position=no,
                answer_format=q.answer_format,
                title=f"問{no}",
                prompt=q.prompt,
                choices=q.choices,
                correct_answer=q.correct_answer,
                tolerance=q.tolerance,
                explanation=q.explanation,
                verify_status=VerifyStatus.VERIFIED,
            )
        problem.related_unit_id = related
        session.add(problem)
    # データファイルを登録
    data_dir = course_dir / "data"
    if data_dir.is_dir():
        for file in sorted(data_dir.iterdir()):
            if file.is_file():
                session.add(
                    Dataset(
                        course_id=course.id,
                        filename=file.name,
                        content_type=mimetypes.guess_type(file.name)[0] or "application/octet-stream",
                        content=file.read_bytes(),
                    )
                )
    session.flush()
    # 登録した講座を返却
    return course
