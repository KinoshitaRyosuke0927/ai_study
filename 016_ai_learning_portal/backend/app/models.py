"""ORM モデル(テーブル定義)。

テーブル構成は docs/spec.md の「データモデル」を参照。
変更したら `alembic revision --autogenerate` でマイグレーションを作成すること。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.common.constants import CourseLevel, CourseStatus, Grading, VerifyStatus

# MySQL の TEXT(64KB)/BLOB(64KB)では足りない列向けの型
LongText = Text().with_variant(mysql.MEDIUMTEXT(), "mysql")
LongBlob = LargeBinary().with_variant(mysql.LONGBLOB(), "mysql")


class Base(DeclarativeBase):
    """全モデルの基底クラス。"""


class TimestampMixin:
    """作成日時・更新日時の共通列。"""

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class User(TimestampMixin, Base):
    """ユーザ(受講者・管理者)。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    login_name: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Course(TimestampMixin, Base):
    """講座。"""

    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text, default="")
    level: Mapped[str] = mapped_column(String(16), default=CourseLevel.BASIC)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    outcomes: Mapped[list] = mapped_column(JSON, default=list)  # この講座で身につくこと
    libraries: Mapped[list] = mapped_column(JSON, default=list)  # 使用ライブラリ
    status: Mapped[str] = mapped_column(String(16), default=CourseStatus.DRAFT)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    author: Mapped[User | None] = relationship()
    units: Mapped[list[Unit]] = relationship(
        back_populates="course", cascade="all, delete-orphan", order_by="Unit.position"
    )
    datasets: Mapped[list[Dataset]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    prerequisites: Mapped[list[CoursePrerequisite]] = relationship(
        foreign_keys="CoursePrerequisite.course_id", cascade="all, delete-orphan"
    )


class CoursePrerequisite(Base):
    """講座の前提講座。"""

    __tablename__ = "course_prerequisites"

    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True
    )
    prerequisite_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True
    )

    prerequisite: Mapped[Course] = relationship(foreign_keys=[prerequisite_id])


class Unit(TimestampMixin, Base):
    """講座内の単元。"""

    __tablename__ = "units"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)  # 1 始まりの並び順
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text, default="")
    goals: Mapped[list] = mapped_column(JSON, default=list)  # 学習目標
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=20)

    course: Mapped[Course] = relationship(back_populates="units")
    cells: Mapped[list[Cell]] = relationship(
        back_populates="unit", cascade="all, delete-orphan", order_by="Cell.position"
    )


class Problem(TimestampMixin, Base):
    """演習・小テストの問題(両者を同じ構造で扱う)。"""

    __tablename__ = "problems"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    # 単元内の演習なら単元 ID、小テストなら NULL
    unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("units.id", ondelete="CASCADE"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(16))  # ProblemKind
    position: Mapped[int] = mapped_column(Integer, default=1)
    answer_format: Mapped[str] = mapped_column(String(16))  # AnswerFormat
    title: Mapped[str] = mapped_column(String(200), default="")
    prompt: Mapped[str] = mapped_column(LongText, default="")  # 問題文(Markdown)
    hint: Mapped[str] = mapped_column(Text, default="")
    starter_code: Mapped[str] = mapped_column(LongText, default="")
    grading: Mapped[str] = mapped_column(String(16), default=Grading.OUTPUT)
    expected_output: Mapped[str] = mapped_column(LongText, default="")  # 受講者には返さない
    test_code: Mapped[str] = mapped_column(LongText, default="")
    choices: Mapped[list] = mapped_column(JSON, default=list)  # 選択式の選択肢
    correct_answer: Mapped[str] = mapped_column(Text, default="")  # 選択式・数値の正解
    tolerance: Mapped[float] = mapped_column(Float, default=1e-6)  # 数値比較の許容誤差
    explanation: Mapped[str] = mapped_column(LongText, default="")  # 正解後に表示する解説
    related_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("units.id", ondelete="SET NULL"), nullable=True
    )
    ai_model_answer: Mapped[str] = mapped_column(LongText, default="")  # AI の模範解答(非公開)
    author_answer: Mapped[str] = mapped_column(LongText, default="")  # 作成者の解答
    verify_status: Mapped[str] = mapped_column(String(16), default=VerifyStatus.TODO)
    content_version: Mapped[int] = mapped_column(Integer, default=1)


