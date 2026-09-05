"""週次パイプライン。

collectors → events → items / week_items → metrics → AI 分析 → embeddings の
一連の処理をまとめ、runs テーブルに実行記録を残す。

- 再実行してもイベントは重複しない(uq_event により冪等)。
- 途中の日付データは ts の ISO 週へ正規化して各週を処理する。
- 1 ソースの失敗ではパイプライン全体を止めない。
"""

from __future__ import annotations

import json
import logging
import traceback
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ai import AiAnalyzer
from collectors.base import Collector, Event, ItemRecord
from db import get_session_factory
from metrics import compute_metrics, load_metrics_trend, save_metrics
from rag import build_and_store_embeddings
from runtime_config import RuntimeConfig, load_runtime_config
from settings import Settings, get_settings
from store import (
    compute_diff,
    diff_digest,
    save_events,
    snapshot_week_items,
    upsert_items,
)
from weeks import current_week, iso_week_of, prev_week, recent_weeks

logger = logging.getLogger(__name__)

# 初回実行時にさかのぼる期間(サンプルは 5 週分生成するため余裕を持たせる)
INITIAL_LOOKBACK_DAYS = 45


def _build_collectors(settings: Settings, rc: RuntimeConfig) -> list[Collector]:
    """実行モードと実行時設定に応じてコレクタ一覧を組み立てる。"""
    if settings.is_sample_mode:
        from collectors.sample import SampleCollector

        return [SampleCollector()]

    # real モード。GitHub / GROWI は常に対象。
    from collectors.github import GitHubCollector
    from collectors.growi import GrowiCollector
    from collectors.mattermost import MattermostCollector
    from collectors.trello import TrelloCollector

    collectors: list[Collector] = []

    # Mattermost: 設定画面で選んだチャンネルのみ。1 件も無ければ取得しない。
    channel_ids = rc.mattermost_channel_ids or (
        [settings.mattermost_channel_id]
        if settings.mattermost_channel_id and settings.mattermost_channel_id != "changeme"
        else []
    )
    if channel_ids:
        collectors.append(MattermostCollector(settings, channel_ids=channel_ids))
    else:
        logger.info("Mattermost: 取得対象チャンネルが未設定のためスキップ")

    # GitHub: 設定画面のリポジトリ名称を優先(空なら .env の GITHUB_REPOS)
    repos = [rc.github_repo] if rc.github_repo else settings.github_repo_list
    collectors.append(GitHubCollector(settings, repos=repos))

    # GROWI: 設定画面の Wiki パスを優先(空なら .env の GROWI_TARGET_PATHS)
    paths = [rc.growi_page_path] if rc.growi_page_path else settings.growi_path_list
    collectors.append(GrowiCollector(settings, paths=paths))

    # Trello: 設定画面で選んだボードのみ。1 件も無ければ取得しない。
    board_ids = rc.trello_board_ids or (
        [settings.trello_board_id]
        if settings.trello_board_id and settings.trello_board_id != "changeme"
        else []
    )
    if board_ids:
        collectors.append(TrelloCollector(settings, board_ids=board_ids))
    else:
        logger.info("Trello: 取得対象ボードが未設定のためスキップ")

    return collectors


def _determine_since(session: Session, rc: RuntimeConfig) -> datetime:
    """差分取得の起点 since を決める。

    - 前回成功実行があればその完了時刻(増分取得)
    - 無ければ「データ取得開始日 0:00」、それも未設定なら INITIAL_LOOKBACK_DAYS 前
    - いずれの場合も「データ取得開始日 0:00」より前には遡らない
    """
    row = session.execute(
        text(
            """
            SELECT finished_at FROM runs
            WHERE status = 'success' AND finished_at IS NOT NULL
            ORDER BY finished_at DESC LIMIT 1
            """
        )
    ).first()
    cfg_since = rc.since_datetime()

    if row and row[0]:
        since = row[0]
    elif cfg_since is not None:
        since = cfg_since
    else:
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            days=INITIAL_LOOKBACK_DAYS
        )

    # 取得開始日より前は対象外
    if cfg_since is not None and since < cfg_since:
        since = cfg_since
    return since


def _actor_commit_load(session: Session, week: str) -> dict[str, int]:
    """週内コミットの担当者別件数(負荷偏りの判定材料)。"""
    rows = session.execute(
        text(
            """
            SELECT actor, COUNT(*) AS c
            FROM events
            WHERE week = :w AND type = 'commit'
            GROUP BY actor
            """
        ),
        {"w": week},
    ).all()
    return {actor: int(c) for actor, c in rows}


def _load_posts(session: Session, week: str) -> list[dict[str, Any]]:
    """週内の投稿イベントを暗黙知抽出用の辞書リストへ。"""
    rows = session.execute(
        text(
            """
            SELECT ref, actor, payload FROM events
            WHERE week = :w AND type = 'post'
            ORDER BY ts ASC
            """
        ),
        {"w": week},
    ).all()
    posts: list[dict[str, Any]] = []
    for ref, actor, payload_raw in rows:
        payload = payload_raw if isinstance(payload_raw, dict) else json.loads(payload_raw or "{}")
        posts.append({"ref": ref, "actor": actor, "text": payload.get("text", "")})
    return posts


