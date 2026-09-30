"""AI の入力(画面からの依頼)と出力(AI の応答)の型。

AI の応答はこの型で検証してから DB に保存する。項目を増やすときは、こことプロンプト(prompts.py)、
保存処理(services/ai_course_service.py)の3か所を合わせて直す。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator


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
    minutes: int = Field(default=20, ge=5, le=120)
    exercise_count: int = Field(default=1, ge=1, le=3)


class CourseOutline(_Lenient):
    """講座の構成案(画面で編集してから下書き作成に使う)。"""

    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=8)
    outcomes: list[str] = Field(default_factory=list, max_length=8)
    libraries: list[str] = Field(default_factory=list, max_length=8)
    units: list[OutlineUnit] = Field(min_length=1, max_length=12)
    quiz_count: int = Field(default=10, ge=3, le=20)


class GeneratedExercise(_Lenient):
    """AI が作る演習(模範解答を含む)。"""

    title: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1)  # 問題文(Markdown)
    hint: str = ""
    starter_code: str = Field(min_length=1)  # 空欄 ____ を含む初期コード
    model_answer: str = Field(min_length=1)  # AI の模範解答(作成者には最初は見せない)
    explanation: str = ""
    grading: Literal["output", "test"] = "output"
    test_code: str = ""


class GeneratedCell(_Lenient):
    """AI が作る単元のセル。"""

    type: Literal["markdown", "code", "exercise"]
    source: str = ""  # markdown / code のときの本文
    exercise: GeneratedExercise | None = None  # exercise のときの内容


class UnitDraft(_Lenient):
    """AI が作る単元の下書き。"""

    cells: list[GeneratedCell] = Field(min_length=1)


class GeneratedQuestion(_Lenient):
    """AI が作る小テストの問題。"""

    type: Literal["choice", "numeric", "code"]
    prompt: str = Field(min_length=1)
    choices: list[str] = []  # choice のときの選択肢
    answer: str = ""  # choice は正解の選択肢の文言、numeric は数値
    unit: int | None = None  # 関連単元の番号(1 始まり)
    explanation: str = ""
    starter_code: str = ""  # code のとき
    model_answer: str = ""  # code のとき(AI の模範解答)
    grading: Literal["output", "test"] = "output"
    test_code: str = ""


class QuizDraft(_Lenient):
    """AI が作る小テストの下書き。"""

    questions: list[GeneratedQuestion] = Field(min_length=1, max_length=30)
