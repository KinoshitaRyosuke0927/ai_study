"""AI の入力(画面からの依頼)と出力(AI の応答)の型。

AI の応答はこの型で検証してから DB に保存する。項目を増やすときは、こことプロンプト(prompts.py)、
保存処理(services/ai_course_service.py)の3か所を合わせて直す。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator


class _Lenient(BaseModel):
    """AI の出力用の基底クラス。既定値のある項目に null が返ってきたら既定値として扱う。"""

    @field_validator("*", mode="before")
    @classmethod
    def _normalize(cls, value: Any, info: ValidationInfo) -> Any:
        """
        AI の出力の小さな揺れをならす
        - null は既定値に置き換える(必須の項目はそのまま検証エラーにする)
        - 文字列の項目に数値が来たら文字列にする(数値入力の正解など)

        Args
        -----------------
        - value: Any,                       AI が返した値
        - info: ValidationInfo,             検証中の項目の情報

        Returns
        -----------------
        - value: Any,                       置き換え後の値

        """
        # null で、既定値のある項目なら既定値を返す
        field = cls.model_fields.get(info.field_name or "")
        if value is None and field is not None and not field.is_required():
            return field.get_default(call_default_factory=True)
        # 文字列の項目に数値が来たら文字列にする(真偽値は除く)
        if field is not None and field.annotation is str and isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
        # それ以外はそのまま返却
        return value


# ---------- 入力(画面からの依頼) ----------


class OutlineRequest(BaseModel):
    """構成案の生成依頼。"""

    title: str = Field(min_length=1, max_length=200)  # 講座タイトル(仮)
    # 講座のタイプ: concept = 概念理解型(コードなし。図表・手計算・試験形式の演習)
    #               practice = 実践型(コーディング中心。例題コードとコードの演習)
    course_type: Literal["concept", "practice"] = "practice"
    purpose: str = Field(default="", max_length=2000)  # 講座の目的(受講後にどうなってほしいか)
    # 講座のデータファイルの要約(列・型・欠損・先頭の行)。画面で選んだファイルからサーバが作る
    data_summary: str = Field(default="", max_length=8000)
    topic: str = Field(min_length=1, max_length=4000)  # 題材・扱いたい内容
    level: Literal["basic", "intermediate", "advanced"] = "basic"
    unit_count: int = Field(default=5, ge=1, le=12)  # 単元数の目安
    libraries: list[str] = []  # 使用ライブラリ
    audience: str = Field(default="", max_length=1000)  # 対象者・前提知識


# ---------- 出力(AI の応答) ----------


class OutlineUnit(_Lenient):
    """構成案の単元。"""

    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=500)
    goals: list[str] = Field(default_factory=list, max_length=6)
    minutes: int = Field(default=30, ge=5, le=120)
    exercise_count: int = Field(default=3, ge=1, le=5)


class CourseOutline(_Lenient):
    """講座の構成案(画面で編集してから下書き作成に使う)。"""

    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=8)
    outcomes: list[str] = Field(default_factory=list, max_length=8)
    libraries: list[str] = Field(default_factory=list, max_length=8)
    units: list[OutlineUnit] = Field(min_length=1, max_length=12)
    quiz_count: int = Field(default=10, ge=3, le=20)


def _check_keyed(
    qtype: str, choices: list[str], matrix_rows: list[str], answer: str, matrix_answers: list[str], starter: str, model: str
) -> None:
    """
    問題の形式ごとに、必要な項目がそろっているかを確かめる(足りなければ AI に再試行させるため例外にする)

    Args
    -----------------
    - qtype: str,                       問題の形式
    - choices: list[str],               選択肢(表形式では列の選択肢)
    - matrix_rows: list[str],           表形式の行
    - answer: str,                      正解(選択式・数値入力)
    - matrix_answers: list[str],        表形式の行ごとの正解
    - starter: str,                     初期コード(コード)
    - model: str,                       模範解答(コード)

    """
    # 形式ごとに必須の項目を確認
    if qtype == "code" and not (starter.strip() and model.strip()):
        raise ValueError("type が code のときは starter_code と model_answer が必要です")
    if qtype == "choice" and (len(choices) < 2 or answer not in choices):
        raise ValueError("type が choice のときは choices を 2 つ以上と、choices のいずれかと同じ文言の answer が必要です")
    if qtype == "numeric" and not answer.strip():
        raise ValueError("type が numeric のときは answer(数値)が必要です")
    if qtype == "matrix" and (len(choices) < 2 or not matrix_rows or len(matrix_answers) != len(matrix_rows)):
        raise ValueError("type が matrix のときは choices(列の選択肢)を 2 つ以上、matrix_rows と、行と同じ数の matrix_answers が必要です")


class GeneratedExercise(_Lenient):
    """AI が作る単元の演習(コード・選択式・数値入力・表形式)。"""

    type: Literal["code", "choice", "numeric", "matrix"] = "code"
    title: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1)  # 問題文(Markdown)
    hint: str = ""
    explanation: str = ""
    # code のとき
    starter_code: str = ""  # 空欄 ____ を含む初期コード
    model_answer: str = ""  # AI の模範解答(作成者には最初は見せない)
    grading: Literal["output", "test"] = "output"
    test_code: str = ""
    # choice / numeric / matrix のとき
    choices: list[str] = []  # 選択肢(matrix では列の選択肢)
    matrix_rows: list[str] = []  # matrix の行(分類する項目)
    answer: str = ""  # choice は正解の選択肢の文言、numeric は数値
    matrix_answers: list[str] = []  # matrix の行ごとの正解(choices のいずれか)
    tolerance: float = 0.0  # numeric の許容誤差
    check_code: str = ""  # choice / numeric / matrix の正解の根拠を計算して print するコード(自動検証に使う)
    # 問題文に載せる図(任意)。matplotlib で図を描くコードと、図の説明
    figure_code: str = ""
    figure_alt: str = ""

    @model_validator(mode="after")
    def _required_by_type(self) -> GeneratedExercise:
        """形式ごとに必要な項目がそろっているかを確かめる"""
        _check_keyed(self.type, self.choices, self.matrix_rows, self.answer, self.matrix_answers, self.starter_code, self.model_answer)
        return self


class GeneratedCell(_Lenient):
    """AI が作る単元のセル。"""

    # markdown: 説明 / code: 例題(受講者が実行する)/ figure: 説明に載せる図(サーバで描いて画像にする)/ exercise: 演習
    type: Literal["markdown", "code", "figure", "exercise"]
    source: str = ""  # markdown の本文、code の例題、figure の図を描くコード
    alt: str = ""  # figure のときの図の説明(画像の代替テキスト)
    exercise: GeneratedExercise | None = None  # exercise のときの内容


class UnitDraft(_Lenient):
    """AI が作る単元の下書き。"""

    cells: list[GeneratedCell] = Field(min_length=1)


class GeneratedQuestion(_Lenient):
    """AI が作る小テストの問題。"""

    type: Literal["choice", "numeric", "matrix", "code"]
    prompt: str = Field(min_length=1)
    choices: list[str] = []  # choice の選択肢(matrix では列の選択肢)
    matrix_rows: list[str] = []  # matrix の行(分類する項目)
    answer: str = ""  # choice は正解の選択肢の文言、numeric は数値
    matrix_answers: list[str] = []  # matrix の行ごとの正解
    tolerance: float = 0.0  # numeric の許容誤差
    unit: int | None = None  # 関連単元の番号(1 始まり)
    explanation: str = ""
    starter_code: str = ""  # code のとき
    model_answer: str = ""  # code のとき(AI の模範解答)
    grading: Literal["output", "test"] = "output"
    test_code: str = ""
    check_code: str = ""  # choice / numeric / matrix の正解の根拠を計算して print するコード(自動検証に使う)
    figure_code: str = ""  # 問題文に載せる図を描くコード(任意)
    figure_alt: str = ""  # 図の説明

    @model_validator(mode="after")
    def _required_by_type(self) -> GeneratedQuestion:
        """形式ごとに必要な項目がそろっているかを確かめる"""
        _check_keyed(self.type, self.choices, self.matrix_rows, self.answer, self.matrix_answers, self.starter_code, self.model_answer)
        return self


class QuizDraft(_Lenient):
    """AI が作る小テストの下書き。"""

    questions: list[GeneratedQuestion] = Field(min_length=1, max_length=30)
