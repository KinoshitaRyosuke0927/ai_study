"""実装差分解析(pipeline/spec_code_diff)と、その保存(analysis_store)のテスト。"""

from __future__ import annotations

import pytest

from pipeline import analysis_store as store
from pipeline import spec_code_diff as scd
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

    monkeypatch.setattr(scd, "_build_client", lambda settings: _FakeClient())
    return calls


DESIGN_FEATURES = [
    {
        "id": 11, "name": "ログイン", "overview": "利用者を認証する",
        "sections": [{"heading": "入力", "body": "ID とパスワード"}],
        "refs": [{"ref_kind": "design_section", "file_path": "auth.md",
                  "locator": "auth.md::1", "heading": "ログイン"}],
    },
    {
        "id": 12, "name": "パスワード再発行", "overview": "メールで再発行リンクを送る",
        "sections": [], "refs": [],
    },
]
CODE_FEATURES = [
    {
        "id": 21, "name": "サインイン", "overview": "認証してセッションを張る",
        "sections": [{"heading": "トリガー", "body": "POST /login"}],
        "refs": [{"ref_kind": "code_symbol", "file_path": "app/auth.py",
                  "locator": "app/auth.py::login", "symbol_name": "login",
                  "start_line": 20, "end_line": 40}],
    },
    {
        "id": 22, "name": "監査ログ出力", "overview": "操作を監査ログに書く",
        "sections": [], "refs": [],
    },
]


# --- 対応付け ---
def test_pair_features_matches_by_name_and_computes_unmatched(monkeypatch):
    monkeypatch.setattr(
        scd, "_call_chat",
        lambda s, sp, up, label="": {
            "pairs": [{"design": "ログイン", "code": "サインイン"},
                      {"design": "ghost", "code": "サインイン"}],  # 2件目は無効(名前不一致/重複)
            "design_only": [], "code_only": [],
        },
    )
    out = scd._pair_features(_settings(), DESIGN_FEATURES, CODE_FEATURES)

    assert [(d["id"], c["id"]) for d, c in out["pairs"]] == [(11, 21)]
    # ペアに含まれなかったものが unmatched
    assert [f["id"] for f in out["design_only"]] == [12]
    assert [f["id"] for f in out["code_only"]] == [22]


# --- ペアの相違点抽出 ---
def test_diff_pair_parses_and_attaches_evidence(monkeypatch):
    calls = _patch_client(
        monkeypatch,
        '{"differences": [{"severity": "high", "summary": "認証方式が違う", '
        '"design_state": "ID+パスワード", "code_state": "OAuth のみ"}, '
        '{"severity": "bogus", "summary": "セッション期限の記載差"}, '
        '{"summary": ""}]}',
    )
    items = scd.diff_pair(_settings(), DESIGN_FEATURES[0], CODE_FEATURES[0])

    assert len(items) == 2  # summary 空は除外
    a, b = items
    assert a["verdict"] == "conflict" and a["severity"] == "high"
    assert a["design_feature_id"] == 11 and a["code_feature_id"] == 21
    assert a["evidence"]["design"][0]["file_path"] == "auth.md"
    assert a["evidence"]["code"][0]["symbol_name"] == "login"
    assert b["severity"] == "mid"  # 不正な severity は mid に丸める
    # プロンプトに双方の仕様テキストが入っている
    up = calls[0]["messages"][1]["content"]
    assert "ID とパスワード" in up and "POST /login" in up


def test_unmatched_item_shapes():
    d = scd.unmatched_item(DESIGN_FEATURES[1], "design_only")
    assert d["verdict"] == "design_only" and d["design_feature_id"] == 12
    assert d["code_state"] == "コードに実装なし"
    c = scd.unmatched_item(CODE_FEATURES[1], "code_only")
    assert c["verdict"] == "code_only" and c["code_feature_id"] == 22
    assert c["design_state"] == "設計書に記載なし"


def test_diff_pair_requires_ai_config():
    s = Settings(_env_file=None, AZURE_OPENAI_API_KEY="changeme")
    with pytest.raises(scd.SpecCodeDiffError):
        scd.diff_pair(s, DESIGN_FEATURES[0], CODE_FEATURES[0])


# --- 保存・取得 ---
def _sample_items() -> list[dict]:
    return [
        {
            "feature_name": "ログイン", "verdict": "conflict", "severity": "high",
            "summary": "認証方式が違う", "design_state": "ID+PW", "code_state": "OAuth",
            "design_feature_id": 11, "code_feature_id": 21,
            "evidence": {"design": [{"file_path": "auth.md"}], "code": [{"file_path": "app/auth.py"}]},
        },
        {
            "feature_name": "監査ログ出力", "verdict": "code_only", "severity": "mid",
            "summary": "設計書に記載なし", "design_state": "設計書に記載なし",
            "code_state": "操作を監査ログに書く",
            "design_feature_id": None, "code_feature_id": 22, "evidence": {"design": [], "code": []},
        },
    ]


def test_save_and_get_diff_round_trip(db_session):
    saved = store.save_diff(
        repo="acme/app", design_run_id=1, code_run_id=2, model="m",
        stats={"pair_count": 1}, items=_sample_items(),
    )
    got = store.get_diff(saved["id"])
    assert got["repo"] == "acme/app" and got["diff_count"] == 2
    assert got["design_run_id"] == 1 and got["code_run_id"] == 2
    assert [it["verdict"] for it in got["items"]] == ["conflict", "code_only"]
    assert got["items"][0]["evidence"]["code"][0]["file_path"] == "app/auth.py"
    assert got["items"][1]["code_feature_id"] == 22


def test_latest_diff_and_list(db_session):
    store.save_diff(repo="acme/app", design_run_id=1, code_run_id=2, model="m",
                    stats={}, items=_sample_items())
    s2 = store.save_diff(repo="acme/app", design_run_id=3, code_run_id=4, model="m",
                         stats={}, items=_sample_items()[:1])

    latest = store.get_latest_diff()
    assert latest["id"] == s2["id"] and latest["diff_count"] == 1

    rows = store.list_diffs()
    assert len(rows) == 2 and rows[0]["id"] == s2["id"]
    assert "items" not in rows[0]  # 一覧は本体を含めない
