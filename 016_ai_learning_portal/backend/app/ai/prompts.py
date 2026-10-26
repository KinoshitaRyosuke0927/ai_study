"""講座下書き生成のプロンプト。

精度改善はこのファイルを中心に行う。プロンプトを変えたら PROMPT_VERSION を上げること
(AI 呼び出しの記録 ai_generations に版番号が残り、どの版で作った下書きかを追える)。

講座のタイプ(OutlineRequest.course_type)ごとに作り方が大きく違うため、方針と見本をタイプ別に持つ。
- concept(概念理解型): コードを書かない。図表・文章で説明し、演習は選択式・数値入力・表形式(試験形式)
- practice(実践型): 例題コードを実行して結果を読み取り、空欄を埋めるコードの演習と、結果の解釈の選択式で学ぶ
見本(exemplars/)は、手作業で作った手本講座(統計検定2級対策・タイタニックで学ぶデータ分析)の単元の原稿。
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from pydantic import BaseModel

from app.ai.figure_style import FIGURE_STYLE_GUIDE
from app.ai.schemas import CourseOutline, OutlineRequest, OutlineUnit, QuizDraft, UnitDraft

PROMPT_VERSION = "v6"

_LEVEL_LABEL = {"basic": "基礎", "intermediate": "応用", "advanced": "実践"}
_TYPE_LABEL = {"concept": "概念理解型(コードを書かない)", "practice": "実践型(コーディング中心)"}

# 見本の単元の原稿(手本講座からコピーしたもの)
_EXEMPLAR_DIR = Path(__file__).parent / "exemplars"

# 受講者のコードが動く環境(すべてのプロンプトで共通)
_ENVIRONMENT = """\
- 受講者のコードはブラウザ内の Python(Pyodide、Python 3.14)で実行される。
- 使えるライブラリ: pandas 3.0, numpy, matplotlib, scipy, scikit-learn, statsmodels, lightgbm(seaborn などその他は使わない)。
- インターネット接続・ファイルのダウンロード・外部 API の呼び出しはできない。
- データは、講座のデータファイル(あれば列挙する)を pd.read_csv("ファイル名") で読むか、
  コードの中で作る(乱数を使うときは np.random.default_rng(固定の seed) で毎回同じ値にする)。
- matplotlib の図は画像として表示される。日本語フォントが無いため、図の中の文字は英語にする。
  グラフの色・文字の大きさなどの共通スタイルは自動で適用されるので、スタイルは変更しない。"""

# 図の描き方(講座の図の共通スタイル。図はサーバで実行して画像にする)
_FIGURE_GUIDE = f"""- 図は、figure セル(説明に載せる図)または演習・問題の figure_code(問題文に載せる図)に、matplotlib で図を描く Python コードを書く。
  コードはサーバで実行され、描いた図(1つのコードで 1 枚)が画像として保存される。plt.savefig・plt.show は不要。
- 図を描くコードは単独で実行される。データは、講座のデータファイルを読むか、コードの中で作る(乱数は seed を固定)。
- 色の変数 PRIMARY・ACCENT・CATEGORY_COLORS・SERIES_COLORS と、共通スタイルの設定は、figure セル・figure_code のコードの前にだけ自動で用意される
  (受講者が実行する例題・演習のコードでは使わない。コードのコメントにも、こうしたアプリ側の仕組みのことは書かない)。
- 図は figure セル・figure_code だけで作る。説明・問題文・解説の本文に画像の Markdown(![...](...))を書かない(表示できない)。
{FIGURE_STYLE_GUIDE.replace("- 最後に fig.tight_layout() を呼んでから、指定されたファイル名で fig.savefig() する。", "- 最後に fig.tight_layout() を呼ぶ。")}"""

# 講座のタイプごとの作り方の方針(手本講座を作るときに決めたこと)
_TYPE_GUIDE = {
    "concept": """\
