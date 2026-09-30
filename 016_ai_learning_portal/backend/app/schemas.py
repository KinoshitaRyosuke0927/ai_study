"""API の入出力スキーマ(Pydantic)。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ---------- 認証 ----------
class LoginRequest(BaseModel):
    """ログイン要求。"""

    login_name: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)


class UserOut(BaseModel):
    """ログイン中ユーザの情報。"""

    id: int
    login_name: str
    display_name: str
    is_admin: bool


class AppConfigOut(BaseModel):
    """フロントエンドに渡す実行時設定。"""

    pyodide_base_url: str


# ---------- 講座 ----------
class CourseSummaryOut(BaseModel):
    """講座一覧の1件。"""

    slug: str
    title: str
    summary: str
    level: str
    tags: list[str]
    status: str
    unit_count: int
    completed_unit_count: int
    exercise_count: int
    estimated_minutes: int
    next_unit_id: int | None
    completed: bool
    quiz_question_count: int
    quiz_unlocked: bool  # 全単元を完了していれば True(小テストを受けられる)
    best_quiz_score: int | None  # 小テストの最高得点(未受験は None)
    published_at: datetime | None


class PrerequisiteOut(BaseModel):
    """前提講座。"""

    slug: str
    title: str
    completed: bool


class UnitSummaryOut(BaseModel):
    """講座詳細に表示する単元の1件。"""

    id: int
    position: int
    title: str
    summary: str
    estimated_minutes: int
    exercise_count: int
    completed: bool


class DatasetOut(BaseModel):
    """講座で使うデータファイル。"""

    id: int
    filename: str
    url: str


class CourseDetailOut(CourseSummaryOut):
    """講座詳細。"""

    outcomes: list[str]
    libraries: list[str]
    author_name: str | None
    updated_at: datetime | None
    prerequisites: list[PrerequisiteOut]
    units: list[UnitSummaryOut]
    datasets: list[DatasetOut]


# ---------- 単元 ----------
class ExerciseOut(BaseModel):
    """演習セルの内容(想定出力や解答は含めない)。"""

    problem_id: int
    title: str
    prompt: str
    hint: str
    starter_code: str
    grading: str
    test_code: str
    passed: bool
    last_answer: str | None


class CellOut(BaseModel):
    """単元を構成するセル。"""

    id: int
    cell_type: str
    source: str
    exercise: ExerciseOut | None = None


class UnitNavOut(BaseModel):
    """単元の目次・前後移動用の情報。"""

    id: int
    position: int
    title: str
    completed: bool


class UnitDetailOut(BaseModel):
    """単元画面の表示内容。"""

    id: int
    course_slug: str
    course_title: str
    position: int
    unit_count: int
    title: str
    goals: list[str]
    estimated_minutes: int
    exercise_count: int
    completed: bool
    cells: list[CellOut]
    units: list[UnitNavOut]
    prev_unit: UnitNavOut | None
    next_unit: UnitNavOut | None
    datasets: list[DatasetOut]


# ---------- 提出 ----------
class CodeSubmitRequest(BaseModel):
    """コード問題の提出(コードはブラウザで実行済み)。"""

    code: str = Field(max_length=200_000)
    output: str = Field(default="", max_length=200_000)  # 標準出力 + 最後の式の値
    error: str | None = Field(default=None, max_length=50_000)  # 例外発生時のメッセージ
    test_passed: bool | None = None  # 採点方式「テストコード」の結果


class SubmitResultOut(BaseModel):
    """提出の採点結果。"""

    passed: bool
    message: str
    unit_completed: bool
    unit_newly_completed: bool


# ---------- 小テスト ----------
class RelatedUnitOut(BaseModel):
    """復習用の関連単元。"""

    id: int
    position: int
    title: str


class QuizQuestionOut(BaseModel):
    """小テストの問題(正解・想定出力は含めない)。"""

    problem_id: int
    position: int
    answer_format: str  # choice / numeric / code
    prompt: str
    choices: list[str]
    starter_code: str
    grading: str
    test_code: str
    related_unit: RelatedUnitOut | None


class QuizAttemptOut(BaseModel):
    """小テストの受験記録。"""

    id: int
    score: int
    total: int
    created_at: datetime


class QuizOut(BaseModel):
    """小テスト画面の表示内容。"""

    course_slug: str
    course_title: str
    unlocked: bool
    remaining_units: list[RelatedUnitOut]  # 未完了の単元(受験できない理由)
    completed: bool
    questions: list[QuizQuestionOut]
    attempts: list[QuizAttemptOut]
    datasets: list[DatasetOut]


class QuizAnswerIn(BaseModel):
    """小テストの1問分の回答(コード問題はブラウザで実行済み)。"""

    problem_id: int
    answer: str = Field(default="", max_length=200_000)  # 選択肢の文言・数値・コード
    output: str = Field(default="", max_length=200_000)
    error: str | None = Field(default=None, max_length=50_000)
    test_passed: bool | None = None


class QuizSubmitRequest(BaseModel):
    """小テストの提出。"""

    answers: list[QuizAnswerIn]


class QuizQuestionResultOut(BaseModel):
    """1問分の採点結果。"""

    problem_id: int
    correct: bool
    answered: bool
    message: str
    explanation: str  # 正解した問題のみ
    related_unit: RelatedUnitOut | None


class QuizResultOut(BaseModel):
    """小テストの採点結果。"""

    attempt: QuizAttemptOut
    perfect: bool
    course_newly_completed: bool
    results: list[QuizQuestionResultOut]


# ---------- ホーム・マイページ ----------
class RoadmapCourseOut(BaseModel):
    """学習ロードマップの講座。"""

    slug: str
    title: str
    state: str  # completed / in_progress / not_started


class HomeOut(BaseModel):
    """ホーム画面の表示内容。"""

    continue_course: CourseSummaryOut | None
    continue_unit_title: str | None
    in_progress: list[CourseSummaryOut]
    completed_course_count: int
    in_progress_count: int
    solved_exercise_count: int
    roadmap: dict[str, list[RoadmapCourseOut]]  # レベル → 講座
    new_courses: list[CourseSummaryOut]


class ActivityOut(BaseModel):
    """最近の学習の1件。"""

    at: datetime
    text: str


class QuizHistoryOut(BaseModel):
    """小テストの受験履歴の1件。"""

    course_slug: str
    course_title: str
    score: int
    total: int
    created_at: datetime


class CompletedCourseOut(BaseModel):
    """修了した講座。"""

    slug: str
    title: str
    completed_at: datetime
    attempt_count: int


class MyPageOut(BaseModel):
    """マイページの表示内容。"""

    completed_course_count: int
    in_progress_count: int
    solved_exercise_count: int
    quiz_attempt_count: int
    in_progress: list[CourseSummaryOut]
    completed: list[CompletedCourseOut]
    quiz_history: list[QuizHistoryOut]
    activities: list[ActivityOut]
