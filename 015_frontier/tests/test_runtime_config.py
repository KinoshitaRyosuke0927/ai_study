"""実行時設定(acquisition_settings.json)の保存・読み込みのテスト。

実ファイルには触れず、CONFIG_PATH を tmp_path へ差し替えて検証する。
"""

from __future__ import annotations

from datetime import date

import pytest

from config import runtime as runtime_config
from config.runtime import RuntimeConfig, load_runtime_config, save_runtime_config


@pytest.fixture()
def tmp_config(tmp_path, monkeypatch):
    """CONFIG_PATH を一時ファイルへ差し替える。"""
    path = tmp_path / "acquisition_settings.json"
    monkeypatch.setattr(runtime_config, "CONFIG_PATH", path)
    return path


def test_defaults_when_missing(tmp_config):
    cfg = load_runtime_config()
    assert cfg.since_date is None
    assert cfg.mattermost_channel_ids == []
    assert cfg.trello_board_ids == []
    assert cfg.github_repo == ""


def test_save_load_roundtrip(tmp_config):
    cfg = RuntimeConfig(
        since_date=date(2026, 8, 1),
        mattermost_channel_ids=["ch1", "ch2"],
        trello_board_ids=["b1"],
        github_repo="octocat/Hello-World",
        github_design_path="docs/design",
        growi_page_path="/projects/foo",
    )
    save_runtime_config(cfg)
    assert tmp_config.exists()

    loaded = load_runtime_config()
    assert loaded.since_date == date(2026, 8, 1)
    assert loaded.mattermost_channel_ids == ["ch1", "ch2"]
    assert loaded.trello_board_ids == ["b1"]
    assert loaded.github_repo == "octocat/Hello-World"
    assert loaded.github_design_path == "docs/design"
    assert loaded.growi_page_path == "/projects/foo"


def test_invalid_values_are_ignored(tmp_config):
    tmp_config.write_text(
        '{"since_date": "not-a-date", "mattermost_channel_ids": "x", '
        '"schedule": {"kind": "bogus"}}',  # 旧フィールドは無視される
        encoding="utf-8",
    )
    cfg = load_runtime_config()
    assert cfg.since_date is None            # 不正な日付は無視
    assert cfg.mattermost_channel_ids == []  # list 以外は空
    assert cfg.github_repo == ""
    assert cfg.github_design_path == ""
    assert cfg.growi_page_path == ""


def test_broken_json_falls_back_to_defaults(tmp_config):
    tmp_config.write_text("{ this is not json", encoding="utf-8")
    cfg = load_runtime_config()
    assert cfg.since_date is None
    assert cfg.mattermost_channel_ids == []


def test_to_api_dict_has_no_schedule(tmp_config):
    d = RuntimeConfig(since_date=date(2026, 8, 1)).to_api_dict()
    assert "schedule" not in d
    assert d["since_date"] == "2026-08-01"