- 目的は、概念の理解と手計算の力を身につけること。Python のコードは説明にも演習にも載せない(参考コードも載せない)。
- 説明は、具体的な数値の例・表・数式($...$ / $$...$$)・図・文章で行う。計算の途中経過も示し、受講者が手で追えるようにする。
- 分布の形・グラフの読み取り・概念の違いなど、図で見るとわかりやすい内容には figure セルで図を入れる(1単元に 1〜3 枚程度)。
  グラフを読み取る問題には、問題の figure_code で図を付ける(答えが図から直接わかる注釈や色分けはしない)。
- 単元の内容にグラフ・図表の読み取り(ヒストグラム・箱ひげ図・散布図・時系列の折れ線など)が含まれるなら、
  その読み取りを問う演習を1問以上入れる(図は figure_code で、説明の図とは別のデータで描く)。
  図から値を読み取らせる場合は、その値が目盛りで正確に読めるようにする(値を目盛りの刻みに合わせる、目盛りを細かくする、
  または棒や点の横に値を書き込む)。figure_alt には図の内容だけを書き、答えや読み取る値そのものは書かない。
- 演習は試験形式にする。公式に値を1回代入するだけの問題ばかりにせず、半分以上は、表や図から値を読み取って計算する・
  2段階以上の計算をする・複数の記述の正誤を判断する、など試験で問われる形の問題にする。
- 問題文が参照する表・データ・図は、問題文の中(図は figure_code)に必ず含める(「次の表」と書いて表を載せ忘れない)。
  - choice(選択式): 概念の理解や、記述 I〜III の正誤の組み合わせ(「I と III のみ」など)を問う。誤りの選択肢は、よくある誤解・計算間違いから作る。
  - numeric(数値入力): 手計算できる数値で答えを求める。tolerance(許容誤差)を答えの桁に合わせて指定する。
  - matrix(表形式の選択): 複数の項目を、共通の選択肢から1つずつ選んで分類する(変数の種類の分類、用語と意味の対応など)。
- パーセント点(1.96、t 分布表の値など)など、計算に必要な分布表の値は問題文で与える。
- 図・表の読み取りは、具体的な値を挙げて書く(例:「B の中央値は 4 で A の 5 より小さく、四分位範囲は B が 3、A が 2」)。
  「比べてください」「確かめましょう」のような書き方だけで終わらせない。
- 解説の例と演習で、同じデータ・同じ数値・同じ図を使わない(解説から答えが読めてしまうため)。
- 統計ソフトの出力の読み取りを出題するときは、出力のすべての数値(t 値・自由度・p 値など)が互いに整合するようにする。
- 正解の数値は必ず計算して確かめる。choice / numeric / matrix の演習には、正解の根拠を計算して print する check_code を付ける
  (受講者には見せない。作成時の自動検証に使う。numeric は答えの数値、choice は正解の根拠となる値を print する)。""",
    "practice": """\
- 目的は、実際のデータ分析で使う技術を、コードを書きながら身につけること。
- 説明は「例題のコード → 実行結果の読み取り」の順に進める。読み取りでは、実行結果の具体的な数値を挙げて、何がわかるかを書く
  (例:「女性の生存率は 73%、男性は 19% で、大きな差があります」)。「違いがあるか確かめましょう」のような書き方だけで終わらせない。
  数値は、その例題を実行した結果と一致させる(作成後に実行して確かめ、食い違いは直す)。
- 例題(code セル)は、同じ単元の前の例題で作った変数を使ってよい(受講者は上から順に実行する)。単元の最初の例題で import とデータの読み込みを行う。
  同じ単元の中で、同じコード(import・データの読み込みなど)を繰り返す例題を作らない。
- 受講者は初学者を想定する。例題・初期コード・模範解答のコードには、各処理が何をしているかがわかる日本語のコメントを付ける
  (関数・引数の意味も添える。例: normalize=True は「件数ではなく割合にする」)。
