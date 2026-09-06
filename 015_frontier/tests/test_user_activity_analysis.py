"""アクティビティ分析の AI 処理(pipeline/user_activity_analysis)のテスト。"""

from __future__ import annotations

import pytest

from pipeline import user_activity_analysis as uaa
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

    monkeypatch.setattr(uaa, "_build_client", lambda settings: _FakeClient())
    return calls


BUNDLE = {
    "name": "海野 亮", "personal": "PO として評価を行う", "is_member": True,
    "accounts": {"mattermost": "m-unno", "trello": "munno3", "github": "JBD-Makoto-Unno"},
    "sources": {
        "mattermost": {"overview": "報告と確認が中心", "sections": [{"heading": "傾向", "body": "- 仕様確認が多い"}], "stats": {"post_count": 20}},
        "trello": {"overview": "バックログ整理", "sections": [], "stats": {"comment_count": 5}},
        "changelog": {"overview": "設定まわりを変更", "sections": [], "stats": {"commit_count": 4}},
        "github": {"actor": "JBD-Makoto-Unno", "tally": {"pr_merged": 4, "pr_review": 5, "commit": 3},
                   "recent": [{"kind_label": "レビュー", "occurred_at": "2026-09-01T10:00:00", "pr_number": 12,
                               "summary": "レビュー", "body_excerpt": "LGTM"}]},
    },
}
TOOL_CTX = {"mattermost": "AIS_業務連絡: 開発メンバーの連絡", "trello": "のみどき: 開発管理", "github": "Nomidoki: 本体リポジトリ"}


def test_build_user_prompt_includes_all_sources():
    up = uaa.build_user_prompt(BUNDLE, TOOL_CTX)
    assert "海野 亮" in up and "PO として評価を行う" in up
    assert "m-unno" in up and "munno3" in up and "JBD-Makoto-Unno" in up
    assert "報告と確認が中心" in up and "バックログ整理" in up and "設定まわりを変更" in up
    assert "マージ 4" in up and "レビュー 5" in up
    assert "AIS_業務連絡" in up  # ツール運用方法


def test_analyze_user_parses(monkeypatch):
    calls = _patch_client(
        monkeypatch,
        '{"overview": "PO として仕様評価とレビューを担う", '
        '"sections": [{"heading": "役割", "body": "- 仕様確認"}, {"heading": "", "body": ""}]}',
    )
    out = uaa.analyze_user(_settings(), BUNDLE, TOOL_CTX)
    assert out["overview"] == "PO として仕様評価とレビューを担う"
    assert out["sections"] == [{"heading": "役割", "body": "- 仕様確認"}]
    assert "海野 亮" in calls[0]["messages"][1]["content"]


def test_analyze_user_requires_ai_config():
    s = Settings(_env_file=None, AZURE_OPENAI_API_KEY="changeme")
    with pytest.raises(uaa.UserActivityAnalysisError):
        uaa.analyze_user(s, BUNDLE, TOOL_CTX)


def test_analyze_user_bad_json_raises(monkeypatch):
    _patch_client(monkeypatch, "not json")
    with pytest.raises(uaa.UserActivityAnalysisError):
        uaa.analyze_user(_settings(), BUNDLE, TOOL_CTX)
