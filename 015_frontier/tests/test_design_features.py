"""「設計書情報取得」画面の「機能分析」ロジック(2 段階 + セクション絞り込み)のテスト。"""

from __future__ import annotations

import pytest

from pipeline import design_features as df
from pipeline.design_features import (
    DesignFeatureAnalysisError,
    analyze_feature_detail,
    list_features,
    plan_analysis,
    split_sections,
)
from config.settings import Settings


def _settings(**over) -> Settings:
    # AI 接続情報が揃った状態の Settings(実際の通信はモックで置き換える)
    base = dict(
        AZURE_OPENAI_ENDPOINT="https://example/openai/v1",
        AZURE_OPENAI_API_KEY="key-xxx",
    )
    base.update(over)
    return Settings(_env_file=None, **base)


class _FakeResponse:
    """OpenAI クライアントの戻り値を模したオブジェクト。"""

    def __init__(self, content: str) -> None:
        message = type("M", (), {"content": content})()
        choice = type("C", (), {"message": message})()
        self.choices = [choice]
        self.usage = None


def _patch_client(monkeypatch, content: str) -> list[dict]:
    """_build_client を差し替え、create に渡された引数を毎回記録して返す。"""
    calls: list[dict] = []

    class _FakeClient:
        class chat:  # noqa: N801 - OpenAI SDK の構造に合わせる
            class completions:  # noqa: N801
                @staticmethod
                def create(**kwargs):
                    calls.append(kwargs)
                    return _FakeResponse(content)

    monkeypatch.setattr(df, "_build_client", lambda settings: _FakeClient())
    return calls


# 見出しあり・親子関係あり・本文が長い(共通判定を回避する)ファイル
MD_A = (
    "序文の説明テキスト\n\n"
    "# 機能A\nAの概要説明\n\n"
    "## A詳細\nAのロジックが長々と書いてある。" + "x" * 1600 + "\n\n"
    "# 機能B\nBの概要説明\n"
)
# ファイル名で共通ドキュメントと判定されるファイル(小さい)
MD_GLOSSARY = "# 用語集\n用語の定義がここにある\n"
FILES = [
    {"name": "a.md", "content": MD_A},
    {"name": "glossary.md", "content": MD_GLOSSARY},
]


# --- セクション分割 ---
def test_split_sections_builds_headings_and_paths():
    secs = split_sections(FILES)
    a_secs = [s for s in secs if s["file"] == "a.md"]
    # 先頭部 + 機能A + A詳細 + 機能B
    assert [s["heading"] for s in a_secs] == ["(先頭)", "機能A", "A詳細", "機能B"]
    assert a_secs[0]["id"] == "a.md::0"
    # 親見出しが heading_path に連結される
    detail = next(s for s in a_secs if s["heading"] == "A詳細")
    assert detail["heading_path"] == "機能A > A詳細"
    # 大きい a.md は共通ではない / glossary.md は名前で共通
    assert a_secs[1]["is_common"] is False
    assert all(s["is_common"] for s in secs if s["file"] == "glossary.md")


# --- 1 回目: 機能の洗い出し + section_ids 検証 ---
def test_list_features_validates_section_ids(monkeypatch):
    calls = _patch_client(
        monkeypatch,
        '{"features": [{"name": "機能A", "summary": "A", '
        '"section_ids": ["a.md::2", "ghost::9", "a.md::1"]}, '
        '{"name": "", "summary": ""}]}',
    )
    secs = split_sections(FILES)
    out = list_features(_settings(), FILES, secs)

    # 実在しない ID は捨てられ、空要素も除外される
    assert out == [{"name": "機能A", "summary": "A", "section_ids": ["a.md::2", "a.md::1"]}]
    # 全文とアウトライン(section_id)の両方をプロンプトへ渡している
    user_prompt = calls[0]["messages"][1]["content"]
    assert "セクションアウトライン" in user_prompt and "a.md::2" in user_prompt


