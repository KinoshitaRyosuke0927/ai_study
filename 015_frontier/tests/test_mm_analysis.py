"""Mattermost 情報解析の AI 処理(pipeline/mm_analysis)のテスト。"""

from __future__ import annotations

import pytest

from pipeline import mm_analysis as mma
from config.settings import Settings


def _settings(**over) -> Settings:
    base = dict(
        AZURE_OPENAI_ENDPOINT="https://example/openai/v1",
        AZURE_OPENAI_API_KEY="key-xxx",
    )
    base.update(over)
    return Settings(_env_file=None, **base)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        message = type("M", (), {"content": content})()
        choice = type("C", (), {"message": message})()
        self.choices = [choice]
        self.usage = None


def _patch_client(monkeypatch, content: str) -> list[dict]:
    calls: list[dict] = []

    class _FakeClient:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                def create(**kwargs):
                    calls.append(kwargs)
                    return _FakeResponse(content)

    monkeypatch.setattr(mma, "_build_client", lambda settings: _FakeClient())
    return calls


ACCOUNT = {
    "username": "alice",
    "stats": {"post_count": 12, "channel_count": 3, "active_days": 5},
    "context": "[2026-09-01 10:00] #dev バグを直しました\n[2026-09-02 09:00] #ops デプロイ完了",
}


def test_analyze_account_parses_and_uses_context(monkeypatch):
    calls = _patch_client(
        monkeypatch,
        '{"overview": "報告中心のアカウント", '
        '"sections": [{"heading": "傾向", "body": "- 進捗報告が多い"}, {"heading": "", "body": ""}]}',
    )
    out = mma.analyze_account(_settings(), ACCOUNT, ["デプロイ", "バグ修正"])

    assert out["overview"] == "報告中心のアカウント"
    assert out["sections"] == [{"heading": "傾向", "body": "- 進捗報告が多い"}]
    up = calls[0]["messages"][1]["content"]
    assert "alice" in up and "バグを直しました" in up and "デプロイ" in up


def test_analyze_account_requires_ai_config():
    s = Settings(_env_file=None, AZURE_OPENAI_API_KEY="changeme")
    with pytest.raises(mma.MmAnalysisError):
        mma.analyze_account(s, ACCOUNT, [])


def test_list_team_topics(monkeypatch):
    monkeypatch.setattr(
        mma, "_call_chat",
        lambda s, sp, up, label="": {"topics": ["注文量予測", "  ", "気象データ"]},
    )
    contexts = [{"username": "alice", "stats": ACCOUNT["stats"], "context": "x"}]
    assert mma.list_team_topics(_settings(), contexts) == ["注文量予測", "気象データ"]


def test_list_team_topics_returns_empty_without_ai():
    s = Settings(_env_file=None, AZURE_OPENAI_API_KEY="changeme")
    assert mma.list_team_topics(s, [{"username": "a", "stats": {}, "context": "x"}]) == []


def test_list_team_topics_swallows_ai_error(monkeypatch):
    def _boom(*a, **k):
        raise mma.MmAnalysisError("boom")

    monkeypatch.setattr(mma, "_call_chat", _boom)
    contexts = [{"username": "a", "stats": ACCOUNT["stats"], "context": "x"}]
    assert mma.list_team_topics(_settings(), contexts) == []