- グラフは、受講者が実行する例題(code セル)の中で描く(描き方も学習内容のため)。概念を説明する図が必要なときだけ figure セルを使う。
- 演習はコード(type: code)を中心にし、結果の解釈・考え方を問う問題は choice にする。
  - starter_code は、必要な import とデータの読み込みから始まり、受講者が埋める部分を ____ にする。
    ____ ごとに「何を入れるか」をコメントで示す(答えそのものは書かない)。
  - model_answer は starter_code の ____ を埋めた完成コードで、単独で(例題を実行していなくても)動き、答えを print する。
  - 出力一致で採点するので、問題文(または starter_code)だけで出力が一つに決まるようにする。区間の境界と名前・しきい値・
    使う列・並び順・丸めの桁・出力の形式など、答えを決めるのに必要な値はすべて問題文に書く(「指定された区間」と書くなら、その指定を書く)。
  - 演習の出力は、列の少ない表・Series・数値にする(表示設定によって見た目が変わらないようにする)。小数は round で桁をそろえる。
  - 演習では、解説の例題と別の列・別の切り口を使う。前の単元の演習と同じ題材(同じ列・同じ派生変数の集計)も繰り返さない。
- 予測の時点で手に入らない情報(リーク)を使わない、学習用と予測用に同じ前処理をする、などデータ分析の注意点も、題材に合わせて説明する。
- 公開データを使う場合は、出典(利用条件で求められている表記)を単元の説明に書く。""",
}

# 小テストのタイプごとの方針
_QUIZ_GUIDE = {
    "concept": """\
- コードの問題は出さない。choice / numeric / matrix で出題する。
- 計算に必要な分布表の値は問題文で与える。単元の解説・演習と同じ数値は使わない。
- 単元の演習と同じく、記述 I〜III の正誤の組み合わせを問う choice や、図・表を読み取る問題(図は figure_code)も入れる。
- 問題文が参照する表・データ・図は、問題文の中(図は figure_code)に必ず含める。
- choice / numeric / matrix には、正解の根拠を計算して print する check_code を付ける(自動検証に使う)。""",
    "practice": """\
- code(コードを書く問題)と choice(考え方を問う問題)を半分ずつ程度にする。
- code の starter_code・model_answer には、初学者向けのコメントを付ける。model_answer は単独で動き、答えを print する。
- code は出力一致で採点するので、答えを決めるのに必要な値(区間・しきい値・出力の形式など)はすべて問題文か starter_code に書く。
- 単元の例題・演習と同じ設定・同じ列の組み合わせは使わない。""",
}


def _schema(model: type[BaseModel]) -> str:
    """
    出力の型を JSON スキーマ文字列にする(プロンプトに埋め込む)

    Args
    -----------------
    - model: type[BaseModel],           出力の型

    Returns
    -----------------
    - schema: str,                      JSON スキーマ

    """
    # 日本語をそのまま残して整形して返却
    return json.dumps(model.model_json_schema(), ensure_ascii=False)


@cache
def _exemplar(course_type: str) -> str:
    """
    講座のタイプに合った見本の単元の原稿を返す

    Args
    -----------------
    - course_type: str,                 講座のタイプ(concept / practice)

    Returns
    -----------------
    - text: str,                        見本の単元の原稿

    """
    # タイプごとのファイルを読んで返却
    return (_EXEMPLAR_DIR / f"{course_type}_unit.txt").read_text(encoding="utf-8")


# 見本の原稿の記法の説明(JSON の項目との対応)
_EXEMPLAR_NOTE = """\
見本は、次の記法で書いた単元の原稿です。出力は JSON で返すので、記法ではなく内容・粒度・書きぶりを参考にしてください。
- 「#%% md」の後が markdown セル、「#%% code」の後が code セル(例題)。
- 「<!-- @question ... -->」で始まる markdown セルは、選択式・数値入力・表形式の演習(exercise の type: choice / numeric / matrix)。
  本文の最後の箇条書きが choices、表形式は本文の最後の表の見出し行の2列目以降が choices・各行の1列目が matrix_rows。
