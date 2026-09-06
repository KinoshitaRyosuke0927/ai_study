"""設計書分析 / コード分析の保存・取得(pipeline/analysis_store)のテスト。"""

from __future__ import annotations

from pipeline import analysis_store as store

DESIGN_FILES = [
    {"name": "b.md", "content": "# B\nbbb"},
    {"name": "a.md", "content": "# A\naaa"},
]


def _design_features() -> list[dict]:
    return [
        {
            "name": "ログイン",
            "overview": "利用者を認証する",
            "context_mode": "narrowed",
            "context_char_len": 120,
            "selected_section_ids": ["a.md::1"],
            "sections": [{"heading": "画面項目", "body": "- ID\n- パスワード"}],
            "refs": [
                {
                    "ref_kind": "design_section",
                    "file_path": "a.md",
                    "locator": "a.md::1",
                    "heading": "A",
                }
            ],
        },
        {
            "name": "失敗機能",
            "overview": "",
            "context_mode": "full",
            "context_char_len": 0,
            "selected_section_ids": [],
            "sections": [],
            "error": "この機能の詳細分析に失敗しました",
            "refs": [],
        },
    ]


def _code_features() -> list[dict]:
    return [
        {
            "name": "ユーザー取得",
            "overview": "1件返す",
            "context_mode": "narrowed",
            "context_char_len": 300,
            "selected_paths": ["app/main.py"],
            "selected_symbols": ["app/main.py::get_user"],
            "sections": [{"heading": "トリガー", "body": "GET /users/{id}"}],
            "refs": [
                {
                    "ref_kind": "code_symbol",
                    "file_path": "app/main.py",
                    "locator": "app/main.py::get_user",
                    "symbol_name": "get_user",
                    "start_line": 10,
                    "end_line": 18,
                    "heading": "def get_user",
                }
            ],
        }
    ]


def test_compute_content_hash_is_order_independent():
    h1 = store.compute_content_hash(DESIGN_FILES)
    h2 = store.compute_content_hash(list(reversed(DESIGN_FILES)))
    h3 = store.compute_content_hash(
        [{"name": "a.md", "content": "# A\nCHANGED"}, DESIGN_FILES[0]]
    )
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64


def test_save_and_get_round_trip(db_session):
    ch = store.compute_content_hash(DESIGN_FILES)
    saved = store.save_analysis(
        kind="design",
        repo="acme/app",
        branch="main",
        tree_sha="abc123",
        content_hash=ch,
        model="gpt-x",
        params={"max_context_chars": 100},
        stats={"section_count": 3, "analyzed_file_count": 2},
        features=_design_features(),
    )
    got = store.get_run(saved["id"])

    assert got["kind"] == "design" and got["repo"] == "acme/app"
    assert got["tree_sha"] == "abc123" and got["content_hash"] == ch
    assert got["stats"]["section_count"] == 3
    assert [f["name"] for f in got["features"]] == ["ログイン", "失敗機能"]

    f0 = got["features"][0]
    assert f0["sections"] == [{"heading": "画面項目", "body": "- ID\n- パスワード"}]
    assert f0["context_mode"] == "narrowed" and f0["context_char_len"] == 120
    assert f0["selected_section_ids"] == ["a.md::1"]
    assert f0["refs"][0]["file_path"] == "a.md"
    assert f0["refs"][0]["locator"] == "a.md::1"
    assert got["features"][1]["error"] == "この機能の詳細分析に失敗しました"


def test_code_refs_round_trip(db_session):
    ch = store.compute_content_hash([{"name": "app/main.py", "content": "x"}])
    saved = store.save_analysis(
        kind="code", repo="acme/app", branch="main", tree_sha=None,
        content_hash=ch, model="m", params={}, stats={}, features=_code_features(),
    )
    got = store.get_run(saved["id"])
    ref = got["features"][0]["refs"][0]
    assert ref["ref_kind"] == "code_symbol"
    assert ref["symbol_name"] == "get_user"
    assert ref["start_line"] == 10 and ref["end_line"] == 18
    assert got["features"][0]["selected_symbols"] == ["app/main.py::get_user"]


def test_find_cached_run_returns_latest_for_same_hash(db_session):
    ch = store.compute_content_hash(DESIGN_FILES)
    assert store.find_cached_run("design", ch) is None

    store.save_analysis(kind="design", repo="acme/app", branch="main", tree_sha=None,
                        content_hash=ch, model="m", params={}, stats={}, features=_design_features())
    r2 = store.save_analysis(kind="design", repo="acme/app", branch="main", tree_sha=None,
                             content_hash=ch, model="m", params={}, stats={}, features=_design_features())

    cached = store.find_cached_run("design", ch)
    assert cached["id"] == r2["id"]                     # 最新を返す
    assert store.find_cached_run("code", ch) is None    # kind 違いは別扱い
    assert store.find_cached_run("design", "0" * 64) is None


def test_latest_and_list_and_reverse_lookup(db_session):
    ch = store.compute_content_hash(DESIGN_FILES)
    store.save_analysis(kind="design", repo="acme/app", branch="main", tree_sha=None,
                        content_hash=ch, model="m", params={}, stats={}, features=_design_features())
    store.save_analysis(kind="code", repo="acme/app", branch="main", tree_sha=None,
                        content_hash="x" * 64, model="m", params={}, stats={}, features=_code_features())

    latest = store.get_latest_run("design", "acme/app")
    assert latest["kind"] == "design"

    runs = store.list_runs(kind="design")
    assert len(runs) == 1 and runs[0]["feature_count"] == 2

    # 参照先(ファイル)から、それを参照している機能を逆引きできる
    hits = store.find_feature_refs(file_path="a.md")
    assert len(hits) == 1
    assert hits[0]["feature_name"] == "ログイン" and hits[0]["run_kind"] == "design"
