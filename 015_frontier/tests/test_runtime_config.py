"""実行時設定(acquisition_settings.json)の保存・読み込みと定期実行判定のテスト。

実ファイルには触れず、CONFIG_PATH を tmp_path へ差し替えて検証する。
"""

from __future__ import annotations

from datetime import date

import pytest

from config import runtime as runtime_config
from pipeline import weekly
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
    assert cfg.schedule_kind == "weekly"
    assert cfg.schedule_interval_days == 7
    assert cfg.schedule_weekday == 0
    assert cfg.mattermost_channel_ids == []
    assert cfg.trello_board_ids == []


def test_save_load_roundtrip(tmp_config):
    cfg = RuntimeConfig(
        since_date=date(2026, 8, 1),
        schedule_kind="daily",
        schedule_interval_days=3,
        schedule_weekday=2,
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
    assert loaded.schedule_kind == "daily"
    assert loaded.schedule_interval_days == 3
    assert loaded.schedule_weekday == 2
    assert loaded.mattermost_channel_ids == ["ch1", "ch2"]
    assert loaded.trello_board_ids == ["b1"]
    assert loaded.github_repo == "octocat/Hello-World"
    assert loaded.github_design_path == "docs/design"
    assert loaded.growi_page_path == "/projects/foo"
    assert loaded.since_datetime().isoformat() == "2026-08-01T00:00:00"


def test_invalid_values_are_clamped_or_ignored(tmp_config):
    tmp_config.write_text(
        '{"since_date": "not-a-date", "schedule": {"kind": "bogus", '
        '"interval_days": 999, "weekday": -5}, "mattermost_channel_ids": "x"}',
        encoding="utf-8",
    )
    cfg = load_runtime_config()
    assert cfg.since_date is None            # 不正な日付は無視
    assert cfg.schedule_kind == "weekly"     # 未知の kind は weekly
    assert cfg.schedule_interval_days == 31  # 1..31 にクランプ
    assert cfg.schedule_weekday == 0         # 0..6 にクランプ
    assert cfg.mattermost_channel_ids == []  # list 以外は空
    assert cfg.github_repo == ""             # 未指定はデフォルト
    assert cfg.github_design_path == ""
    assert cfg.growi_page_path == ""


def test_broken_json_falls_back_to_defaults(tmp_config):
    tmp_config.write_text("{ this is not json", encoding="utf-8")
    cfg = load_runtime_config()
    assert cfg.schedule_kind == "weekly"


@pytest.mark.parametrize(
    "kind,interval,weekday,today,last,expected",
    [
        # weekly: 指定曜日(3=木)なら実行
        ("weekly", 7, 3, date(2026, 9, 3), None, True),    # 2026-09-03 は木
        ("weekly", 7, 3, date(2026, 9, 4), None, False),   # 金
        # daily: 前回なし → 実行
        ("daily", 3, 0, date(2026, 9, 4), None, True),
        # daily: 前回から 2 日 → まだ
        ("daily", 3, 0, date(2026, 9, 4), date(2026, 9, 2), False),
        # daily: 前回から 3 日 → 実行
        ("daily", 3, 0, date(2026, 9, 4), date(2026, 9, 1), True),
    ],
)
def test_is_schedule_due(kind, interval, weekday, today, last, expected):
    rc = RuntimeConfig(
        schedule_kind=kind, schedule_interval_days=interval, schedule_weekday=weekday
    )
    assert weekly._is_schedule_due(rc, today, last) is expected