- 「# @starter」「# @solution」のコードセルは、コードの演習(exercise の type: code)の starter_code と model_answer。
- 見本の図(![...](images/...))は、JSON では figure セル(図を描くコード)で作る。"""


def outline_prompt(req: OutlineRequest) -> tuple[str, str]:
    """
    構成案を作るプロンプトを組み立てる

    Args
    -----------------
    - req: OutlineRequest,              構成案の生成依頼

    Returns
    -----------------
    - system_prompt: str,               システムプロンプト
    - user_prompt: str,                 ユーザプロンプト

    """
    concept = req.course_type == "concept"
    # 役割と出力形式
    system = f"""あなたはデータサイエンスの社内講座を設計する講師です。
部署のメンバーが学ぶ講座の構成案を作ります。講座のタイプは「{_TYPE_LABEL[req.course_type]}」です。
次の JSON スキーマに従う JSON オブジェクトだけを返してください。

{_schema(CourseOutline)}

# 受講環境
{_ENVIRONMENT}

# この講座のタイプの作り方
{_TYPE_GUIDE[req.course_type]}

# 構成案の方針
- 講座の目的を達成できるように、単元を基本から応用へ無理なく進む順に並べる。1単元は 30〜45 分で学べる量にする。
- 各単元の summary は、その単元で学ぶことを 1〜2 文で書く。goals は「〜できる」の形で 3〜4 個。
- 各単元の演習は 3〜5 問(exercise_count)。小テストの問題数(quiz_count)は 10〜15。
- {'libraries は空にする(コードを書かない講座のため)。' if concept else 'libraries には、講座で使うライブラリを書く。'}
- outcomes(講座で身につくこと)は「〜できる」の形で 4〜6 個。
- 文章はすべて日本語。"""
    # 依頼内容
    user = f"""# 依頼
- 講座タイトル(仮): {req.title}
- 講座のタイプ: {_TYPE_LABEL[req.course_type]}
- レベル: {_LEVEL_LABEL[req.level]}
- 単元数の目安: {req.unit_count}
- 使用ライブラリ: {'なし(コードを書かない講座)' if concept else (', '.join(req.libraries) or '指定なし(pandas を中心に)')}
- 対象者・前提知識: {req.audience or '指定なし'}

# 講座の目的
{req.purpose or '指定なし'}

# 題材・扱いたい内容
{req.topic}

# 講座のデータファイル
{_data_text(req.data_summary)}"""
    return system, user


def _data_text(data_summary: str) -> str:
    """
    データファイルの要約を、プロンプトに渡す文章にする

    Args
    -----------------
    - data_summary: str,                データファイルの要約(列・型・欠損・先頭の行)

    Returns
    -----------------
    - text: str,                        プロンプトに入れる文章

    """
    # 要約が無ければ、データはコードの中で作るように伝える
    if not data_summary.strip():
        return "なし(データが必要な場合はコードの中で作る。実在のデータを装った架空のデータは作らない)"
    return f"次のファイルを pd.read_csv(\"ファイル名\") で読める。列名・型はこの要約のとおりに使う。\n{data_summary}"


def _outline_text(outline: CourseOutline) -> str:
    """
    構成案を、下書き生成のプロンプトに渡す文章にする

    Args
    -----------------
    - outline: CourseOutline,           講座の構成案

    Returns
    -----------------
    - text: str,                        構成案の説明文

    """
    # 単元ごとに1行ずつ並べる
    lines = [f"講座: {outline.title}", f"概要: {outline.summary}", "単元:"]
    for i, u in enumerate(outline.units, start=1):
        lines.append(f"  {i}. {u.title} — {u.summary}(目標: {' / '.join(u.goals)})")
    return "\n".join(lines)


def unit_prompt(
    outline: CourseOutline,
    index: int,
    level: str,
    datasets: list[str],
    course_type: str = "practice",
    purpose: str = "",
    data_summary: str = "",
    previous_exercises: list[str] | None = None,
) -> tuple[str, str]:
    """
    単元の下書き(説明・例題・演習のセル)を作るプロンプトを組み立てる

    Args
    -----------------
    - outline: CourseOutline,           講座の構成案
    - index: int,                       対象の単元の位置(0 始まり)
    - level: str,                       講座のレベル
    - datasets: list[str],              講座のデータファイル名
    - course_type: str,                 講座のタイプ(concept / practice)
    - purpose: str,                     講座の目的
    - data_summary: str,                データファイルの要約
    - previous_exercises: list[str] | None,  前の単元で作った演習(「単元N: タイトル」。同じ題材を繰り返さないため)

    Returns
    -----------------
    - system_prompt: str,               システムプロンプト
    - user_prompt: str,                 ユーザプロンプト

    """
    unit: OutlineUnit = outline.units[index]
    concept = course_type == "concept"
    # タイプごとのセルの並び
    if concept:
        cells_rule = f"""- 並び: 説明(markdown)を見出しごとに分けて続け、最後に「## 演習」の見出しの markdown と演習(exercise)を {unit.exercise_count} 問、最後に「## まとめ」の markdown。
