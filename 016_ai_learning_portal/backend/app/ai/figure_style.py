"""講座の図(説明・問題文に載せる画像)の共通スタイル。

手本講座(content/stats2-descriptive)の図のデザインを基準にしている(ユーザ決定 2026-10-25)。
図はブラウザ内と同じ Pyodide の matplotlib で描くため、スタイルは Python のコード(FIGURE_STYLE_CODE)として持ち、
図を描くコードの前に実行する。AI に図を作らせるときは、FIGURE_STYLE_GUIDE をプロンプトに含めて描き方をそろえる。

手本講座の図を作るスクリプトも、このファイルの FIGURE_STYLE_CODE を読み込んで使う。
受講者がコードで描くグラフにも同じスタイルを適用するため、同じ設定を matplotlibrc(MATPLOTLIBRC)にして
/api/config でブラウザに渡し、ブラウザ内の Python の起動時に置く。
デザインを変えるときは、このファイルだけを直し、既存の図を作り直す。
"""

from __future__ import annotations

# 基本色(柱・折れ線)と、強調色(注目させたい線・注釈)
PRIMARY = "#3b7f86"
ACCENT = "#c0603a"
# カテゴリを塗り分けるときの色(濃い順。円グラフ・積み上げ棒など)
CATEGORY_COLORS = ["#3b7f86", "#6aa3a8", "#9cc4c6", "#c9dfe0", "#e6efef"]
# 2系列以上を線・点で描き分けるときの色(基本色 → 強調色 → 補助色)
SERIES_COLORS = ["#3b7f86", "#c0603a", "#7a6fa8", "#8a9a3b", "#5b5b5b"]

# matplotlib の設定(matplotlibrc の書き方。色は先頭の # を付けない)
FIGURE_RC = {
    "figure.dpi": "100",
    "savefig.dpi": "100",
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.prop_cycle": "cycler('color', [{}])".format(", ".join(f"'{c[1:]}'" for c in SERIES_COLORS)),
    "axes.titlesize": "12",
    "axes.labelsize": "10",
    "xtick.labelsize": "9",
    "ytick.labelsize": "9",
    "legend.fontsize": "9",
    "legend.frameon": "False",
    # ヒストグラム・棒グラフの柱は白い枠線で区切る
    "patch.force_edgecolor": "True",
    "patch.edgecolor": "white",
    "hist.bins": "10",
}

# ブラウザ内の Python に置く matplotlibrc(受講者のコードで描くグラフにも同じスタイルを適用する)
MATPLOTLIBRC = "\n".join(f"{key}: {value}" for key, value in FIGURE_RC.items()) + "\n"

# 図を描くコードの前に実行する設定(matplotlib の rcParams と、よく使う色の変数)
FIGURE_STYLE_CODE = f'''
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PRIMARY = "{PRIMARY}"
ACCENT = "{ACCENT}"
CATEGORY_COLORS = {CATEGORY_COLORS!r}
SERIES_COLORS = {SERIES_COLORS!r}

for _key, _value in {FIGURE_RC!r}.items():
    plt.rcParams[_key] = _value
'''

# AI に図を作らせるときにプロンプトに含める描き方の指示
FIGURE_STYLE_GUIDE = f"""\
- 図は matplotlib で描く。色・線などの共通設定は事前に適用済みなので、rcParams やスタイルを変更しない。
- 柱・折れ線の基本色は PRIMARY({PRIMARY})、注目させたい線や注釈は ACCENT({ACCENT})を使う(変数として使える)。
  カテゴリの塗り分けは CATEGORY_COLORS、複数系列の描き分けは SERIES_COLORS を使う。
- 図の中の文字(タイトル・軸ラベル・凡例・注釈)はすべて英語にする(日本語フォントが無いため)。
  日本語の説明は図の前後の本文に書く。
- 比べたい図は plt.subplots で横に並べる(2〜5 枚。横幅は 10〜14 インチ、高さは 2.6〜4 インチ)。
  比べる図どうしは、必要に応じて軸の範囲をそろえる(sharey など)。
- ヒストグラムは柱の間をあけない。階級の境界が分かるよう目盛りを階級の区切りに合わせる。
- 読み取らせたい値には、補助線(点線・破線)と短い注釈(例: "about 52")を付ける。
  柱に重ねる線は柱と違う色(ACCENT・濃い灰色 #333333 など)にし、zorder=3 で柱より手前に描く。
- 問題に使う図では、答えが図から直接わかる注釈や数値を入れない。
- 最後に fig.tight_layout() を呼んでから、指定されたファイル名で fig.savefig() する。"""
