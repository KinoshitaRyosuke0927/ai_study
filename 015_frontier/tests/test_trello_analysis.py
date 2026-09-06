"""Trello 情報解析の AI 処理(pipeline/trello_analysis)のテスト。"""

from __future__ import annotations

import pytest

from pipeline import trello_analysis as ta
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

    monkeypatch.setattr(ta, "_build_client", lambda settings: _FakeClient())
    return calls


ACCOUNT = {
    "username": "alice", "full_name": "Alice A",
    "stats": {"comment_count": 5, "assigned_cards": 3, "board_count": 2},
    "context": "=== コメント・操作(時系列)===\n[2026-08-01] #開発 / 作業中 / ログイン改修 コメント: レビュー依頼",
}


def test_analyze_account_parses_and_uses_context(monkeypatch):
    calls = _patch_client(
        monkeypatch,
        '{"overview": "レビュー役", "sections": [{"heading": "役割", "body": "- レビュー中心"}, {"heading":"","body":""}]}',
    )
    out = ta.analyze_account(_settings(), ACCOUNT, ["ログイン改修"])
    assert out["overview"] == "レビュー役"
    assert out["sections"] == [{"heading": "役割", "body": "- レビュー中心"}]
    up = calls[0]["messages"][1]["content"]
    assert "alice" in up and "レビュー依頼" in up and "ログイン改修" in up


def test_analyze_account_requires_ai_config():
    s = Settings(_env_file=None, AZURE_OPENAI_API_KEY="changeme")
    with pytest.raises(ta.TrelloAnalysisError):
        ta.analyze_account(s, ACCOUNT, [])


def test_list_team_themes(monkeypatch):
    monkeypatch.setattr(
        ta, "_call_chat",
        lambda s, sp, up, label="": {"themes": ["ログイン改修", "  ", "デプロイ整備"]},
    )
    cards = [{"board_name": "開発", "list_name": "作業中", "name": "ログイン改修"}]
    assert ta.list_team_themes(_settings(), cards) == ["ログイン改修", "デプロイ整備"]


def test_list_team_themes_empty_without_ai():
    s = Settings(_env_file=None, AZURE_OPENAI_API_KEY="changeme")
    assert ta.list_team_themes(s, [{"board_name": "b", "list_name": "l", "name": "x"}]) == []


def test_list_team_themes_swallows_error(monkeypatch):
    def _boom(*a, **k):
        raise ta.TrelloAnalysisError("boom")

    monkeypatch.setattr(ta, "_call_chat", _boom)
    cards = [{"board_name": "b", "list_name": "l", "name": "x"}]
    assert ta.list_team_themes(_settings(), cards) == []