- code セル(例題)は使わない。演習の type は choice / numeric / matrix のいずれか(内容に合わせて混ぜる)。"""
    else:
        cells_rule = f"""- 並び: 説明(markdown)→ 例題(code)→ 結果の読み取り(markdown)→ … → 「## 演習」の見出しの markdown → 演習(exercise)を {unit.exercise_count} 問 → 「## まとめ」の markdown。
- 演習のうち少なくとも半分は type: code にし、残りは結果の解釈を問う choice にする。"""
    # 役割と出力形式
    system = f"""あなたはデータサイエンスの社内講座の講師です。Jupyter Notebook のような単元の教材を作ります。
講座のタイプは「{_TYPE_LABEL[course_type]}」です。
次の JSON スキーマに従う JSON オブジェクトだけを返してください。

{_schema(UnitDraft)}

# 受講環境
{_ENVIRONMENT}
- 講座のデータファイル: {_data_text(data_summary) if data_summary else (', '.join(datasets) or _data_text(''))}

# 図の描き方
{_FIGURE_GUIDE}

# この講座のタイプの作り方
{_TYPE_GUIDE[course_type]}

# セルの作り方
- 最初のセルは markdown で、「## 学習目標」の見出しと、単元の学習目標の箇条書き。
{cells_rule}
- 説明の見出しは「## 見出し」。表(Markdown の表)を使って比較・整理する。
- exercise の項目:
  - title: 演習の内容がわかる短いタイトル。prompt: 何を求め、何を答えればよいかを明確に書く。
  - hint: 答えを書かずに、考え方の手がかりを示す。explanation: 正解した受講者向けに、なぜその答えになるかを説明する(計算の途中経過も)。
  - choice: choices は 4〜5 個。answer は正解の選択肢の文言そのもの。
  - numeric: answer は数値だけ。tolerance は答えの桁に合わせる(例: 小数第3位まで答えるなら 0.0005)。
  - matrix: prompt の最後に、行の項目と列の選択肢を説明する文を書く(表はアプリが作る)。choices が列、matrix_rows が行、matrix_answers が行ごとの正解。
  - code: grading は通常 "output"(出力一致)。答え方が一つに決まらない場合だけ "test" にし、test_code に assert 文を書く。
  - figure_code / figure_alt: 問題文に図を載せるときの、図を描くコードと図の説明(任意)。
- figure セル: source に図を描くコード、alt に図の説明(日本語)を書く。図の前後の markdown で、図から何を読み取るかを説明する。
- 文章はすべて日本語。

# 見本(手作業で作った同じタイプの講座の単元)
{_EXEMPLAR_NOTE}

