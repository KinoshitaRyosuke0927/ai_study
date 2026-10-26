"""AI が作った単元・小テストの下書きを実行して確かめるモジュール。

実行するもの:
- 例題(code セル): 受講画面と同じく、単元の中で上から順に同じ名前空間で実行する
- 図(figure セル・問題の figure_code): 共通スタイル(FIGURE_STYLE_CODE)を適用して単独で実行し、画像を得る
- コードの演習の模範解答(と、テストコード採点ならテスト): 単独で実行する(受講者が例題を実行していなくても動くこと)
- 選択式・数値入力・表形式の正解の根拠(check_code): 単独で実行する

結果から、AI に見せる「実行結果の報告」と、必ず直すべき「問題点」(エラー・図が描けない・数値の正解の不一致など)を作る。
"""

from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass, field

from app.ai.executor import CodeRunner, Task, TaskResult
from app.ai.figure_style import FIGURE_STYLE_CODE
from app.ai.schemas import GeneratedExercise, GeneratedQuestion, QuizDraft, UnitDraft

# 報告に載せる出力の長さの上限(1つあたり)
_MAX_OUTPUT = 1500
# 数値を取り出す正規表現(check_code の出力の最後の数値を正解と比べる)
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
# 本文に直接書かれた画像の参照(図は figure セル・figure_code で描くので、本文の ![...](...) は表示できない)
_STRAY_IMAGE = re.compile(r"!\[[^\]]*\]\((?!image:)[^)]*\)")


def strip_stray_images(text: str) -> str:
    """
    本文に直接書かれた画像の参照(表示できない)を取り除く

    Args
    -----------------
    - text: str,                        Markdown の本文

    Returns
    -----------------
    - text: str,                        画像の参照を取り除いた本文

    """
    # 参照を消し、空になった行も詰めて返却
    return re.sub(r"\n{3,}", "\n\n", _STRAY_IMAGE.sub("", text)).strip()


def _stray_image_issue(label: str, *texts: str) -> list[str]:
    """
    本文に画像の参照が直接書かれていれば、問題点にする

    Args
    -----------------
    - label: str,                       セル・問題の呼び名
    - texts: str,                       調べる本文(説明・問題文・解説など)

    Returns
    -----------------
    - issues: list[str],                問題点(無ければ空)

    """
    # 見つかった参照を問題点として返却
    found = [m for t in texts for m in _STRAY_IMAGE.findall(t)]
    if not found:
        return []
    return [f"{label}: 本文に画像の参照 {found[0]} が書かれていますが、表示できません。図は figure セル(問題文の図は figure_code)で描き、本文からは削除してください"]


@dataclass
class Execution:
    """下書きを実行した結果。"""

    results: dict[str, TaskResult] = field(default_factory=dict)  # タスクの ID → 実行結果
    issues: list[str] = field(default_factory=list)  # 必ず直すべき問題点
    report: str = ""  # AI に見せる実行結果の報告

    def image(self, task_id: str) -> str | None:
        """
        図のタスクで描かれた画像(PNG, base64)を返す

        Args
        -----------------
        - task_id: str,                     タスクの ID

        Returns
        -----------------
        - image: str | None,                最初の画像(描かれなければ None)

        """
        # 画像があれば最初の1枚を返却
        result = self.results.get(task_id)
        return result.images[0] if result and result.images else None


def _clip(text: str) -> str:
    """
    報告に載せる出力を、長すぎれば切り詰める

    Args
    -----------------
    - text: str,                        出力

    Returns
    -----------------
    - text: str,                        切り詰めた出力

    """
    # 上限を超えたら末尾を省略して返却
    text = text.rstrip()
    return text if len(text) <= _MAX_OUTPUT else text[:_MAX_OUTPUT] + "\n…(省略)"


# 見た目だけに関わる引数・メソッド(値が問題文に無くても出力は変わらない)
_COSMETIC_ARGS = {"figsize", "color", "colors", "alpha", "linewidth", "lw", "fontsize", "rotation", "dpi", "marker", "markersize", "s", "edgecolor", "width", "label", "title"}
_COSMETIC_CALLS = {"subplots", "figure", "plot", "bar", "barh", "hist", "scatter", "boxplot", "legend", "text", "annotate", "axhline", "axvline", "tight_layout"}


