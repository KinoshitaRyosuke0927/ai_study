# -*- coding: utf-8 -*-
"""学習の進捗管理（SQLite）

- プロトタイプ版は「学習者1人」を想定し、ユーザー ID を持たない単純な形。
- 本番では users テーブルを分け、drill_id に user_id を足してください。
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "progress.db")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS progress (
                drill_id   TEXT PRIMARY KEY,
                completed  INTEGER NOT NULL DEFAULT 0,
                attempts   INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
        )


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def record_attempt(drill_id: str, passed: bool):
    """回答を記録。合格したら completed を 1 にする"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT completed, attempts FROM progress WHERE drill_id = ?", (drill_id,)
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO progress (drill_id, completed, attempts, updated_at) VALUES (?, ?, ?, ?)",
                (drill_id, 1 if passed else 0, 1, _now()),
            )
        else:
            attempts = row["attempts"] + 1
            completed = 1 if passed else row["completed"]
            conn.execute(
                "UPDATE progress SET completed = ?, attempts = ?, updated_at = ? WHERE drill_id = ?",
                (completed, attempts, _now(), drill_id),
            )


def get_progress() -> dict:
    """drill_id -> {completed, attempts, updated_at} の辞書を返す"""
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM progress").fetchall()
    return {
        r["drill_id"]: {
            "completed": bool(r["completed"]),
            "attempts": r["attempts"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    }


def reset_progress():
    """進捗をすべて消して最初からやり直す（管理用）"""
    with get_conn() as conn:
        conn.execute("DELETE FROM progress")