def test_list_features_requires_ai_config():
    s = Settings(_env_file=None, AZURE_OPENAI_API_KEY="changeme")
    with pytest.raises(DesignFeatureAnalysisError):
        list_features(s, FILES, split_sections(FILES))


def test_list_features_bad_json_raises(monkeypatch):
    _patch_client(monkeypatch, "これは JSON ではありません")
    with pytest.raises(DesignFeatureAnalysisError):
        list_features(_settings(), FILES, split_sections(FILES))


# --- plan_analysis: 2 回目用コンテキストの組み立て ---
def _patch_call_chat(monkeypatch, features: list[dict]) -> None:
    """1 回目の _call_chat を、指定した features を返すよう差し替える。"""
    monkeypatch.setattr(
        df, "_call_chat", lambda settings, sys_p, usr_p, label="": {"features": features}
    )


def test_plan_analysis_narrows_context_and_always_includes_common(monkeypatch):
    _patch_call_chat(
        monkeypatch,
        [{"name": "機能A", "summary": "A", "section_ids": ["a.md::2"]}],
    )
    plan = plan_analysis(_settings(), FILES)
    feat = plan["features"][0]

    assert feat["context_mode"] == "narrowed"
    # 選択セクション(A詳細)とその親(機能A)は含む
    assert "Aのロジック" in feat["context"]
    assert "Aの概要説明" in feat["context"]
    # 共通ドキュメント(用語集)は常に添付される
    assert "用語の定義" in feat["context"]
    # 無関係セクション(機能B)は含まない
    assert "Bの概要説明" not in feat["context"]
    assert plan["common_section_ids"] and "glossary.md::0" in plan["common_section_ids"]


def test_plan_analysis_falls_back_to_full_when_selection_is_thin(monkeypatch):
    # section_ids が空/不正 → 抜粋が薄いので設計書全文へフォールバック
    _patch_call_chat(
        monkeypatch,
        [{"name": "機能X", "summary": "x", "section_ids": ["ghost::0"]}],
    )
    plan = plan_analysis(_settings(), FILES)
    feat = plan["features"][0]

    assert feat["context_mode"] == "full"
    # 全文なので機能A・機能B の両方が含まれる
    assert "Aのロジック" in feat["context"] and "Bの概要説明" in feat["context"]


# --- 2 回目: 機能ごとの詳細仕様 ---
def test_analyze_feature_detail_uses_context(monkeypatch):
    calls = _patch_client(
        monkeypatch,
        '```json\n{"name": "機能A", "overview": "利用者を認証する", '
        '"sections": [{"heading": "画面項目", "body": "- ID\\n- パスワード"}, '
        '{"heading": "", "body": ""}]}\n```',
    )
    out = analyze_feature_detail(
        _settings(),
        {"name": "機能A", "summary": "A", "context": "### a.md — 機能A\n認証の本文ここ"},
    )

    assert out["name"] == "機能A"
    assert out["overview"] == "利用者を認証する"
    assert out["sections"] == [{"heading": "画面項目", "body": "- ID\n- パスワード"}]
    # 抜粋コンテキストと対象機能名がプロンプトに含まれる
    user_prompt = calls[0]["messages"][1]["content"]
    assert "認証の本文ここ" in user_prompt and "対象機能" in user_prompt


def test_analyze_feature_detail_falls_back_to_feature_fields(monkeypatch):
    _patch_client(monkeypatch, '{"sections": []}')
    out = analyze_feature_detail(
        _settings(), {"name": "日次集計", "summary": "日次で集計する", "context": "本文"}
    )
    assert out["name"] == "日次集計"
    assert out["overview"] == "日次で集計する"
    assert out["sections"] == []


def test_analyze_feature_detail_requires_ai_config():
    s = Settings(_env_file=None, AZURE_OPENAI_API_KEY="changeme")
    with pytest.raises(DesignFeatureAnalysisError):
        analyze_feature_detail(s, {"name": "x", "summary": "", "context": "y"})