def _number_set(text: str) -> set[float]:
    """
    文章に書かれた数値を集める

    Args
    -----------------
    - text: str,                        文章

    Returns
    -----------------
    - numbers: set[float],              数値(符号は除く)

    """
    # 数値を取り出して、絶対値で返却
    return {abs(float(n)) for n in _NUMBER.findall(text)}


def _unstated_values(q: GeneratedExercise | GeneratedQuestion) -> list[str]:
    """
    コードの問題で、模範解答が使っているのに問題文・初期コード・ヒントに書かれていない値を探す
    (区間の境界・区間名・表示の文言など。書かれていないと、受講者は出力を一つに決められない)

    Args
    -----------------
    - q: GeneratedExercise | GeneratedQuestion,  コードの問題

    Returns
    -----------------
    - values: list[str],                書かれていない値(見つかった順)

    """
    try:
        tree = ast.parse(q.model_answer)
    except SyntaxError:
        return []
    stated = f"{q.prompt}\n{q.starter_code}\n{getattr(q, 'hint', '')}"
    numbers = _number_set(stated)
    # パーセントで答える問題の 100 は書かれているものとみなす
    if any(w in stated for w in ("%", "%", "パーセント", "百分率")):
        numbers.add(100.0)
    found: list[str] = []

    def add(value: str) -> None:
        if value not in found:
            found.append(value)

    def visit(node: ast.AST, cosmetic: bool, in_list: bool, in_print: bool) -> None:
        # 見た目だけの引数・メソッドの中は調べない
        if isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            cosmetic = cosmetic or name in _COSMETIC_CALLS or name.startswith("set_")
            in_print = in_print or name == "print"
            for arg in node.args:
                visit(arg, cosmetic, False, in_print)
            for kw in node.keywords:
                visit(kw.value, cosmetic or kw.arg in _COSMETIC_ARGS, False, in_print)
            visit(node.func, cosmetic, False, False)
            return
        if isinstance(node, ast.Constant) and not cosmetic:
            value = node.value
            # 数値: 0 と 1 以外で、問題文などに無いもの
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if abs(value) not in (0, 1) and abs(float(value)) not in numbers:
                    add(repr(value))
            # 文字列: リストの要素(区間名など)と print する文言で、問題文などに無いもの
            elif isinstance(value, str) and (in_list or in_print):
                text = value.strip(" :=\n")
                if text and text not in stated:
                    add(repr(value))
            return
        for child in ast.iter_child_nodes(node):
            visit(child, cosmetic, isinstance(node, (ast.List, ast.Tuple)), in_print)

    visit(tree, False, False, False)
    return found


def _figure_task(task_id: str, code: str) -> Task:
    """
    図を描くタスクを作る(共通スタイルを適用してから実行する)

    Args
    -----------------
    - task_id: str,                     タスクの ID
    - code: str,                        図を描くコード

    Returns
    -----------------
    - task: Task,                       タスク

    """
    # 共通スタイルの設定を前に付けて、単独の名前空間で実行する
    return Task(id=task_id, code=f"{FIGURE_STYLE_CODE}\n{code}", ctx=task_id)


def _problem_tasks(prefix: str, q: GeneratedExercise | GeneratedQuestion) -> list[Task]:
    """
    演習・小テストの問題1つ分のタスクを作る

    Args
    -----------------
    - prefix: str,                      タスクの ID の先頭(問題ごとに一意)
    - q: GeneratedExercise | GeneratedQuestion,  問題

    Returns
    -----------------
    - tasks: list[Task],                タスク(模範解答 or 正解の根拠、図)

    """
    tasks: list[Task] = []
    # コード: 模範解答を単独で実行する(テストコード採点ならテストも)
    if q.type == "code":
        test = q.test_code if q.grading == "test" else ""
        tasks.append(Task(id=f"{prefix}.answer", code=q.model_answer, ctx=f"{prefix}.answer", test=test))
    # 選択式・数値入力・表形式: 正解の根拠のコードを単独で実行する
    elif q.check_code.strip():
        tasks.append(Task(id=f"{prefix}.check", code=q.check_code, ctx=f"{prefix}.check"))
    # 問題文の図
    if q.figure_code.strip():
        tasks.append(_figure_task(f"{prefix}.figure", q.figure_code))
    return tasks


