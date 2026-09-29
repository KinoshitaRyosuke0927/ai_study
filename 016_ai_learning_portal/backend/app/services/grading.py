"""出力一致による採点処理。

ブラウザ(Pyodide)で実行したコードの出力を、想定出力と比較する。
数値は許容誤差内なら一致とみなし、数値の桁数による空白のずれは無視する。
"""

from __future__ import annotations

import math
import re

# 数値(整数・小数・指数表記・nan・inf)にマッチする正規表現
_NUMBER = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?|[-+]?(?:nan|NaN|inf|Inf)")


def normalize_output(text: str) -> str:
    """
    出力文字列を比較用に正規化する

    Args
    -----------------
    - text: str,                        出力文字列

    Returns
    -----------------
    - normalized: str,                  改行コード統一・行末空白と末尾空行を除いた文字列

    """
    # 改行コードを LF に統一
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # 各行の行末空白を除去し、末尾の空行を取り除いて返却
    return "\n".join(line.rstrip() for line in text.split("\n")).strip("\n")


def _split_numbers(text: str) -> tuple[list[str], list[float]]:
    """
    文字列を「数値以外の部分」と「数値」に分解する

    Args
    -----------------
    - text: str,                        正規化済みの出力文字列

    Returns
    -----------------
    - texts: list[str],                 数値以外の部分(空白の連続は1つにまとめる)
    - numbers: list[float],             出現順の数値

    """
    # 入れ物用意
    texts: list[str] = []
    numbers: list[float] = []
    last = 0
    # 数値の出現ごとに、その手前の文字列と数値を取り出す
    for match in _NUMBER.finditer(text):
        texts.append(re.sub(r"[ \t]+", " ", text[last : match.start()]))
        numbers.append(float(match.group()))
        last = match.end()
    # 最後の数値以降の文字列を追加
    texts.append(re.sub(r"[ \t]+", " ", text[last:]))
    # 分解結果を返却
    return texts, numbers


def outputs_match(expected: str, actual: str, tolerance: float = 1e-6) -> bool:
    """
    想定出力と実際の出力が一致するか判定する

    Args
    -----------------
    - expected: str,                    想定出力
    - actual: str,                      受講者のコードの出力
    - tolerance: float,                 数値比較の許容誤差(相対・絶対の両方に適用)

    Returns
    -----------------
    - matched: bool,                    一致すれば True

    """
    # 正規化して完全一致すればその時点で一致
    expected_n = normalize_output(expected)
    actual_n = normalize_output(actual)
    if expected_n == actual_n:
        return True
    # 数値とそれ以外に分解
    exp_texts, exp_numbers = _split_numbers(expected_n)
    act_texts, act_numbers = _split_numbers(actual_n)
    # 数値以外の部分が異なる、または数値の個数が異なる場合は不一致
    if exp_texts != act_texts or len(exp_numbers) != len(act_numbers):
        return False
    # 数値を1つずつ許容誤差で比較
    for exp, act in zip(exp_numbers, act_numbers):
        # 両方 nan なら一致とみなす
        if math.isnan(exp) and math.isnan(act):
            continue
        # 許容誤差を超えたら不一致
        if not math.isclose(exp, act, rel_tol=tolerance, abs_tol=tolerance):
            return False
    # すべての数値が許容誤差内なら一致
    return True
