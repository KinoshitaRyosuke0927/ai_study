"""定期実行パイプラインの進捗を DB に記録・取得する。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from config.settings import get_settings
from infra.db import get_session_factory

# パイプラインのステップ定義(実行順・表示ラベル・フェーズ)
STEPS: list[tuple[str, str, str]] = [
    ("design", "設計書情報分析", "parallel"),
    ("code", "コード情報分析", "parallel"),
    ("mattermost", "Mattermost情報分析", "parallel"),
    ("trello", "Trello情報分析", "parallel"),
    ("github", "GitHub情報取得", "parallel"),
    ("changelog", "変更履歴分析", "parallel"),
    ("spec_diff", "実装差分解析", "sequential"),
    ("user_activity", "アクティビティ分析", "sequential"),
    ("kpt", "KPT分析", "sequential"),
]


def _new_session() -> Session:
    return get_session_factory(get_settings())()


def _json_col(value: Any) -> Any:
    if value is None:
        return None
    return value if not isinstance(value, (str, bytes)) else json.loads(value)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def running_run_id() -> int | None:
    """実行中のパイプライン run があればその id。"""
    session = _new_session()
    try:
        row = session.execute(
            text("SELECT id FROM pipeline_runs WHERE status = 'running' ORDER BY id DESC LIMIT 1")
        ).first()
        return int(row.id) if row else None
    finally:
        session.close()


def create_run() -> int:
    """running の pipeline_run と、全ステップを pending で作成し run_id を返す。"""
    session = _new_session()
    try:
        res = session.execute(
            text("INSERT INTO pipeline_runs (status, started_at) VALUES ('running', :t)"),
            {"t": _now()},
        )
        run_id = int(res.lastrowid)
        for i, (key, label, phase) in enumerate(STEPS):
            session.execute(
                text(
                    """
                    INSERT INTO pipeline_run_steps
                      (run_id, ordinal, step_key, label, phase, status)
                    VALUES (:r, :o, :k, :l, :p, 'pending')
                    """
                ),
                {"r": run_id, "o": i, "k": key, "l": label, "p": phase},
            )
        session.commit()
        return run_id
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def set_step(
    run_id: int,
    step_key: str,
    status: str,
    *,
    result: dict[str, Any] | None = None,
    error: str | None = None,
    started: bool = False,
    finished: bool = False,
) -> None:
    """1 ステップの状態を更新する。"""
    session = _new_session()
    try:
        sets = ["status = :status"]
        params: dict[str, Any] = {"run_id": run_id, "key": step_key, "status": status}
        if started:
            sets.append("started_at = :st")
            params["st"] = _now()
        if finished:
            sets.append("finished_at = :ft")
            params["ft"] = _now()
        if result is not None:
            sets.append("result = :res")
            params["res"] = json.dumps(result, ensure_ascii=False, default=str)
        if error is not None:
            sets.append("error = :err")
            params["err"] = error[:60000]
        session.execute(
            text(f"UPDATE pipeline_run_steps SET {', '.join(sets)} WHERE run_id = :run_id AND step_key = :key"),
            params,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def finish_run(run_id: int, status: str, detail: str | None = None) -> None:
    """pipeline_run を終了状態にする。"""
    session = _new_session()
    try:
        session.execute(
            text(
                "UPDATE pipeline_runs SET status = :s, finished_at = :ft, detail = :d WHERE id = :id"
            ),
            {"s": status, "ft": _now(), "d": (detail or None) and detail[:60000], "id": run_id},
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _get_run(session: Session, run_id: int) -> dict[str, Any] | None:
    r = session.execute(
        text(
            "SELECT id, status, started_at, finished_at, detail FROM pipeline_runs WHERE id = :id"
        ),
        {"id": run_id},
    ).first()
    if not r:
        return None
    steps = session.execute(
        text(
            """
            SELECT ordinal, step_key, label, phase, status, started_at, finished_at, result, error
            FROM pipeline_run_steps WHERE run_id = :r ORDER BY ordinal
            """
        ),
        {"r": run_id},
    ).all()

    def _dur(s: Any) -> int | None:
        if s.started_at and s.finished_at:
            return int((s.finished_at - s.started_at).total_seconds())
        return None

    return {
        "id": r.id,
        "status": r.status,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "detail": r.detail,
        "steps": [
            {
                "ordinal": s.ordinal,
                "step_key": s.step_key,
                "label": s.label,
                "phase": s.phase,
                "status": s.status,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "finished_at": s.finished_at.isoformat() if s.finished_at else None,
                "duration_sec": _dur(s),
                "result": _json_col(s.result),
                "error": s.error,
            }
            for s in steps
        ],
    }


def get_run(run_id: int) -> dict[str, Any] | None:
    session = _new_session()
    try:
        return _get_run(session, run_id)
    finally:
        session.close()


def get_latest_run() -> dict[str, Any] | None:
    session = _new_session()
    try:
        row = session.execute(
            text("SELECT id FROM pipeline_runs ORDER BY id DESC LIMIT 1")
        ).first()
        return _get_run(session, row.id) if row else None
    finally:
        session.close()


def list_runs(limit: int = 30) -> list[dict[str, Any]]:
    session = _new_session()
    try:
        rows = session.execute(
            text(
                """
                SELECT r.id, r.status, r.started_at, r.finished_at,
                       SUM(s.status = 'success') AS ok,
                       SUM(s.status = 'error') AS ng,
                       COUNT(*) AS total
                FROM pipeline_runs r
                LEFT JOIN pipeline_run_steps s ON s.run_id = r.id
                GROUP BY r.id ORDER BY r.id DESC LIMIT :lim
                """
            ),
            {"lim": limit},
        ).all()
        return [
            {
                "id": r.id,
                "status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "success_steps": int(r.ok or 0),
                "error_steps": int(r.ng or 0),
                "total_steps": int(r.total or 0),
            }
            for r in rows
        ]
    finally:
        session.close()