def _check_problem(prefix: str, label: str, q: GeneratedExercise | GeneratedQuestion, results: dict[str, TaskResult]) -> tuple[list[str], list[str]]:
    """
    問題1つ分の実行結果から、報告の行と問題点を作る

    Args
    -----------------
    - prefix: str,                      タスクの ID の先頭
    - label: str,                       問題の呼び名(「演習2」など)
    - q: GeneratedExercise | GeneratedQuestion,  問題
    - results: dict[str, TaskResult],   実行結果

    Returns
    -----------------
    - lines: list[str],                 報告の行
    - issues: list[str],                問題点

    """
    lines: list[str] = []
    issues: list[str] = _stray_image_issue(label, q.prompt, q.explanation, getattr(q, "hint", ""))
    # コード: 模範解答の出力・エラー・テストの結果
    if q.type == "code":
        r = results.get(f"{prefix}.answer")
        if r is not None:
            lines.append(f"### {label}(コード)の model_answer の実行結果\n{_clip(r.output) or '(出力なし)'}")
            if r.error:
                issues.append(f"{label}: model_answer の実行でエラーが出ました: {r.error}")
            elif not r.output.strip() and q.grading == "output":
                issues.append(f"{label}: model_answer が何も出力していません(答えを print してください)")
            if r.test_passed is False:
                issues.append(f"{label}: model_answer がテストに合格しません: {r.test_message}")
        # 答えを一つに決めるのに必要な値が、問題文などに書かれていること
        unstated = _unstated_values(q)
        if unstated:
            issues.append(
                f"{label}: model_answer の値 {', '.join(unstated[:6])} が問題文・starter_code・hint に書かれていないため、"
                "受講者は出力を一つに決められません。必要な値を問題文か starter_code に書いてください"
                "(答えに関係しない値なら、model_answer をその値を使わない書き方に直してください)"
            )
    # 選択式・数値入力・表形式: 正解の根拠の出力と、数値入力の正解との一致
    else:
        r = results.get(f"{prefix}.check")
        if r is None:
            issues.append(f"{label}: 正解の根拠を計算する check_code がありません")
        else:
            lines.append(f"### {label}({q.type})の check_code の実行結果(answer: {q.answer or q.matrix_answers})\n{_clip(r.output) or '(出力なし)'}")
            if r.error:
                issues.append(f"{label}: check_code の実行でエラーが出ました: {r.error}")
            elif q.type == "numeric":
                numbers = _NUMBER.findall(r.output)
                try:
                    expected = float(q.answer)
                    actual = float(numbers[-1]) if numbers else math.nan
                except ValueError:
                    expected, actual = math.nan, math.nan
                tol = max(q.tolerance, 1e-6)
                if not (math.isfinite(actual) and abs(actual - expected) <= tol + 1e-9 * abs(expected)):
                    issues.append(
                        f"{label}: answer({q.answer})が check_code の計算結果(最後に出力された数値: {numbers[-1] if numbers else 'なし'})と"
                        f"許容誤差 {tol} の範囲で一致しません"
                    )
    # 問題文の図
    if q.figure_code.strip():
        r = results.get(f"{prefix}.figure")
        if r is None or r.error or not r.images:
            issues.append(f"{label}: figure_code で図が描けませんでした: {r.error if r else ''}")
    return lines, issues


