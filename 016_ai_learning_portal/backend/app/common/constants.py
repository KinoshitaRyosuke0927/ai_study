"""アプリ全体で使う区分値の定義。

DB には文字列で保存する(MySQL の ENUM は使わず、値の追加をマイグレーション不要にする)。
"""

from __future__ import annotations


class CourseLevel:
    """講座のレベル。"""

    BASIC = "basic"  # 基礎
    INTERMEDIATE = "intermediate"  # 応用
    ADVANCED = "advanced"  # 実践
    ALL = (BASIC, INTERMEDIATE, ADVANCED)


class CourseStatus:
    """講座の公開状態。"""

    DRAFT = "draft"  # 下書き
    PUBLISHED = "published"  # 公開中
    ALL = (DRAFT, PUBLISHED)


class CellType:
    """単元を構成するセルの種類。"""

    MARKDOWN = "markdown"  # 説明
    CODE = "code"  # 例題コード
    EXERCISE = "exercise"  # 演習(problems を参照する)
    ALL = (MARKDOWN, CODE, EXERCISE)


class ProblemKind:
    """問題の種類。"""

    EXERCISE = "exercise"  # 単元内の演習
    QUIZ = "quiz"  # 講座末の小テスト
    ALL = (EXERCISE, QUIZ)


class AnswerFormat:
    """問題の回答形式。"""

    CODE = "code"  # コードを書く
    CHOICE = "choice"  # 選択式
    NUMERIC = "numeric"  # 数値入力
    ALL = (CODE, CHOICE, NUMERIC)


class Grading:
    """コード問題の採点方式。"""

    OUTPUT = "output"  # 出力一致
    TEST = "test"  # テストコード(assert)
    ALL = (OUTPUT, TEST)


class VerifyStatus:
    """作成者による検証の状態。"""

    TODO = "todo"  # 未検証
    VERIFIED = "verified"  # 検証済み
    MISMATCH = "mismatch"  # AI の想定と不一致
    ALL = (TODO, VERIFIED, MISMATCH)
