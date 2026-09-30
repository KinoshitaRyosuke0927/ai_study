"""管理者向け API の入出力スキーマ(Pydantic)。

受講者向けと違い、想定出力・作成者の解答・AI の模範解答など、問題のすべての項目を扱う。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas import DatasetOut

_SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


# ---------- 講座管理 ----------
class AdminCourseRowOut(BaseModel):
    """講座管理一覧の1件。"""

    id: int
    slug: str
    title: str
    level: str
    status: str
    unit_count: int
    problem_count: int  # 演習 + 小テストの問題数
    verified_count: int  # そのうち検証済みの数
    learner_count: int  # 1単元以上完了した人数
    completer_count: int  # 修了した人数
    author_name: str | None
    updated_at: datetime | None


class CourseInfoIn(BaseModel):
    """講座情報の作成・更新。"""

    slug: str = Field(min_length=1, max_length=100, pattern=_SLUG_PATTERN)
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=5000)
    level: str = "basic"
    tags: list[str] = []
    outcomes: list[str] = []
    libraries: list[str] = []
    prerequisite_ids: list[int] = []


# ---------- 問題 ----------
class ProblemIn(BaseModel):
    """演習・小テストの問題の保存(id が無ければ新規)。"""

    id: int | None = None
    answer_format: str = "code"  # code / choice / numeric
    title: str = Field(default="", max_length=200)
    prompt: str = ""
    hint: str = ""
    starter_code: str = ""
    grading: str = "output"
    test_code: str = ""
    choices: list[str] = []
    correct_answer: str = ""
    tolerance: float = 1e-6
    explanation: str = ""
    related_unit_id: int | None = None
    ai_model_answer: str = ""
    author_answer: str = ""


class ProblemOut(ProblemIn):
    """問題のすべての項目(管理者のみ)。"""

    id: int  # type: ignore[assignment]
    expected_output: str
    verify_status: str
    content_version: int


# ---------- 単元 ----------
class CellIn(BaseModel):
    """単元のセルの保存(演習セルは problem を持つ)。"""

    id: int | None = None
    cell_type: str
    source: str = ""
    problem: ProblemIn | None = None


class CellAdminOut(BaseModel):
    """単元のセル(管理者向け)。"""

    id: int
    cell_type: str
    source: str
    ai_generated: bool
    problem: ProblemOut | None


class UnitInfoIn(BaseModel):
    """単元の基本情報。"""

    title: str = Field(min_length=1, max_length=200)
    summary: str = ""
    goals: list[str] = []
    estimated_minutes: int = Field(default=20, ge=1, le=600)


class UnitContentIn(UnitInfoIn):
    """単元の保存(基本情報 + セル一式)。"""

    cells: list[CellIn]


class UnitAdminOut(BaseModel):
    """単元(管理者向け)。"""

    id: int
    position: int
    title: str
    summary: str
    goals: list[str]
    estimated_minutes: int
    cells: list[CellAdminOut]


class QuizContentIn(BaseModel):
    """小テストの保存(問題一式)。"""

    questions: list[ProblemIn]


class CourseEditorOut(BaseModel):
    """講座エディタの表示内容。"""

    id: int
    slug: str
    title: str
    summary: str
    level: str
    tags: list[str]
    outcomes: list[str]
    libraries: list[str]
    status: str
    prerequisite_ids: list[int]
    units: list[UnitAdminOut]
    quiz: list[ProblemOut]
    datasets: list[DatasetOut]
    other_courses: list[dict]  # 前提講座の候補 [{id, title}]


class ReorderIn(BaseModel):
    """単元の並べ替え。"""

    unit_ids: list[int]


# ---------- 検証 ----------
class RunIn(BaseModel):
    """ブラウザで実行した結果。"""

    output: str = Field(default="", max_length=200_000)
    error: str | None = Field(default=None, max_length=50_000)
    test_passed: bool | None = None


class VerifyIn(BaseModel):
    """作成者の解答(と AI の模範解答)の実行結果。"""

    author: RunIn
    ai: RunIn | None = None


class VerifyOut(BaseModel):
    """検証結果。"""

    verify_status: str
    message: str
    expected_output: str
    author_output: str
    ai_output: str | None


class AcceptAuthorIn(BaseModel):
    """作成者の解答の出力を正とする。"""

    output: str = Field(max_length=200_000)


# ---------- 公開 ----------
class CheckItemOut(BaseModel):
    """公開前チェックの未解決項目。"""

    label: str
    status: str
    unit_id: int | None
    problem_id: int | None


class CheckOut(BaseModel):
    """公開前チェックの1項目。"""

    key: str
    label: str
    ok: bool
    detail: str
    items: list[CheckItemOut] = []


class PublishCheckOut(BaseModel):
    """公開前チェックの結果。"""

    course_id: int
    slug: str
    title: str
    status: str
    checks: list[CheckOut]
    publishable: bool  # ブラウザでの例題実行チェック以外がすべて OK


class PublishIn(BaseModel):
    """公開の要求(例題の実行チェックはブラウザで行う)。"""

    examples_ok: bool


# ---------- メンバー ----------
class ProgressCellOut(BaseModel):
    """受講状況マトリクスの1マス。"""

    course_id: int
    state: str  # completed / in_progress / none
    done: int
    total: int


class MemberProgressOut(BaseModel):
    """受講状況マトリクスの1行(メンバー)。"""

    id: int
    login_name: str
    display_name: str
    is_admin: bool
    last_activity: datetime | None
    cells: list[ProgressCellOut]


class ProgressMatrixOut(BaseModel):
    """メンバーの受講状況。"""

    courses: list[dict]  # [{id, slug, title, unit_count}]
    members: list[MemberProgressOut]


class UserAdminOut(BaseModel):
    """メンバー管理の1件。"""

    id: int
    login_name: str
    display_name: str
    is_admin: bool
    is_active: bool
    created_at: datetime | None


class UserCreateIn(BaseModel):
    """メンバーの追加。"""

    login_name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=200)
    is_admin: bool = False


class UserUpdateIn(BaseModel):
    """メンバーの更新(password を指定したときだけ変更する)。"""

    display_name: str = Field(min_length=1, max_length=100)
    is_admin: bool
    is_active: bool
    password: str | None = Field(default=None, min_length=8, max_length=200)


# ---------- AI による講座作成 ----------
class AIStatusOut(BaseModel):
    """AI の利用可否。"""

    enabled: bool
    model_outline: str
    model_draft: str


class DraftCreateIn(BaseModel):
    """構成案から下書きを作る要求。"""

    slug: str = Field(min_length=1, max_length=100, pattern=_SLUG_PATTERN)
    request: dict  # OutlineRequest(元の生成依頼)
    outline: dict  # CourseOutline(画面で編集した構成案)


class AIJobOut(BaseModel):
    """下書き生成ジョブの状態。"""

    id: int
    course_id: int | None
    status: str  # queued / running / done / failed
    total_steps: int
    done_steps: int
    current_step: str
    message: str