def _load_prev_kpt(session: Session, week: str) -> dict[str, Any] | None:
    """前週レポートの KPT を取得(try の引き継ぎに使用)。"""
    row = session.execute(
        text("SELECT kpt FROM reports WHERE week = :w"), {"w": prev_week(week)}
    ).first()
    if not row or not row[0]:
        return None
    return row[0] if isinstance(row[0], dict) else json.loads(row[0])


def _save_report(
    session: Session,
    week: str,
    report: dict[str, Any],
    risks: list[dict[str, Any]],
) -> None:
    """reports テーブルへ upsert する。"""
    kpt = {
        "keep": report.get("keep", []),
        "problem": report.get("problem", []),
        "try": report.get("try", []),
        "done": report.get("done", []),
        "learned": report.get("learned", []),
    }
    session.execute(
        text(
            """
            INSERT INTO reports (week, kpt, risks, summary_md)
            VALUES (:week, :kpt, :risks, :summary_md)
            ON DUPLICATE KEY UPDATE
                kpt = VALUES(kpt), risks = VALUES(risks),
                summary_md = VALUES(summary_md), created_at = CURRENT_TIMESTAMP
            """
        ),
        {
            "week": week,
            "kpt": json.dumps(kpt, ensure_ascii=False),
            "risks": json.dumps(risks, ensure_ascii=False),
            "summary_md": report.get("summary_md", ""),
        },
    )


def _save_decisions(
    session: Session, week: str, decisions: list[dict[str, Any]]
) -> None:
    """decisions テーブルを当該週について作り直す。"""
    session.execute(text("DELETE FROM decisions WHERE week = :w"), {"w": week})
    stmt = text(
        """
        INSERT INTO decisions (week, summary, rationale, participants, source_refs)
        VALUES (:week, :summary, :rationale, :participants, :source_refs)
        """
    )
    for d in decisions:
        session.execute(
            stmt,
            {
                "week": week,
                "summary": d.get("summary", ""),
                "rationale": d.get("rationale") or None,
                "participants": json.dumps(d.get("participants", []), ensure_ascii=False),
                "source_refs": json.dumps(d.get("source_refs", []), ensure_ascii=False),
            },
        )


def create_run(mode: str = "manual") -> int:
    """runs テーブルに running レコードを作成し run_id を返す。

    /api/run が即座に run_id を返せるよう、パイプライン本体と分離している。
    """
    factory = get_session_factory(get_settings())
    session: Session = factory()
    try:
        started = datetime.now(timezone.utc).replace(tzinfo=None)
        run_id = session.execute(
            text(
                "INSERT INTO runs (started_at, status, mode) VALUES (:s, 'running', :m)"
            ),
            {"s": started, "m": mode},
        ).lastrowid
        session.commit()
        return int(run_id)
    finally:
        session.close()


