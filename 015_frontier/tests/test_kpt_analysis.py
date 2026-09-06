"""KPT分析の AI 処理(pipeline/kpt_analysis)のテスト。"""

from __future__ import annotations

import pytest

from config.settings import Settings
from pipeline import kpt_analysis as kpta


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

    monkeypatch.setattr(kpta, "_build_client", lambda settings: _FakeClient())
    return calls


MM = {
    "id": 1, "topics": ["仕様確認", "リリース調整"], "stats": {"post_count": 40, "channels": ["a"]},
    "accounts": [
        {"username": "m-unno", "overview": "報告と確認が中心",
         "sections": [
             {"heading": "発言の傾向", "body": "- レビュー依頼と日程調整が多い。調整役。" * 40},
             {"heading": "扱う話題", "body": "- 予測運用と1次リリース"},
         ], "stats": {"post_count": 20}},
    ],
}
TR = {
    "id": 2, "themes": ["バックログ整理"], "stats": {"card_count": 30},
    "accounts": [{"username": "munno3", "overview": "整理役",
                  "sections": [{"heading": "関わるボード", "body": "スプリント1/2 の in review が滞留"}]}],
}
CL = {
    "id": 3, "themes": ["設定まわりの変更"], "stats": {"commit_count": 12},
    "accounts": [{"username": "unno", "overview": "設定を触る", "sections": []}],
}
GH = {
    "repo": "org/repo", "activity_total": 50, "branch_count": 4, "pr_count": 10,
    "by_actor": [{"actor": "unno", "total": 20, "commit": 12, "pr_opened": 3, "pr_merged": 3, "pr_comment": 2, "pr_review": 0}],
}
SD = {
    "diff_id": 7, "diff_count": 3, "stats": {"pair_count": 8},
    "items": [
        {"feature_name": "ログイン", "verdict": "conflict", "severity": "high", "summary": "認証方式が設計と異なる"},
        {"feature_name": "検索", "verdict": "design_only", "severity": "low", "summary": "未実装"},
    ],
}
UA = {
    "id": 9,
    "stats": {"member_count": 2, "other_count": 1},
    "items": [
        {"is_member": True, "display_name": "浅野間 龍児", "personal": "スクラムマスター",
         "overview": "調整役として進捗整理・日程調整・レビュー依頼を回している。",
         "sections": [{"heading": "チーム内での関わり方", "body": "レビュー依頼のハブ。木下へレビューが集中。"}]},
        {"is_member": True, "display_name": "木下 涼介", "personal": "実装担当",
         "overview": "実装の中核。レビュー対応も多い。",
         "sections": [{"heading": "気になる点", "body": "レビュー負荷が高く、着手前の方針確認が省略されがち。"}]},
        {"is_member": False, "display_name": "copilot[bot]", "personal": "",
         "overview": "", "sections": []},
    ],
}
TOOL_CTX = {"mattermost": "AIS_業務連絡: 連絡", "trello": "のみどき: 管理", "github": "repo: 本体"}


def test_build_bundle_digests_all_sources():
    b = kpta.build_bundle(MM, TR, CL, GH, SD, UA, TOOL_CTX)
    assert set(b["available"]) == {"user_activity", "mattermost", "trello", "github", "changelog", "spec_diff"}
    # run-level のトピック/テーマが入る
    assert b["sources"]["mattermost"]["topics"] == ["仕様確認", "リリース調整"]
    assert b["sources"]["trello"]["topics"] == ["バックログ整理"]
    # アカウント別分析はセクション本文まで残す(見出しだけにしない)
    sec = b["sources"]["mattermost"]["accounts"][0]["sections"][0]
    assert sec["heading"] == "発言の傾向" and "調整役" in sec["body"]
    assert len(sec["body"]) <= kpta.MAX_SECTION_BODY_CHARS
    # アクティビティ分析(メンバー別)がソースに入る
    people = b["sources"]["user_activity"]["people"]
    assert [p["name"] for p in people] == ["浅野間 龍児", "木下 涼介"]  # 空の人は除外
    assert "レビュー負荷" in people[1]["sections"][0]["body"]
    # 配列やネストの統計値は落とす
    assert "channels" not in b["sources"]["mattermost"]["stats"]
    assert b["sources"]["mattermost"]["stats"]["post_count"] == 40
    # spec_diff は重大度順に並ぶ
    assert b["sources"]["spec_diff"]["items"][0]["severity"] == "high"
    assert b["sources"]["spec_diff"]["severity_counts"]["high"] == 1
    # GitHub 集計
    assert b["sources"]["github"]["by_actor"][0]["actor"] == "unno"
    assert b["tool_context"]["mattermost"].startswith("AIS_業務連絡")


def test_build_bundle_handles_missing_sources():
    b = kpta.build_bundle(None, None, None, None, None, None, None)
    assert b["available"] == []
    assert all(v is None for v in b["sources"].values())


def test_build_user_prompt_mentions_sources():
    up = kpta.build_user_prompt(kpta.build_bundle(MM, TR, CL, GH, SD, UA, TOOL_CTX))
    assert "Mattermost情報分析" in up and "実装差分解析" in up
    assert "アクティビティ分析(メンバー別)" in up
    assert "仕様確認" in up and "認証方式が設計と異なる" in up
    assert "レビュー負荷" in up  # user_activity のセクション本文が渡る
    assert "業務・プロセス面" in up
    assert "AIS_業務連絡" in up


def test_analyze_kpt_parses_and_normalizes(monkeypatch):
    calls = _patch_client(
        monkeypatch,
        '{"keep": [{"title": "レビュー文化", "detail": "PR レビューが活発", '
        '"evidence": "GitHub でレビュー多数", "sources": ["github", "bogus"]}], '
        '"problem": [{"title": "レビュー負荷の偏り", "detail": "", "evidence": "木下に集中", "sources": ["user_activity", "mattermost"]}], '
        '"try": [{"title": "", "detail": ""}, {"title": "レビュー担当のローテーション", "sources": ["user_activity"]}]}',
    )
    out = kpta.analyze_kpt(_settings(), kpta.build_bundle(MM, TR, CL, GH, SD, UA, TOOL_CTX))
    assert [i["title"] for i in out["keep"]] == ["レビュー文化"]
    # 未知のソースキーは除外される
    assert out["keep"][0]["sources"] == ["github"]
    assert out["problem"][0]["title"] == "レビュー負荷の偏り"
    # user_activity は有効なソースキーとして残る
    assert out["problem"][0]["sources"] == ["user_activity", "mattermost"]
    # title/detail 空の項目は捨てられる
    assert [i["title"] for i in out["try"]] == ["レビュー担当のローテーション"]
    assert "アクティビティ分析" in calls[0]["messages"][1]["content"]


def test_analyze_kpt_requires_ai_config():
    s = Settings(_env_file=None, AZURE_OPENAI_API_KEY="changeme")
    with pytest.raises(kpta.KptAnalysisError):
        kpta.analyze_kpt(s, kpta.build_bundle(MM, None, None, None, None, None, None))


def test_analyze_kpt_requires_material(monkeypatch):
    _patch_client(monkeypatch, "{}")
    with pytest.raises(kpta.KptAnalysisError):
        kpta.analyze_kpt(_settings(), kpta.build_bundle(None, None, None, None, None, None, None))


def test_analyze_kpt_bad_json_raises(monkeypatch):
    _patch_client(monkeypatch, "not json")
    with pytest.raises(kpta.KptAnalysisError):
        kpta.analyze_kpt(_settings(), kpta.build_bundle(MM, None, None, None, None, None, None))