{_exemplar(course_type)}"""
    # 依頼内容
    user = f"""# 講座全体の構成
{_outline_text(outline)}

# 講座の目的
{purpose or '指定なし'}

# 作成する単元(レベル: {_LEVEL_LABEL.get(level, level)})
- 単元 {index + 1}: {unit.title}
- 概要: {unit.summary}
- 学習目標: {' / '.join(unit.goals)}
- 目安時間: {unit.minutes} 分
- 演習の数: {unit.exercise_count} 問{'(コードは使わない)' if concept else ''}"""
    # 前の単元の演習(同じ題材を繰り返さないよう伝える)
    if previous_exercises:
        listed = "\n".join(f"- {t}" for t in previous_exercises)
        user += f"\n\n# 前の単元で出した演習(同じ題材・同じ集計を繰り返さない)\n{listed}"
    return system, user


def quiz_prompt(
    outline: CourseOutline,
    level: str,
    datasets: list[str],
    course_type: str = "practice",
    purpose: str = "",
    data_summary: str = "",
) -> tuple[str, str]:
    """
    小テストの下書きを作るプロンプトを組み立てる

    Args
    -----------------
    - outline: CourseOutline,           講座の構成案
    - level: str,                       講座のレベル
    - datasets: list[str],              講座のデータファイル名
    - course_type: str,                 講座のタイプ(concept / practice)
    - purpose: str,                     講座の目的
    - data_summary: str,                データファイルの要約

    Returns
    -----------------
    - system_prompt: str,               システムプロンプト
    - user_prompt: str,                 ユーザプロンプト

    """
    # 役割と出力形式
    system = f"""あなたはデータサイエンスの社内講座の講師です。講座の理解度を確かめる小テストを作ります。
講座のタイプは「{_TYPE_LABEL[course_type]}」です。
次の JSON スキーマに従う JSON オブジェクトだけを返してください。

{_schema(QuizDraft)}

# 受講環境
{_ENVIRONMENT}
- 講座のデータファイル: {_data_text(data_summary) if data_summary else (', '.join(datasets) or _data_text(''))}

# 図の描き方
{_FIGURE_GUIDE}

# 問題の作り方
- 問題数は {outline.quiz_count} 問。全単元からまんべんなく出題し、unit に関連する単元の番号(1 始まり)を入れる。
- 小テストは全問を解いてから採点し、満点で講座修了になる。問題文だけで答えが一つに決まるようにする。
{_QUIZ_GUIDE[course_type]}
- 形式ごとの項目:
  - choice: choices は 4〜5 個、answer は正解の選択肢の文言そのもの。
  - numeric: answer は数値だけ。tolerance は答えの桁に合わせる。
  - matrix: choices が列の選択肢、matrix_rows が行の項目、matrix_answers が行ごとの正解。
  - code: starter_code は ____ を含むコード、model_answer は完成コードで答えを print する。
  - figure_code / figure_alt: 問題文に図を載せるときの、図を描くコードと図の説明(任意)。
- explanation には、正解の理由を短く書く。
- 文章はすべて日本語。"""
    # 依頼内容
    user = f"""# 講座全体の構成(レベル: {_LEVEL_LABEL.get(level, level)})
{_outline_text(outline)}

# 講座の目的
{purpose or '指定なし'}"""
    return system, user


# 実行結果に合わせて下書きを直すときの指示(単元・小テストで共通)
_REVIEW_RULES = """\
- 下書きの中のコード(例題・模範解答・正解の根拠の check_code・図のコード)をサーバで実行した結果を渡す。
- 説明(markdown)の中の数値・表・読み取りが、例題の実行結果と食い違っていれば、実行結果に合わせて直す。
  例題の後の読み取りが具体的な数値を挙げていなければ、実行結果の数値を引用して書き足す(食い違いを避けるために数値を消さない)。
