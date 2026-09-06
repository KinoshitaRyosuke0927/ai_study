"""settings.ini パース(pipeline/project_config)のテスト。"""

from __future__ import annotations

from pipeline import project_config

SAMPLE = """\
[Mattermost]
- AIS_業務連絡
  開発メンバーのみで共有したい情報を共有するチャンネル
  レビュー依頼などを行う

[Trello]
- のみどき
  水の消費量を予測するアプリの開発プロジェクトのワークスペース
  - プロダクトバックログ
    開発状況を管理するボード

[GitHub]
- Nomidoki
  水の消費量を予測するアプリのリポジトリ

[GROWi]
- /path/to/docs
  ドキュメント置き場

[USER_ID]
- 矢野 誠
  - personal : AIB, AISの事業部長。
  - Mattermost : yano
  - Trello : jbd-ai
- 海野 亮
  - personal : 2020年入社。POとして評価を行う。
  - Mattermost : m-unno
  - GROWi : m-unno
  - Trello : munno3
  - GitHub : JBD-Makoto-Unno
"""


def test_parse(tmp_path):
    p = tmp_path / "settings.ini"
    p.write_text(SAMPLE, encoding="utf-8")
    cfg = project_config.load_project_config(p)

    assert cfg["found"] is True and len(cfg["raw_hash"]) == 64

    members = {m["name"]: m for m in cfg["members"]}
    assert set(members) == {"矢野 誠", "海野 亮"}

    yano = members["矢野 誠"]
    assert yano["personal"].startswith("AIB")
    assert yano["accounts"]["mattermost"] == "yano"
    assert yano["accounts"]["trello"] == "jbd-ai"
    assert yano["accounts"]["github"] == ""            # 未定義は空

    unno = members["海野 亮"]
    assert unno["accounts"]["github"] == "JBD-Makoto-Unno"
    assert unno["accounts"]["growi"] == "m-unno"

    ctx = cfg["tool_context"]
    assert "AIS_業務連絡" in ctx["mattermost"] and "レビュー依頼" in ctx["mattermost"]
    assert "プロダクトバックログ" in ctx["trello"]
    assert "Nomidoki" in ctx["github"]


def test_missing_file(tmp_path):
    cfg = project_config.load_project_config(tmp_path / "nope.ini")
    assert cfg["found"] is False and cfg["members"] == []


def test_hash_changes_with_content(tmp_path):
    p = tmp_path / "settings.ini"
    p.write_text(SAMPLE, encoding="utf-8")
    h1 = project_config.load_project_config(p)["raw_hash"]
    p.write_text(SAMPLE + "\n- 追加 太郎\n  - Mattermost : taro\n", encoding="utf-8")
    h2 = project_config.load_project_config(p)["raw_hash"]
    assert h1 != h2
