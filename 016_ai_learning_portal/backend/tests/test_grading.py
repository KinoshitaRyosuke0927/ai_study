"""出力一致の採点ロジックのテスト。"""

from app.services.grading import outputs_match


def test_exact_match_ignores_trailing_whitespace():
    # 行末空白・末尾の改行・改行コードの違いは無視する
    assert outputs_match("平均: 100.89\n中央値: 75.0\n", "平均: 100.89  \r\n中央値: 75.0")


def test_numbers_within_tolerance():
    # 許容誤差内の数値の違いは一致とみなす
    assert outputs_match("0.3333333333", "0.33333333331", tolerance=1e-6)
    assert not outputs_match("0.33", "0.34", tolerance=1e-6)


def test_number_width_alignment_is_ignored():
    # 数値の桁数による列揃えの空白のずれは無視する
    assert outputs_match("a    1.0\nb   10.0", "a  1.000\nb  10.000")


def test_text_difference_fails():
    # 数値以外の文字が違えば不一致
    assert not outputs_match("平均: 100.89", "中央値: 100.89")
    # 数値の個数が違えば不一致
    assert not outputs_match("1 2 3", "1 2")


def test_nan_matches_nan():
    # nan どうしは一致とみなす
    assert outputs_match("0    NaN\n1    2.0", "0    NaN\n1    2.0")
