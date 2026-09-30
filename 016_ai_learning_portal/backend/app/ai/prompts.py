"""講座下書き生成のプロンプト。

精度改善はこのファイルを中心に行う。プロンプトを変えたら PROMPT_VERSION を上げること
(AI 呼び出しの記録 ai_generations に版番号が残り、どの版で作った下書きかを追える)。
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from app.ai.schemas import CourseOutline, OutlineRequest, OutlineUnit, QuizDraft, UnitDraft

PROMPT_VERSION = "v1"

_LEVEL_LABEL = {"basic": "基礎", "intermediate": "応用", "advanced": "実践"}

# 受講者のコードが動く環境(すべてのプロンプトで共通)
_ENVIRONMENT = """\
- 受講者のコードはブラウザ内の Python(Pyodide、Python 3.14)で実行される。
- 使えるライブラリ: pandas 3.0, numpy, matplotlib, scipy, scikit-learn, statsmodels(seaborn などその他は使わない)。
- インターネット接続・ファイルのダウンロード・外部 API の呼び出しはできない。
- データは、講座のデータファイル(あれば列挙する)を pd.read_csv("ファイル名") で読むか、
  コードの中で作る(乱数を使うときは np.random.default_rng(固定の seed) で毎回同じ値にする)。
- matplotlib の図は画像として表示される。日本語フォントが無いため、図のラベルは英語にする。"""


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
    # 役割と出力形式
    system = f"""あなたはデータサイエンスの社内講座を設計する講師です。
部署のメンバーが、概念の説明とハンズオン(コードを書く演習)で学ぶ講座の構成案を作ります。
次の JSON スキーマに従う JSON オブジェクトだけを返してください。

{_schema(CourseOutline)}

# 受講環境
{_ENVIRONMENT}

# 方針
- 単元は、基本から応用へ無理なく進む順に並べる。1単元は 15〜30 分で学べる量にする。
- 各単元の goals は「〜できる」の形で 2〜3 個。
- 各単元に演習を 1〜2 問(exercise_count)。
- 小テストの問題数(quiz_count)は 10 前後。
- 文章はすべて日本語。"""
    # 依頼内容
    user = f"""# 依頼
- 講座タイトル(仮): {req.title}
- レベル: {_LEVEL_LABEL[req.level]}
- 単元数の目安: {req.unit_count}
- 使用ライブラリ: {', '.join(req.libraries) or '指定なし(pandas を中心に)'}
- 対象者・前提知識: {req.audience or '指定なし'}

# 題材・扱いたい内容
{req.topic}"""
    return system, user


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


def unit_prompt(outline: CourseOutline, index: int, level: str, datasets: list[str]) -> tuple[str, str]:
    """
    単元の下書き(説明・例題・演習のセル)を作るプロンプトを組み立てる

    Args
    -----------------
    - outline: CourseOutline,           講座の構成案
    - index: int,                       対象の単元の位置(0 始まり)
    - level: str,                       講座のレベル
    - datasets: list[str],              講座のデータファイル名

    Returns
    -----------------
    - system_prompt: str,               システムプロンプト
    - user_prompt: str,                 ユーザプロンプト

    """
    unit: OutlineUnit = outline.units[index]
    # 役割と出力形式
    system = f"""あなたはデータサイエンスの社内講座の講師です。Jupyter Notebook のような単元の教材を作ります。
次の JSON スキーマに従う JSON オブジェクトだけを返してください。

{_schema(UnitDraft)}

# 受講環境
{_ENVIRONMENT}
- 講座のデータファイル: {', '.join(datasets) or 'なし(データはコードの中で作る)'}

# セルの作り方
- 並び: 説明(markdown)→ 例題(code)→ 説明 → … → 演習(exercise)。説明の見出しは「## 見出し」。
- markdown: 概念を具体例とともに説明する。数式は $...$ で書いてよい。
- code: そのまま実行できる例題。結果を print するか、最後の行を式にして値を表示する。
- exercise: 受講者がコードを書く演習を {unit.exercise_count} 問。
  - prompt: 何を求め、何を表示すればよいかを明確に書く。
  - starter_code: 必要な import とデータの準備を含み、受講者が埋める部分を ____ にしたコード。
  - model_answer: starter_code の ____ を埋めた完成コード。実行すると答えを print する。
  - 出力が毎回同じになるようにする(乱数は seed を固定し、小数は round で桁をそろえる)。
  - grading は通常 "output"(出力一致)。答え方が一つに決まらない場合だけ "test" にし、
    test_code に受講者のコード実行後に評価する assert 文を書く。
- 各セルは前のセルの変数に頼らず、単独で実行できるようにする。
- 文章はすべて日本語。"""
    # 依頼内容
    user = f"""# 講座全体の構成
{_outline_text(outline)}

# 作成する単元(レベル: {_LEVEL_LABEL.get(level, level)})
- 単元 {index + 1}: {unit.title}
- 概要: {unit.summary}
- 学習目標: {' / '.join(unit.goals)}
- 目安時間: {unit.minutes} 分"""
    return system, user


def quiz_prompt(outline: CourseOutline, level: str, datasets: list[str]) -> tuple[str, str]:
    """
    小テストの下書きを作るプロンプトを組み立てる

    Args
    -----------------
    - outline: CourseOutline,           講座の構成案
    - level: str,                       講座のレベル
    - datasets: list[str],              講座のデータファイル名

    Returns
    -----------------
    - system_prompt: str,               システムプロンプト
    - user_prompt: str,                 ユーザプロンプト

    """
    # 役割と出力形式
    system = f"""あなたはデータサイエンスの社内講座の講師です。講座の理解度を確かめる小テストを作ります。
次の JSON スキーマに従う JSON オブジェクトだけを返してください。

{_schema(QuizDraft)}

# 受講環境
{_ENVIRONMENT}
- 講座のデータファイル: {', '.join(datasets) or 'なし(データはコードの中で作る)'}

# 問題の作り方
- 問題数は {outline.quiz_count} 問。全単元からまんべんなく出題し、unit に関連する単元の番号(1 始まり)を入れる。
- 単元の内容に合わせて、最も適した形式を選ぶ。
  - choice(選択式): 概念の理解を問う。choices は 4 つ、answer は正解の選択肢の文言そのもの。
  - numeric(数値入力): 手計算できる程度の計算。answer は数値だけ。
  - code(コード): 実際に手を動かして求める。starter_code は ____ を含むコード、model_answer は完成コードで答えを print する。
- explanation には、正解した受講者向けの短い解説を書く。
- 文章はすべて日本語。"""
    # 依頼内容
    user = f"""# 講座全体の構成(レベル: {_LEVEL_LABEL.get(level, level)})
{_outline_text(outline)}"""
    return system, user