def run(
    mode: str = "manual", analyze: bool = True, run_id: int | None = None
) -> dict[str, Any]:
    """週次パイプラインを実行する。

    Args:
        mode: "manual" / "scheduled"。runs.mode に記録する。
        analyze: AI 分析(レポート / リスク / 暗黙知 / 埋め込み)を行うか。
        run_id: 事前に create_run() で作成済みの run_id。None なら本関数で作成する。

    Returns:
        実行サマリの辞書(run_id, status, weeks, events_new など)。
    """
    settings = get_settings()
    factory = get_session_factory(settings)
    session: Session = factory()

    # 1. 実行記録(running)
    if run_id is None:
        started = datetime.now(timezone.utc).replace(tzinfo=None)
        run_id = session.execute(
            text(
                "INSERT INTO runs (started_at, status, mode) VALUES (:s, 'running', :m)"
            ),
            {"s": started, "m": mode},
        ).lastrowid
        session.commit()
    logger.info("run 開始: id=%s mode=%s analyze=%s", run_id, mode, analyze)

    summary: dict[str, Any] = {
        "run_id": run_id,
        "mode": mode,
        "status": "running",
        "weeks": [],
        "events_new": 0,
        "errors": [],
    }

    try:
        # 2. 実行時設定を「使用する処理の実行時」に読み込む
        rc = load_runtime_config()
        since = _determine_since(session, rc)
        logger.info(
            "差分取得の起点 since=%s / 取得開始日=%s", since, rc.since_date
        )

        # 3. コレクタ実行(ソース単位で失敗を許容)
        all_events: list[Event] = []
        all_items: list[ItemRecord] = []
        for collector in _build_collectors(settings, rc):
            try:
                events = collector.fetch_since(since)
                all_events.extend(events)
                if hasattr(collector, "fetch_items"):
                    all_items.extend(collector.fetch_items())
                logger.info(
                    "コレクタ %s: events=%d items 取得", collector.source, len(events)
                )
            except Exception as exc:
                msg = f"{collector.source}: {exc}"
                logger.error("コレクタ失敗 %s\n%s", msg, traceback.format_exc())
                summary["errors"].append(msg)

        # 3b. events 保存
        summary["events_new"] = save_events(session, all_events)
        session.commit()

        # 4. 処理対象週(イベントの ISO 週)。無ければ当週のみ
        weeks = sorted({iso_week_of(e.ts) for e in all_events}) or [current_week()]
        summary["weeks"] = weeks
        processing_week = weeks[-1]

        # items 反映
        upsert_items(session, all_items, processing_week)
        session.commit()

        analyzer = AiAnalyzer(settings) if analyze else None

        # 5-7. 週ごとに断面・指標・AI 分析
        for week in weeks:
            snapshot_week_items(session, week)
            values = compute_metrics(session, week)
            save_metrics(session, week, values)
            session.commit()

            if analyzer is None:
                continue

            diff = compute_diff(session, week)
            digest = diff_digest(diff)
            trend = load_metrics_trend(session, recent_weeks(week, 4))
            actor_load = _actor_commit_load(session, week)
            prev_kpt = _load_prev_kpt(session, week)

            report = analyzer.generate_report(week, values, digest, prev_kpt, trend)
            risks = analyzer.scan_risks(week, values, digest, trend, actor_load)
            _save_report(session, week, report, risks)

            posts = _load_posts(session, week)
            decisions = analyzer.extract_decisions(week, posts)
            _save_decisions(session, week, decisions)
            session.commit()

            # 8. 埋め込み生成
            build_and_store_embeddings(session, analyzer, week)
            session.commit()

        # 9. 成功記録
        finished = datetime.now(timezone.utc).replace(tzinfo=None)
        summary["status"] = "success"
        session.execute(
            text(
                "UPDATE runs SET finished_at = :f, status = 'success', detail = :d WHERE id = :id"
            ),
            {"f": finished, "d": json.dumps(summary, ensure_ascii=False, default=str)[:60000], "id": run_id},
        )
        session.commit()
        logger.info("run 完了: id=%s weeks=%s events_new=%d", run_id, weeks, summary["events_new"])

    except Exception as exc:
        session.rollback()
        detail = f"{exc}\n{traceback.format_exc()}"
        logger.error("run 失敗: id=%s\n%s", run_id, detail)
        session.execute(
            text(
                "UPDATE runs SET finished_at = :f, status = 'error', detail = :d WHERE id = :id"
            ),
            {
                "f": datetime.now(timezone.utc).replace(tzinfo=None),
                "d": detail[:60000],
                "id": run_id,
            },
        )
        session.commit()
        summary["status"] = "error"
        summary["errors"].append(str(exc))
    finally:
        session.close()

    return summary


# ----------------------------------------------------------------------
# 定期実行(スケジューラから毎日 0:00 に呼ばれるディスパッチャ)
# ----------------------------------------------------------------------
def _last_scheduled_success_date(session: Session) -> date | None:
    """最後に成功した定期実行の日付(started_at ベース)。"""
    row = session.execute(
        text(
            """
            SELECT MAX(started_at) FROM runs
            WHERE mode = 'scheduled' AND status = 'success'
            """
        )
    ).scalar()
    return row.date() if row else None


def _is_schedule_due(rc: RuntimeConfig, today: date, last_success: date | None) -> bool:
    """本日が定期実行の対象日かどうかを実行時設定から判定する。"""
    if rc.schedule_kind == "weekly":
        # 指定曜日なら実行(0=月 .. 6=日)
        return today.weekday() == rc.schedule_weekday
    # daily: 前回成功から interval_days 日以上経過していれば実行
    if last_success is None:
        return True
    return (today - last_success).days >= rc.schedule_interval_days


def scheduled_tick(now: datetime | None = None) -> bool:
    """スケジューラから毎日 0:00 に呼ばれる。設定を読み、対象日ならパイプラインを実行する。

    設定(acquisition_settings.json)はこの実行時に読み込む(起動時にはキャッシュしない)。

    Returns:
        パイプラインを開始したかどうか。
    """
    rc = load_runtime_config()
    today = (now or datetime.now(timezone.utc).replace(tzinfo=None)).date()

    factory = get_session_factory(get_settings())
    session: Session = factory()
    try:
        last_success = _last_scheduled_success_date(session)
    finally:
        session.close()

    if not _is_schedule_due(rc, today, last_success):
        logger.info(
            "定期実行チェック: 本日(%s)は対象外(kind=%s)", today, rc.schedule_kind
        )
        return False

    logger.info("定期実行チェック: 本日(%s)は対象。パイプラインを開始します", today)
    run(mode="scheduled", analyze=True)
    return True