class Cell(TimestampMixin, Base):
    """単元を構成するセル(説明・例題コード・演習)。"""

    __tablename__ = "cells"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    cell_type: Mapped[str] = mapped_column(String(16))  # CellType
    source: Mapped[str] = mapped_column(LongText, default="")  # Markdown またはコード
    problem_id: Mapped[int | None] = mapped_column(
        ForeignKey("problems.id", ondelete="SET NULL"), nullable=True
    )
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)

    unit: Mapped[Unit] = relationship(back_populates="cells")
    problem: Mapped[Problem | None] = relationship()


class Dataset(TimestampMixin, Base):
    """講座で使うデータファイル(ブラウザの Python 実行環境に配置する)。"""

    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100), default="text/csv")
    content: Mapped[bytes] = mapped_column(LongBlob)

    course: Mapped[Course] = relationship(back_populates="datasets")


class UnitProgress(Base):
    """単元の完了記録(単元内の演習をすべて正解した時点で作成)。"""

    __tablename__ = "unit_progress"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    unit_id: Mapped[int] = mapped_column(
        ForeignKey("units.id", ondelete="CASCADE"), primary_key=True
    )
    completed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class QuizAttempt(Base):
    """小テストの受験記録(1回の採点 = 1件)。"""

    __tablename__ = "quiz_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    score: Mapped[int] = mapped_column(Integer)  # 正解数
    total: Mapped[int] = mapped_column(Integer)  # 問題数
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Submission(Base):
    """演習・小テストの提出記録。"""

    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"))
    # 小テストの回答なら受験記録 ID(演習の提出は NULL)
    attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey("quiz_attempts.id", ondelete="CASCADE"), nullable=True
    )
    answer: Mapped[str] = mapped_column(LongText, default="")  # コードまたは回答値
    output: Mapped[str] = mapped_column(LongText, default="")  # 実行時の出力
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    content_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CourseCompletion(Base):
    """講座の修了記録(小テスト満点で作成。演習を後から直しても消さない)。"""

    __tablename__ = "course_completions"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True
    )
    completed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AIJob(TimestampMixin, Base):
    """AI による講座下書きの生成ジョブ(進捗を画面に表示する)。"""

    __tablename__ = "ai_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), default="course_draft")
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued / running / done / failed
    total_steps: Mapped[int] = mapped_column(Integer, default=0)
    done_steps: Mapped[int] = mapped_column(Integer, default=0)
    current_step: Mapped[str] = mapped_column(String(200), default="")
    message: Mapped[str] = mapped_column(LongText, default="")  # 失敗・警告の内容
    request: Mapped[dict] = mapped_column(JSON, default=dict)  # 生成時の入力(題材・構成案)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class AIGeneration(Base):
    """AI 呼び出しの記録(プロンプトと応答をそのまま残し、精度改善に使う)。"""

    __tablename__ = "ai_generations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("ai_jobs.id", ondelete="SET NULL"), nullable=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id", ondelete="SET NULL"), nullable=True)
    purpose: Mapped[str] = mapped_column(String(32))  # outline / unit / quiz
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(32))
    system_prompt: Mapped[str] = mapped_column(LongText, default="")
    user_prompt: Mapped[str] = mapped_column(LongText, default="")
    response_text: Mapped[str] = mapped_column(LongText, default="")
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str] = mapped_column(LongText, default="")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AppState(Base):
    """アプリの状態(最終アクセス日時など)。DB の自動停止の判断に使う。"""

    __tablename__ = "app_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
