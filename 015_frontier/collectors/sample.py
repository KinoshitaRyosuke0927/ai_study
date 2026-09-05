"""サンプルデータコレクタ。

APP_RUN_MODE=sample のとき、4 ソースの実 API の代わりに使用する。
過去 5 週分の「プロジェクトらしい」活動を生成し、潜在問題(滞留・負荷偏り・
コミュニケーション低下・スコープ膨張・ドキュメント腐敗・品質リスク)を
意図的に含めることで、パイプラインと AI 分析の縦貫通テストを可能にする。

生成は乱数シード固定で決定的。再実行しても同じイベント(同じ ref)になるため、
uq_event により二重取り込みされない。
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from common.weeks import current_week, recent_weeks, week_start

from .base import Event, ItemRecord

# チームメンバー(後半になるほど takahashi の活動が減る = バスファクター/負荷偏り)
MEMBERS = ["sato", "suzuki", "tanaka", "takahashi"]

DONE_LISTS = {"Done", "完了"}
TRELLO_LISTS = ["Backlog", "Doing", "Review", "Done"]

# Mattermost 投稿の素材(決定パターンを含む文を混ぜる = 暗黙知抽出のため)
POST_TEMPLATES = [
    "{who} さん、レビューお願いします",
    "ステージング環境でエラーが再発しています。ログ確認中",
    "MySQL の文字コードは utf8mb4 に統一することにしました",
    "認証方式は Entra ID を採用することで合意しました",
    "リリースは今週金曜に延期することにした",
    "パフォーマンス改善のため N+1 クエリを解消したい",
    "定例MTGの議事録を GROWI に上げました",
    "この issue の優先度を上げましょう",
    "ライブラリのバージョン固定は見送りとします(影響範囲が大きいため)",
    "デプロイ手順書のドラフトを作成しました",
    "テストが不安定なので後で調査します",
    "外部APIのレート制限にひっかかった。指数バックオフを入れる",
    "デザインレビューの指摘を反映しました",
    "本番のスロークエリを 3 件特定。インデックス追加で対応することにした",
]

COMMIT_TEMPLATES = [
    "コレクタの正規化ロジックを修正",
    "週次パイプラインの冪等性を担保",
    "MySQL 接続で caching_sha2_password に対応",
    "ダッシュボードの指標カードを追加",
    "AI プロンプトのハルシネーション防止ルールを追記",
    "APScheduler のタイムゾーンを Asia/Tokyo に固定",
    "RAG 検索のコサイン類似度計算を実装",
    "差分計算(added/changed/removed)のバグ修正",
    "エラーハンドリング: 1 ソース失敗でも継続",
    "テスト追加: ページング動作の検証",
]

CARD_TITLES = [
    "ログイン画面のリニューアル",
    "週次バッチのリトライ設計",
    "MySQL スキーマのレビュー",
    "Chart.js による推移グラフ実装",
    "Azure Container Apps へのデプロイ検証",
    "Mattermost コレクタのページング対応",
    "GitHub Webhook の調査",
    "GROWI ページ取得APIの検証",
    "Trello アクション種別の対応表作成",
    "潜在問題スキャンの観点整理",
    "埋め込みモデルの選定",
    "負荷試験シナリオの作成",
]

ISSUE_TITLES = [
    "本番でスケジューラが二重起動する",
    "絵文字を含む投稿が文字化けする",
    "PR 一覧の取得が Link ヘッダで途切れる",
    "サンプルデータの日付がずれる",
    "検索結果の出典リンクが 404",
    "レポート生成がタイムアウトする",
]

PAGE_TITLES = [
    "アーキテクチャ概要",
    "MySQL 設計メモ",
    "デプロイ手順(Azure)",
    "AI プロンプト設計",
    "オンボーディングガイド",
]


class SampleCollector:
    """4 ソース分のサンプルイベント/アイテムをまとめて生成するコレクタ。"""

    source = "sample"

    def __init__(self, now: datetime | None = None) -> None:
        # 生成を決定的にするためシード固定
        self._rnd = random.Random(42)
        # 直近 5 週(古い順)を対象にする
        base_week = current_week(now)
        self._weeks = recent_weeks(base_week, 5)
        self._events: list[Event] = []
        self._items: dict[str, ItemRecord] = {}
        self._build()

    # ------------------------------------------------------------------
    # Collector インターフェース
    # ------------------------------------------------------------------
    def fetch_since(self, since: datetime) -> list[Event]:
        """since 以降のイベントのみを時系列で返す。"""
        since_naive = since.replace(tzinfo=None) if since.tzinfo else since
        return sorted(
            (e for e in self._events if e.ts >= since_naive), key=lambda e: e.ts
        )

    def fetch_items(self) -> list[ItemRecord]:
        """アイテム(カード / PR / issue / ページ)の最終状態を返す。"""
        return list(self._items.values())

    # ------------------------------------------------------------------
    # 生成本体
    # ------------------------------------------------------------------
    def _dt(self, week: str, day_offset: int, hour: int) -> datetime:
        """週初(月曜)からの相対日時を UTC naive で返す。"""
        return week_start(week) + timedelta(days=day_offset, hours=hour)

    def _build(self) -> None:
        """全ソースのイベントとアイテムを生成する。"""
        self._build_mattermost()
        self._build_github()
        self._build_trello()
        self._build_growi()

    def _build_mattermost(self) -> None:
        """投稿数が週を追うごとに減少(コミュニケーション低下)。"""
        posts_per_week = [40, 32, 25, 18, 9]
        # 後半ほど takahashi / tanaka が発言しなくなる = アクティブ人数の減少
        actor_weights_per_week = [
            [0.35, 0.30, 0.20, 0.15],
            [0.38, 0.32, 0.18, 0.12],
            [0.42, 0.34, 0.16, 0.08],
            [0.50, 0.38, 0.10, 0.02],
            [0.60, 0.38, 0.02, 0.00],
        ]
        post_no = 0
        for week, n_posts, weights in zip(
            self._weeks, posts_per_week, actor_weights_per_week
        ):
            for _ in range(n_posts):
                post_no += 1
                actor = self._rnd.choices(MEMBERS, weights=weights, k=1)[0]
                template = self._rnd.choice(POST_TEMPLATES)
                text = template.format(who=self._rnd.choice(MEMBERS))
                ts = self._dt(
                    week,
                    day_offset=self._rnd.randint(0, 4),
                    hour=self._rnd.randint(9, 19),
                )
                ref = f"post{post_no:04d}"
                self._events.append(
                    Event(
                        source="sample",
                        type="post",
                        actor=actor,
                        ts=ts,
                        ref=ref,
                        payload={
                            "text": text,
                            "thread_root": None,
                            "channel_id": "sample-channel",
                            "origin": "mattermost",
                        },
                    )
                )

    def _build_github(self) -> None:
        """コミットが sato に集中(バスファクター)、レビュー待ち PR が滞留。"""
        commits_per_week = [22, 25, 20, 24, 19]
        # sato に約 65% 集中
        commit_weights = [0.65, 0.18, 0.12, 0.05]
        sha_no = 0
        for week, n_commits in zip(self._weeks, commits_per_week):
            for _ in range(n_commits):
                sha_no += 1
                actor = self._rnd.choices(MEMBERS, weights=commit_weights, k=1)[0]
                ts = self._dt(
                    week,
                    day_offset=self._rnd.randint(0, 4),
                    hour=self._rnd.randint(10, 20),
                )
                sha = f"{sha_no:07x}"
                self._events.append(
                    Event(
                        source="sample",
                        type="commit",
                        actor=actor,
                        ts=ts,
                        ref=sha,
                        payload={
                            "message": self._rnd.choice(COMMIT_TEMPLATES),
                            "sha": sha,
                            "url": f"https://github.com/acme/frontier-app/commit/{sha}",
                            "origin": "github",
                        },
                    )
                )

        # PR: 毎週 4 件オープンし、マージは 1〜2 件のみ → 残りが滞留(stale PR)
        merges_per_week = [2, 1, 2, 1, 1]
        pr_no = 0
        for w_idx, (week, n_merge) in enumerate(zip(self._weeks, merges_per_week)):
            opened_this_week: list[int] = []
            for _ in range(4):
                pr_no += 1
                opened_this_week.append(pr_no)
                assignee = self._rnd.choice(MEMBERS)
                opened_ts = self._dt(week, self._rnd.randint(0, 2), self._rnd.randint(10, 18))
                title = f"PR: {self._rnd.choice(COMMIT_TEMPLATES)}"
                item_key = f"github:pr:{pr_no}"
                self._events.append(
                    Event(
                        source="sample",
                        type="pr_opened",
                        actor=assignee,
                        ts=opened_ts,
                        ref=f"pr-{pr_no}",
                        payload={
                            "item_key": item_key,
                            "title": title,
                            "number": pr_no,
                            "url": f"https://github.com/acme/frontier-app/pull/{pr_no}",
                            "assignee": assignee,
                            "labels": [],
                            "created_at": opened_ts.isoformat(),
                            "origin": "github",
                        },
                    )
                )
                self._items[item_key] = ItemRecord(
                    item_key=item_key,
                    source="github",
                    type="pr",
                    title=title,
                    status="open",
                    assignee=assignee,
                    payload={"number": pr_no, "created_at": opened_ts.isoformat()},
                )
            # 今週マージする PR を選ぶ(古い PR から優先的に)
            mergeable = sorted(self._items_open_prs())
            for pr_id in mergeable[:n_merge]:
                merged_ts = self._dt(week, self._rnd.randint(3, 4), self._rnd.randint(11, 19))
                item_key = f"github:pr:{pr_id}"
                rec = self._items[item_key]
                self._events.append(
                    Event(
                        source="sample",
                        type="pr_merged",
                        actor=rec.assignee or "sato",
                        ts=merged_ts,
                        ref=f"pr-{pr_id}",
                        payload={
                            "item_key": item_key,
                            "title": rec.title,
                            "number": pr_id,
                            "url": f"https://github.com/acme/frontier-app/pull/{pr_id}",
                            "assignee": rec.assignee,
                            "origin": "github",
                        },
                    )
                )
                rec.status = "merged"

        # issue: 毎週 3 件オープン / 1 件クローズ、加えて 2 件の再オープン(品質リスク)
        issue_no = 0
        closed_issues: list[int] = []
        for w_idx, week in enumerate(self._weeks):
            for _ in range(3):
                issue_no += 1
                actor = self._rnd.choice(MEMBERS)
                ts = self._dt(week, self._rnd.randint(0, 3), self._rnd.randint(9, 18))
                item_key = f"github:issue:{issue_no}"
                title = self._rnd.choice(ISSUE_TITLES)
                self._events.append(
                    Event(
                        source="sample",
                        type="issue_opened",
                        actor=actor,
                        ts=ts,
                        ref=f"issue-{issue_no}",
                        payload={
                            "item_key": item_key,
                            "title": title,
                            "number": issue_no,
                            "url": f"https://github.com/acme/frontier-app/issues/{issue_no}",
                            "labels": ["bug"] if self._rnd.random() < 0.5 else [],
                            "assignee": actor,
                            "origin": "github",
                        },
                    )
                )
                self._items[item_key] = ItemRecord(
                    item_key=item_key,
                    source="github",
                    type="issue",
                    title=title,
                    status="open",
                    assignee=actor,
                    payload={"number": issue_no},
                )
            # 1 件クローズ(まだ open のものから最古)
            open_issues = sorted(
                int(k.split(":")[-1])
                for k, v in self._items.items()
                if v.type == "issue" and v.status == "open"
            )
            if open_issues:
                cid = open_issues[0]
                ts = self._dt(week, 4, 16)
                self._events.append(
                    Event(
                        source="sample",
                        type="issue_closed",
                        actor=self._rnd.choice(MEMBERS),
                        ts=ts,
                        ref=f"issue-{cid}-c{w_idx}",
                        payload={
                            "item_key": f"github:issue:{cid}",
                            "title": self._items[f"github:issue:{cid}"].title,
                            "number": cid,
                            "url": f"https://github.com/acme/frontier-app/issues/{cid}",
                            "origin": "github",
                        },
                    )
                )
                self._items[f"github:issue:{cid}"].status = "closed"
                closed_issues.append(cid)

        # 再オープン 2 件(3 週目と 4 週目)
        for w_idx in (2, 3):
            if w_idx < len(self._weeks) and closed_issues:
                rid = closed_issues.pop(0)
                week = self._weeks[w_idx]
                ts = self._dt(week, 1, 10)
                self._events.append(
                    Event(
                        source="sample",
                        type="issue_reopened",
                        actor=self._rnd.choice(MEMBERS),
                        ts=ts,
                        ref=f"issue-{rid}-re{w_idx}",
                        payload={
                            "item_key": f"github:issue:{rid}",
                            "title": self._items[f"github:issue:{rid}"].title,
                            "number": rid,
                            "url": f"https://github.com/acme/frontier-app/issues/{rid}",
                            "origin": "github",
                        },
                    )
                )
                self._items[f"github:issue:{rid}"].status = "open"

    def _items_open_prs(self) -> list[int]:
        """現在 open な PR 番号の一覧。"""
        return [
            int(k.split(":")[-1])
            for k, v in self._items.items()
            if v.type == "pr" and v.status == "open"
        ]

    def _build_trello(self) -> None:
        """作成ペースが完了ペースを上回る(スコープ膨張)、WIP が増加。"""
        create_per_week = [7, 7, 8, 7, 6]
        done_per_week = [3, 3, 2, 2, 1]
        card_no = 0
        action_no = 0
        for week, n_create, n_done in zip(
            self._weeks, create_per_week, done_per_week
        ):
            for _ in range(n_create):
                card_no += 1
                action_no += 1
                actor = self._rnd.choice(MEMBERS)
                ts = self._dt(week, self._rnd.randint(0, 3), self._rnd.randint(9, 17))
                card_key = f"trello:card:{card_no}"
                title = f"{self._rnd.choice(CARD_TITLES)} #{card_no}"
                self._events.append(
                    Event(
                        source="sample",
                        type="card_created",
                        actor=actor,
                        ts=ts,
                        ref=f"act{action_no:04d}",
                        payload={
                            "card_key": card_key,
                            "title": title,
                            "list": "Backlog",
                            "origin": "trello",
                        },
                    )
                )
                self._items[card_key] = ItemRecord(
                    item_key=card_key,
                    source="trello",
                    type="card",
                    title=title,
                    status="open",
                    assignee=actor,
                    payload={"list": "Backlog"},
                )
            # 一部を Doing / Review へ移動(WIP)
            open_cards = [
                k for k, v in self._items.items() if v.type == "card" and v.status == "open"
            ]
            self._rnd.shuffle(open_cards)
            for card_key in open_cards[: n_create - n_done]:
                action_no += 1
                list_after = self._rnd.choice(["Doing", "Review"])
                ts = self._dt(week, self._rnd.randint(1, 4), self._rnd.randint(10, 18))
                self._events.append(
                    Event(
                        source="sample",
                        type="card_moved",
                        actor=self._rnd.choice(MEMBERS),
                        ts=ts,
                        ref=f"act{action_no:04d}",
                        payload={
                            "card_key": card_key,
                            "title": self._items[card_key].title,
                            "list_after": list_after,
                            "origin": "trello",
                        },
                    )
                )
                self._items[card_key].payload["list"] = list_after
            # n_done 件を Done へ
            movable = [
                k for k, v in self._items.items() if v.type == "card" and v.status == "open"
            ]
            self._rnd.shuffle(movable)
            for card_key in movable[:n_done]:
                action_no += 1
                ts = self._dt(week, 4, self._rnd.randint(14, 19))
                self._events.append(
                    Event(
                        source="sample",
                        type="card_moved",
                        actor=self._rnd.choice(MEMBERS),
                        ts=ts,
                        ref=f"act{action_no:04d}",
                        payload={
                            "card_key": card_key,
                            "title": self._items[card_key].title,
                            "list_after": "Done",
                            "origin": "trello",
                        },
                    )
                )
                self._items[card_key].status = "done"
                self._items[card_key].payload["list"] = "Done"

    def _build_growi(self) -> None:
        """コード変更が続く一方で Wiki 更新はごく少ない(ドキュメント腐敗)。"""
        created_per_week = [2, 1, 1, 0, 0]
        updated_per_week = [1, 1, 0, 1, 0]
        page_no = 0
        rev_no = 0
        for week, n_created, n_updated in zip(
            self._weeks, created_per_week, updated_per_week
        ):
            for _ in range(n_created):
                page_no += 1
                rev_no += 1
                actor = self._rnd.choice(MEMBERS)
                ts = self._dt(week, self._rnd.randint(0, 3), self._rnd.randint(10, 17))
                page_key = f"growi:page:{page_no}"
                title = self._rnd.choice(PAGE_TITLES)
                path = f"/projects/frontier/{title}"
                self._events.append(
                    Event(
                        source="sample",
                        type="page_created",
                        actor=actor,
                        ts=ts,
                        ref=f"{page_key}-r{rev_no}",
                        payload={
                            "page_key": page_key,
                            "title": title,
                            "path": path,
                            "revision_id": f"rev{rev_no}",
                            "updated_at": ts.isoformat(),
                            "origin": "growi",
                        },
                    )
                )
                self._items[page_key] = ItemRecord(
                    item_key=page_key,
                    source="growi",
                    type="page",
                    title=title,
                    status="active",
                    assignee=actor,
                    payload={"path": path},
                )
            # 既存ページの更新(少数)
            existing = [k for k, v in self._items.items() if v.type == "page"]
            self._rnd.shuffle(existing)
            for page_key in existing[:n_updated]:
                rev_no += 1
                ts = self._dt(week, self._rnd.randint(1, 4), self._rnd.randint(10, 18))
                self._events.append(
                    Event(
                        source="sample",
                        type="page_updated",
                        actor=self._rnd.choice(MEMBERS),
                        ts=ts,
                        ref=f"{page_key}-r{rev_no}",
                        payload={
                            "page_key": page_key,
                            "title": self._items[page_key].title,
                            "path": self._items[page_key].payload["path"],
                            "revision_id": f"rev{rev_no}",
                            "updated_at": ts.isoformat(),
                            "origin": "growi",
                        },
                    )
                )
