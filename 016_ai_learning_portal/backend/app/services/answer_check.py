"""選択式・数値入力・表形式の選択の、正解の確認と採点を扱うモジュール(演習・小テスト共通)。

表形式の選択は、行(分類する項目)ごとに、列の選択肢から1つを選ぶ問題。
正解と受講者の回答は、行の順に選んだ選択肢の文言を並べた JSON 配列の文字列で表す。
    例) 行 = ["region", "members"]、選択肢 = ["名義", "離散"] のとき、正解 '["名義", "離散"]'
"""

from __future__ import annotations

import json
import math
import unicodedata

from app.common.constants import AnswerFormat
from app.models import Problem


def parse_matrix_answer(text: str) -> list[str] | None:
    """
    表形式の選択の回答(JSON 配列の文字列)を読み取る

    Args
    -----------------
    - text: str,                        回答・正解の文字列

    Returns
    -----------------
    - values: list[str] | None,         行ごとに選んだ選択肢(読み取れなければ None)

    """
    # JSON として読めない場合は None
    try:
        values = json.loads(text)
    except (TypeError, ValueError):
        return None
    # 文字列(未選択は空文字)の配列でなければ None
    if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
        return None
    return values


def answer_key_error(answer_format: str, choices: list[str], rows: list[str], correct_answer: str) -> str | None:
    """
    選択式・数値入力・表形式の選択の正解が正しく設定されているかを確認する

    Args
    -----------------
    - answer_format: str,               回答形式
    - choices: list[str],               選択肢(表形式は列)
    - rows: list[str],                  表形式の行
    - correct_answer: str,              正解

    Returns
    -----------------
    - error: str | None,                誤りの内容(正しければ None)

    """
    # 選択式: 選択肢が2つ以上あり、正解が選択肢の1つであること
    if answer_format == AnswerFormat.CHOICE:
        if len(choices) < 2 or correct_answer not in choices:
            return "選択肢を2つ以上用意し、正解を選んでください"
        return None
    # 数値入力: 正解が有限の数値であること
    if answer_format == AnswerFormat.NUMERIC:
        try:
            if math.isfinite(float(correct_answer)):
                return None
        except ValueError:
            pass
        return "正解の数値を入力してください"
    # 表形式: 行が1つ以上・選択肢が2つ以上あり、すべての行の正解が選択肢の1つであること
    if answer_format == AnswerFormat.MATRIX:
        if not rows or len(choices) < 2:
            return "行を1つ以上、選択肢を2つ以上用意してください"
        values = parse_matrix_answer(correct_answer)
        if values is None or len(values) != len(rows) or any(v not in choices for v in values):
            return "すべての行について正解を選んでください"
        return None
    # コード問題は対象外
    return None


def _normalize(text: str) -> str:
    """
    回答文字列を比較用に正規化する(全角英数字を半角に、前後の空白を除去)

    Args
    -----------------
    - text: str,                        回答

    Returns
    -----------------
    - normalized: str,                  正規化した回答

    """
    # NFKC で全角・半角を揃えて前後の空白を除いて返却
    return unicodedata.normalize("NFKC", text).strip()


def grade_answer(problem: Problem, answer: str) -> tuple[bool, bool, str]:
    """
    選択式・数値入力・表形式の選択の回答を採点する

    Args
    -----------------
    - problem: Problem,                 問題
    - answer: str,                      回答(選択肢の文言・数値・表形式は JSON 配列の文字列)

    Returns
    -----------------
    - correct: bool,                    正解なら True
    - answered: bool,                   回答があれば True
    - message: str,                     受講者に表示するメッセージ

    """
    # 未回答は不正解
    if not answer.strip():
        return False, False, "未回答です。"
    # 選択式: 選択肢の文言が正解と一致するか
    if problem.answer_format == AnswerFormat.CHOICE:
        ok = answer == problem.correct_answer
        return ok, True, "正解です。" if ok else "不正解です。"
    # 数値入力: 許容誤差内で一致するか
    if problem.answer_format == AnswerFormat.NUMERIC:
        try:
            value = float(_normalize(answer).replace(",", ""))
        except ValueError:
            return False, True, "数値として読み取れませんでした。"
        expected = float(problem.correct_answer)
        ok = math.isfinite(value) and math.isclose(
            value, expected, rel_tol=problem.tolerance, abs_tol=problem.tolerance
        )
        return ok, True, "正解です。" if ok else "不正解です。"
    # 表形式: すべての行が正解と一致するか(正解した行の数も伝える)
    if problem.answer_format == AnswerFormat.MATRIX:
        expected_rows = parse_matrix_answer(problem.correct_answer) or []
        values = parse_matrix_answer(answer)
        if values is None or len(values) != len(expected_rows):
            return False, True, "回答の形式が正しくありません。"
        if not any(values):
            return False, False, "未回答です。"
        if any(not v for v in values):
            return False, True, "まだ選んでいない行があります。"
        hits = sum(1 for v, e in zip(values, expected_rows) if v == e)
        if hits == len(expected_rows):
            return True, True, "正解です。"
        return False, True, f"不正解です({len(expected_rows)} 行中 {hits} 行が正解)。"
    # それ以外(コード問題)はここでは採点しない
    raise ValueError(f"answer_format '{problem.answer_format}' はこの関数では採点できません")
