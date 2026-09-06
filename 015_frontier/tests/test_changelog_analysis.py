"""変更履歴取得の AI 処理(pipeline/changelog_analysis)のテスト。"""

from __future__ import annotations

import pytest

from pipeline import changelog_analysis as ca
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

    monkeypatch.setattr(ca, "_build_client", lambda settings: _FakeClient())
    return calls


AUTHOR = {
    "author": "alice", "author_name": "Alice",
    "stats": {"commit_count": 12, "additions": 300, "deletions": 40,
              "files_touched": 8, "top_files": ["app/auth.py", "app/main.py"]},
    "context": "=== コミット履歴(時系列)===\n[2026-08-01 10:00] ログイン追加  (+40/-0, 1ファイル) app/auth.py",
}


def test_analyze_author_parses_and_uses_context(monkeypatch):
    calls = _patch_client(
        monkeypatch,
        '{"overview": "認証まわり担当", "sections": [{"heading": "担当領域", "body": "- 認証"}, {"heading":"","body":""}]}',
    )
    out = ca.analyze_author(_settings(), AUTHOR, ["ログイン改修"])
    assert out["overview"] == "認証まわり担当"
    assert out["sections"] == [{"heading": "担当領域", "body": "- 認証"}]
    up = calls[0]["messages"][1]["content"]
    assert "alice" in up and "ログイン追加" in up and "ログイン改修" in up
    assert "app/auth.py" in up  # top_files が統計に載る


def test_analyze_author_requires_ai_config():
    s = Settings(_env_file=None, AZURE_OPENAI_API_KEY="changeme")
    with pytest.raises(ca.ChangelogAnalysisError):
        ca.analyze_author(s, AUTHOR, [])


def test_list_repo_themes(monkeypatch):
    monkeypatch.setattr(
        ca, "_call_chat",
        lambda s, sp, up, label="": {"themes": ["ログイン改修", "  ", "テスト整備"]},
    )
    commits = [{"message": "ログイン追加\n詳細"}, {"message": "テスト追加"}]
    assert ca.list_repo_themes(_settings(), commits) == ["ログイン改修", "テスト整備"]


def test_list_repo_themes_empty_without_ai():
    s = Settings(_env_file=None, AZURE_OPENAI_API_KEY="changeme")
    assert ca.list_repo_themes(s, [{"message": "x"}]) == []


def test_list_repo_themes_swallows_error(monkeypatch):
    def _boom(*a, **k):
        raise ca.ChangelogAnalysisError("boom")

    monkeypatch.setattr(ca, "_call_chat", _boom)
    assert ca.list_repo_themes(_settings(), [{"message": "x"}]) == []
