"""ノートブック取り込みのテスト。"""

from pathlib import Path

import nbformat
import pytest

from app.common.constants import CellType, Grading
from app.services.notebook_import import NotebookFormatError, parse_notebook
from tests.conftest import SAMPLE_COURSE


def test_parse_sample_unit():
    # サンプル講座の単元3を解析
    unit = parse_notebook(SAMPLE_COURSE / "03_central_tendency.ipynb")
    # タイトル・概要・学習目標が取り出されている
    assert unit.title == "代表値：平均・中央値・最頻値"
    assert unit.summary.startswith("3つの代表値")
    assert len(unit.goals) == 3
    # 演習が1問あり、問題文・初期コード・想定出力が入っている
    exercises = [ex for t, _, ex in unit.cells if t == CellType.EXERCISE]
    assert len(exercises) == 1
    ex = exercises[0]
    assert "300点" in ex.prompt
    assert "____" in ex.starter_code
    assert ex.expected_output == "平均: 100.89\n中央値: 75.0"
    assert ex.hint and ex.explanation


def test_parse_test_graded_exercise():
    # 単元4の2問目はテストコード採点
    unit = parse_notebook(SAMPLE_COURSE / "04_dispersion.ipynb")
    exercises = [ex for t, _, ex in unit.cells if t == CellType.EXERCISE]
    assert [ex.grading for ex in exercises] == [Grading.OUTPUT, Grading.TEST]
    assert "assert" in exercises[1].test_code


def _write_nb(tmp_path: Path, cells) -> Path:
    """テスト用のノートブックを書き出す。"""
    nb = nbformat.v4.new_notebook()
    nb.cells = cells
    path = tmp_path / "unit.ipynb"
    nbformat.write(nb, str(path))
    return path


def test_unit_without_exercise_is_rejected(tmp_path):
    # 演習のない単元は取り込めない
    path = _write_nb(tmp_path, [nbformat.v4.new_markdown_cell("# タイトル"), nbformat.v4.new_code_cell("x = 1")])
    with pytest.raises(NotebookFormatError, match="演習が1問以上"):
        parse_notebook(path)


def test_solution_without_output_is_rejected(tmp_path):
    # 出力一致の演習で、解答セルが未実行(出力なし)の場合は取り込めない
    path = _write_nb(
        tmp_path,
        [
            nbformat.v4.new_markdown_cell("# タイトル"),
            nbformat.v4.new_markdown_cell("問題文"),
            nbformat.v4.new_code_cell("# @starter\nprint(____)"),
            nbformat.v4.new_code_cell("# @solution\nprint(1)"),
        ],
    )
    with pytest.raises(NotebookFormatError, match="出力がありません"):
        parse_notebook(path)