def run_unit(runner: CodeRunner, draft: UnitDraft, files: dict[str, bytes]) -> Execution:
    """
    単元の下書きを実行して確かめる

    Args
    -----------------
    - runner: CodeRunner,               実行環境
    - draft: UnitDraft,                 単元の下書き
    - files: dict[str, bytes],          講座のデータファイル

    Returns
    -----------------
    - execution: Execution,             実行結果・報告・問題点

    """
    # セルの種類ごとにタスクを作る(例題は同じ名前空間で順に、それ以外は単独で)
    tasks: list[Task] = []
    exercise_no = 0
    for i, cell in enumerate(draft.cells, start=1):
        if cell.type == "code" and cell.source.strip():
            tasks.append(Task(id=f"cell{i}", code=cell.source, ctx="unit"))
        elif cell.type == "figure" and cell.source.strip():
            tasks.append(_figure_task(f"cell{i}", cell.source))
        elif cell.type == "exercise" and cell.exercise is not None:
            exercise_no += 1
            tasks.extend(_problem_tasks(f"ex{exercise_no}", cell.exercise))
    results = runner.run(tasks, files) if tasks else {}
    # 結果から報告と問題点を作る
    lines: list[str] = []
    issues: list[str] = []
    exercise_no = 0
    for i, cell in enumerate(draft.cells, start=1):
        if cell.type == "markdown":
            issues.extend(_stray_image_issue(f"セル{i}(説明)", cell.source))
        elif cell.type == "code" and cell.source.strip():
            r = results.get(f"cell{i}")
            if r is not None:
                images = f"(図 {len(r.images)} 枚)" if r.images else ""
                lines.append(f"### セル{i}(例題)の実行結果{images}\n{_clip(r.output) or '(出力なし)'}")
                if r.error:
                    issues.append(f"セル{i}(例題): 実行でエラーが出ました: {r.error}")
        elif cell.type == "figure" and cell.source.strip():
            r = results.get(f"cell{i}")
            if r is None or r.error or not r.images:
                issues.append(f"セル{i}(図): 図が描けませんでした: {r.error if r else ''}")
            else:
                lines.append(f"### セル{i}(図): 描けました")
        elif cell.type == "exercise" and cell.exercise is not None:
            exercise_no += 1
            add_lines, add_issues = _check_problem(f"ex{exercise_no}", f"演習{exercise_no}(セル{i})", cell.exercise, results)
            lines.extend(add_lines)
            issues.extend(add_issues)
    # 同じコードを繰り返す例題(前の例題のコードをそのまま先頭に含む)
    codes = [(i, c.source.strip()) for i, c in enumerate(draft.cells, start=1) if c.type == "code" and c.source.strip()]
    for k, (i, src) in enumerate(codes):
        for j, later in codes[k + 1 :]:
            if later.startswith(src):
                issues.append(f"セル{j}(例題): セル{i}と同じコードを繰り返しています。同じ単元の例題では、前の例題で作った変数をそのまま使い、繰り返す部分は削除してください")
                break
    # 演習の図が説明の図と同じだと、説明から答えが読めてしまう
    explanation_images = {img for i, c in enumerate(draft.cells, start=1) if c.type == "figure" for img in results.get(f"cell{i}", TaskResult(id="")).images}
    for n in range(1, exercise_no + 1):
        r = results.get(f"ex{n}.figure")
        if r is not None and any(img in explanation_images for img in r.images):
            issues.append(f"演習{n}: 問題文の図が説明の図とまったく同じです。説明から答えが読めないよう、別のデータで図を描いてください")
    return Execution(results=results, issues=issues, report="\n\n".join(lines))


def run_quiz(runner: CodeRunner, quiz: QuizDraft, files: dict[str, bytes]) -> Execution:
    """
    小テストの下書きを実行して確かめる

    Args
    -----------------
    - runner: CodeRunner,               実行環境
    - quiz: QuizDraft,                  小テストの下書き
    - files: dict[str, bytes],          講座のデータファイル

    Returns
    -----------------
    - execution: Execution,             実行結果・報告・問題点

    """
    # 問題ごとにタスクを作って実行する
    tasks = [t for n, q in enumerate(quiz.questions, start=1) for t in _problem_tasks(f"q{n}", q)]
    results = runner.run(tasks, files) if tasks else {}
    # 結果から報告と問題点を作る
    lines: list[str] = []
    issues: list[str] = []
    for n, q in enumerate(quiz.questions, start=1):
        add_lines, add_issues = _check_problem(f"q{n}", f"問{n}", q, results)
        lines.extend(add_lines)
        issues.extend(add_issues)
    return Execution(results=results, issues=issues, report="\n\n".join(lines))
