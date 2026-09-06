"""「コード情報取得」画面の「機能分析」ロジック(2 段階 + ファイル絞り込み)のテスト。"""

from __future__ import annotations

import pytest

from pipeline import code_features as cf
from pipeline.code_features import (
    CodeAnalysisError,
    analyze_feature_detail,
    build_code_outline,
    list_features,
    plan_analysis,
)
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

    monkeypatch.setattr(cf, "_build_client", lambda settings: _FakeClient())
    return calls


APP_PY = (
    '"""アプリ本体。"""\n'
    "from fastapi import FastAPI\n"
    "app = FastAPI()\n\n"
    "@app.get('/users/{uid}')\n"
    "def get_user(uid: int):\n"
    "    return db_fetch(uid)\n\n"
    "@app.post('/users')\n"
    "def create_user(body: dict):\n"
    "    " + "x = 1\n    " * 400 + "return 1\n"
)
MODELS_PY = "class User:\n    id: int\n    name: str\n"
UTIL_JS = "export function greet(name){ return 'hi ' + name }\n"
FILES = [
    {"name": "app/main.py", "content": APP_PY},
    {"name": "app/models.py", "content": MODELS_PY},
    {"name": "web/util.js", "content": UTIL_JS},
]


# --- コードアウトライン / シンボル索引 ---
def test_build_code_outline_extracts_symbols():
    outline = build_code_outline(FILES)
    assert "app/main.py" in outline
    # Python: docstring・ルートデコレータ・関数名
    assert "# アプリ本体。" in outline
    assert "@app.get('/users/{uid}') def get_user" in outline
    assert "class User" in outline
    # JS: 正規表現でのシンボル抽出
    assert "def greet" in outline


def test_scan_code_builds_symbol_index_with_source():
    _outline, index = cf._scan_code(FILES)
    key = "app/main.py::create_user"
    assert key in index
    entry = index[key]
    assert entry["file"] == "app/main.py" and entry["kind"] == "func"
    assert isinstance(entry["start"], int) and entry["end"] > entry["start"]
    # 関数の全文(末尾の return まで)が入っている
    assert "def create_user" in entry["source"] and "return 1" in entry["source"]
    assert "app/models.py::User" in index


# --- 1 回目: file_paths / symbols の検証 ---
def test_list_features_resolves_paths_and_symbols(monkeypatch):
    calls = _patch_client(
        monkeypatch,
        '{"features": [{"name": "ユーザー取得", "summary": "1件取得", '
        '"file_paths": ["./app/main.py", "ghost/x.py"], '
        '"symbols": ["app/main.py::get_user", "models.py::User", "app/main.py::ghost"]}]}',
    )
    outline, index = cf._scan_code(FILES)
    out = list_features(_settings(), FILES, outline, index)

    assert out[0]["name"] == "ユーザー取得"
    # 実在しないシンボルは除外 / パス表記ゆれ(models.py)は末尾一致で解決
    assert out[0]["symbols"] == ["app/main.py::get_user", "app/models.py::User"]
    # シンボルの属するファイルは file_paths にも取り込まれる
    assert set(out[0]["file_paths"]) == {"app/main.py", "app/models.py"}
    assert "コードアウトライン" in calls[0]["messages"][1]["content"]


def test_list_features_requires_ai_config():
    s = Settings(_env_file=None, AZURE_OPENAI_API_KEY="changeme")
    with pytest.raises(CodeAnalysisError):
        list_features(s, FILES, "outline", {})


def test_list_features_bad_json_raises(monkeypatch):
    _patch_client(monkeypatch, "not json")
    with pytest.raises(CodeAnalysisError):
        list_features(_settings(), FILES, "outline", {})


# --- plan_analysis: 2 回目用コンテキストの組み立て ---
def _patch_call_chat(monkeypatch, features: list[dict]) -> None:
    monkeypatch.setattr(
        cf, "_call_chat", lambda settings, sys_p, usr_p, label="": {"features": features}
    )


def test_plan_analysis_narrows_to_selected_symbols_plus_core(monkeypatch):
    _patch_call_chat(
        monkeypatch,
        [{"name": "ユーザー作成", "summary": "作成",
          "file_paths": ["app/main.py"],
          "symbols": ["app/main.py::create_user"]}],
    )
    plan = plan_analysis(_settings(), FILES)
    feat = plan["features"][0]

    assert feat["context_mode"] == "narrowed"
    assert feat["selected_symbols"] == ["app/main.py::create_user"]
    # 選択した関数の全文(末尾の return まで)が入る
    assert "def create_user" in feat["context"] and "return 1" in feat["context"]
    # 同ファイルの定義一覧(スケルトン)に get_user が出る(全文は入れない)
    assert "def get_user" in feat["context"]
    # コアファイル(models.py)は常に添付される
    assert "app/models.py" in feat["context"] and "class User" in feat["context"]
    # 無関係ファイル(web/util.js)は含まれない
    assert "web/util.js" not in feat["context"]
    assert "app/models.py" in plan["core_paths"]
    assert plan["symbol_count"] >= 3


def test_plan_analysis_falls_back_to_entrypoints_when_thin(monkeypatch):
    # 選択シンボルが小さい定義だけ → 抜粋が薄いので entrypoint 群へフォールバック
    _patch_call_chat(
        monkeypatch,
        [{"name": "あいさつ", "summary": "greet",
          "file_paths": ["web/util.js"], "symbols": ["web/util.js::greet"]}],
    )
    plan = plan_analysis(_settings(), FILES)
    feat = plan["features"][0]

    assert feat["context_mode"] == "fallback"
    # entrypoint(ルート定義を含む app/main.py)が入る
    assert "app/main.py" in feat["context"]


# --- 2 回目: 機能ごとの詳細分析 ---
def test_analyze_feature_detail_uses_context(monkeypatch):
    calls = _patch_client(
        monkeypatch,
        '{"name": "ユーザー取得", "overview": "1件返す", '
        '"sections": [{"heading": "トリガー", "body": "GET /users/{uid}"}]}',
    )
    out = analyze_feature_detail(
        _settings(),
        {"name": "ユーザー取得", "summary": "s", "context": "### app/main.py\n```\nget_user\n```"},
    )
    assert out["overview"] == "1件返す"
    assert out["sections"] == [{"heading": "トリガー", "body": "GET /users/{uid}"}]
    user_prompt = calls[0]["messages"][1]["content"]
    assert "get_user" in user_prompt and "コード抜粋" in user_prompt


def test_analyze_feature_detail_requires_ai_config():
    s = Settings(_env_file=None, AZURE_OPENAI_API_KEY="changeme")
    with pytest.raises(CodeAnalysisError):
        analyze_feature_detail(s, {"name": "x", "summary": "", "context": "y"})