- 選択式・数値入力・表形式の answer / matrix_answers と explanation が、check_code の計算結果と食い違っていれば直す。
  計算のコードの方が誤っている場合は、コードを直す。
- 「必ず直すべき問題点」に挙げたもの(実行エラー・図が描けない・正解の不一致など)は、すべて直す。
- 直す必要のない部分(構成・文章・問題の内容)は変えない。セルや問題を減らさない。
- 直した下書き全体を、元と同じ JSON スキーマの JSON オブジェクトで返す。"""


def unit_review_prompt(draft_json: str, report: str, issues: list[str], course_type: str, data_summary: str = "") -> tuple[str, str]:
    """
    単元の下書きを、コードの実行結果に合わせて直させるプロンプトを組み立てる

    Args
    -----------------
    - draft_json: str,                  単元の下書き(JSON)
    - report: str,                      実行結果の報告
    - issues: list[str],                必ず直すべき問題点
    - course_type: str,                 講座のタイプ(concept / practice)
    - data_summary: str,                データファイルの要約

    Returns
    -----------------
    - system_prompt: str,               システムプロンプト
    - user_prompt: str,                 ユーザプロンプト

    """
    # 役割と出力形式(作り方の方針は、直すときにも守らせる)
    system = f"""あなたはデータサイエンスの社内講座の講師です。自分が作った単元の教材の下書きを、コードの実行結果に合わせて直します。
講座のタイプは「{_TYPE_LABEL[course_type]}」です。
次の JSON スキーマに従う JSON オブジェクトだけを返してください。

{_schema(UnitDraft)}

# 受講環境
{_ENVIRONMENT}
- 講座のデータファイル: {_data_text(data_summary)}

# 図の描き方
{_FIGURE_GUIDE}

# この講座のタイプの作り方
{_TYPE_GUIDE[course_type]}

# 直し方
{_REVIEW_RULES}"""
    # 下書きと実行結果
    user = f"""# 必ず直すべき問題点
{chr(10).join(f'- {i}' for i in issues) or '- なし(実行結果との食い違いがないかを確認し、あれば直す)'}

# 実行結果(セルの番号は cells の順番、1 始まり)
{report or '(実行したコードはありません)'}

# 下書き
{draft_json}"""
    return system, user


def quiz_review_prompt(draft_json: str, report: str, issues: list[str], course_type: str, data_summary: str = "") -> tuple[str, str]:
    """
    小テストの下書きを、コードの実行結果に合わせて直させるプロンプトを組み立てる

    Args
    -----------------
    - draft_json: str,                  小テストの下書き(JSON)
    - report: str,                      実行結果の報告
    - issues: list[str],                必ず直すべき問題点
    - course_type: str,                 講座のタイプ(concept / practice)
    - data_summary: str,                データファイルの要約

    Returns
    -----------------
    - system_prompt: str,               システムプロンプト
    - user_prompt: str,                 ユーザプロンプト

    """
    # 役割と出力形式
    system = f"""あなたはデータサイエンスの社内講座の講師です。自分が作った小テストの下書きを、コードの実行結果に合わせて直します。
講座のタイプは「{_TYPE_LABEL[course_type]}」です。
次の JSON スキーマに従う JSON オブジェクトだけを返してください。

{_schema(QuizDraft)}

# 受講環境
{_ENVIRONMENT}
- 講座のデータファイル: {_data_text(data_summary)}

# 図の描き方
{_FIGURE_GUIDE}

# 小テストの作り方
{_QUIZ_GUIDE[course_type]}

# 直し方
{_REVIEW_RULES}"""
    # 下書きと実行結果
    user = f"""# 必ず直すべき問題点
{chr(10).join(f'- {i}' for i in issues) or '- なし(実行結果との食い違いがないかを確認し、あれば直す)'}

# 実行結果(問の番号は questions の順番、1 始まり)
{report or '(実行したコードはありません)'}

# 下書き
{draft_json}"""
    return system, user
