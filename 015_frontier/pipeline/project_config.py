"""settings.ini(手書きのプロジェクト定義ファイル)の読み込み。

.env とは別の、独自のインデント箇条書き形式のファイル:

    [USER_ID]
    - 氏名
      - personal : 役割説明
      - Mattermost : account
      - Trello : account
      - GitHub : login

    [Mattermost] / [Trello] / [GitHub]
    - 名称
      説明文(そのツールの運用方法)

- load_project_config(): メンバー(氏名 → 各サービスのアカウント)と、
  各ツールの運用方法テキスト、ファイルのハッシュを返す。
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

SETTINGS_PATH = Path(__file__).resolve().parents[1] / "settings.ini"

_SECTION_RE = re.compile(r"^\[(.+?)\]\s*$")
_MEMBER_RE = re.compile(r"^-\s+(.+?)\s*$")           # 先頭インデントなしの "- 氏名"
_KV_RE = re.compile(r"^\s+-\s+([A-Za-z]+)\s*[:：]\s*(.+?)\s*$")  # "  - Mattermost : account"

# settings.ini のキー名 → 内部キー
_KEY_MAP = {
    "personal": "personal",
    "mattermost": "mattermost",
    "trello": "trello",
    "github": "github",
    "growi": "growi",
}
# 運用方法テキストとして丸ごと保持するセクション
_TOOL_SECTIONS = ("Mattermost", "Trello", "GitHub", "GROWi")


def _split_sections(text: str) -> dict[str, list[str]]:
    """"[名前]" 行でセクションに分割し、{名前: 行リスト} を返す。"""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        m = _SECTION_RE.match(line)
        if m:
            current = m.group(1).strip()
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)
    return sections


def _parse_members(lines: list[str]) -> list[dict]:
    """[USER_ID] セクションの行から、メンバー一覧を組み立てる。"""
    members: list[dict] = []
    cur: dict | None = None
    for line in lines:
        if not line.strip():
            continue
        kv = _KV_RE.match(line)
        if kv and cur is not None:
            key = _KEY_MAP.get(kv.group(1).strip().lower())
            if key:
                cur[key] = kv.group(2).strip()
            continue
        mm = _MEMBER_RE.match(line)
        if mm:
            cur = {
                "name": mm.group(1).strip(),
                "personal": "",
                "accounts": {"mattermost": "", "trello": "", "github": "", "growi": ""},
            }
            members.append(cur)
    # personal / accounts をフラットな dict から所定の形へ寄せる
    out: list[dict] = []
    for m in members:
        accounts = {
            "mattermost": m.get("mattermost", ""),
            "trello": m.get("trello", ""),
            "github": m.get("github", ""),
            "growi": m.get("growi", ""),
        }
        out.append({"name": m["name"], "personal": m.get("personal", ""), "accounts": accounts})
    return out


def load_project_config(path: Path | None = None) -> dict:
    """settings.ini を読み、メンバー / ツール運用方法 / ハッシュを返す。

    Returns
    -----------------
    - {
        "members": [{"name", "personal", "accounts": {mattermost, trello, github, growi}}],
        "tool_context": {"mattermost": str, "trello": str, "github": str, "growi": str},
        "raw_hash": str,   # ファイル内容の SHA-256(キャッシュキー用)
        "found": bool,
      }
    """
    p = path or SETTINGS_PATH
    if not p.exists():
        logger.warning("settings.ini が見つかりません: %s", p)
        return {"members": [], "tool_context": {}, "raw_hash": "", "found": False}

    raw = p.read_text(encoding="utf-8")
    sections = _split_sections(raw)

    members = _parse_members(sections.get("USER_ID", []))
    tool_context = {
        key.lower(): "\n".join(sections.get(key, [])).strip()
        for key in _TOOL_SECTIONS
    }
    return {
        "members": members,
        "tool_context": tool_context,
        "raw_hash": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "found": True,
    }
