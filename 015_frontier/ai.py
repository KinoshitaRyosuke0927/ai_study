"""Azure OpenAI による分析(週次レポート / リスクスキャン / 暗黙知抽出 / RAG)。

- Azure OpenAI が設定されていない環境では、決定的なルールベースの
  フォールバック応答を返す(sample モードでもパイプラインが完走する)。
- 全 AI 呼び出しは失敗時に 1 回リトライし、なお失敗ならエラーを記録して継続する。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from settings import Settings
from vectors import hash_embedding

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# JSON Schema(structured outputs / strict)
# ----------------------------------------------------------------------
_EVIDENCE_ARRAY = {"type": "array", "items": {"type": "string"}}

# keep / problem / done / learned 共通のアイテム定義
_KPT_ITEM = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "detail": {"type": "string"},
        "evidence": _EVIDENCE_ARRAY,
    },
    "required": ["title", "detail", "evidence"],
}

_REPORT_SCHEMA = {
    "name": "weekly_report",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "keep": {"type": "array", "items": _KPT_ITEM},
            "problem": {"type": "array", "items": _KPT_ITEM},
            "done": {"type": "array", "items": _KPT_ITEM},
            "learned": {"type": "array", "items": _KPT_ITEM},
            "try": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string"},
                        "detail": {"type": "string"},
                        "followup_of": {"type": "string"},
                    },
                    "required": ["title", "detail", "followup_of"],
                },
            },
            "summary_md": {"type": "string"},
        },
        "required": ["keep", "problem", "done", "learned", "try", "summary_md"],
    },
}

_RISKS_SCHEMA = {
    "name": "risk_scan",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "risks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "category": {"type": "string"},
                        "severity": {"type": "string", "enum": ["high", "mid", "low"]},
                        "title": {"type": "string"},
                        "detail": {"type": "string"},
                        "evidence": _EVIDENCE_ARRAY,
                    },
                    "required": ["category", "severity", "title", "detail", "evidence"],
                },
            }
        },
        "required": ["risks"],
    },
}

_DECISIONS_SCHEMA = {
    "name": "decisions",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "decisions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "summary": {"type": "string"},
                        "rationale": {"type": "string"},
                        "participants": {"type": "array", "items": {"type": "string"}},
                        "source_refs": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["summary", "rationale", "participants", "source_refs"],
                },
            }
        },
        "required": ["decisions"],
    },
}

# ----------------------------------------------------------------------
# システムプロンプト
# ----------------------------------------------------------------------
_REPORT_SYSTEM = """あなたはアジャイル開発の振り返りファシリテータです。
与えられた入力(指標JSON・差分ダイジェスト・先週のKPT・直近4週の推移)だけを根拠に、
KPT(Keep/Problem/Try)と Fun-Done-Learn(Done/Learned)を日本語で作成します。

厳守事項(ハルシネーション防止):
- 入力に含まれない事実を絶対に捏造しない。
- 数値は入力された指標JSONの値をそのまま引用する。再計算・推測しない。
- すべての keep/problem/done/learned 項目に evidence を最低1つ付ける。
  evidence には event_uid、または「指標名+週」(例: github_stale_prs@2026-W36)を用いる。
- try[] は先週の try を引き継ぐ場合 followup_of に先週の try のタイトルを入れる。引き継がない場合は空文字。
- summary_md は Markdown の週次サマリ(見出し+箇条書き、300〜600字程度)。"""

_RISKS_SYSTEM = """あなたはプロジェクトの健全性を監視するアナリストです。
与えられた入力だけを根拠に、潜在問題(risks)を日本語で洗い出します。

チェック観点:
- 進捗の滞留(レビュー待ちPRの滞留、WIP増加、長期オープンのカード/issue)
- 品質リスク(issueの再オープン、バグラベル集中)
- 負荷の偏り(特定メンバーへのコミット/担当集中、バスファクター)
- コミュニケーション低下(投稿数の急減、アクティブ人数の減少)
- スコープ膨張(作成ペース > 完了ペース)
- ドキュメント腐敗(コード変更が続く一方でWikiが更新されない)

厳守事項:
- 入力に無い事実を捏造しない。数値は入力値をそのまま引用する。
- 各 risk に evidence(指標名+週 または event_uid)を最低1つ付ける。
- severity は high/mid/low のいずれか。"""

_DECISIONS_SYSTEM = """あなたはチームの暗黙知を記録する書記です。
与えられた Mattermost 投稿群から「決定事項」を抽出します。

検出基準(次のような言語パターン):
- 「〜することにした」「〜にしましょう」「〜で合意」「〜で行く」
- 「〜は見送り」「〜はやめる」「〜を採用」「〜に決定」

各決定について、summary(決定内容)・rationale(理由・背景・代替案や異論があれば含める)・
participants(発言者)・source_refs(該当投稿の ref)を日本語で出力します。
決定が見当たらなければ decisions は空配列にします。捏造しないこと。"""


class AiAnalyzer:
    """Azure OpenAI 呼び出しをまとめたクラス(未設定時はフォールバック)。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.enabled = settings.ai_enabled
        self._chat_model = settings.azure_openai_chat_deployment
        self._embed_model = settings.azure_openai_embedding_deployment
        self._client = None
        if self.enabled:
            try:
                from openai import AzureOpenAI

                self._client = AzureOpenAI(
                    azure_endpoint=settings.azure_openai_endpoint,
                    api_key=settings.azure_openai_api_key,
                    api_version=settings.azure_openai_api_version,
                )
                logger.info("Azure OpenAI クライアント初期化完了")
            except Exception as exc:  # pragma: no cover
                logger.error("Azure OpenAI 初期化失敗。フォールバックへ: %s", exc)
                self.enabled = False

    # ------------------------------------------------------------------
    # 内部: 構造化出力つきチャット呼び出し(1 回リトライ)
    # ------------------------------------------------------------------
    def _structured_chat(
        self, system: str, user_payload: dict[str, Any], schema: dict[str, Any]
    ) -> dict[str, Any] | None:
        """JSON Schema(strict)で構造化出力を得る。失敗時は None。"""
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": json.dumps(user_payload, ensure_ascii=False, default=str),
            },
        ]
        for attempt in range(2):  # 初回 + リトライ 1 回
            try:
                resp = self._client.chat.completions.create(  # type: ignore[union-attr]
                    model=self._chat_model,
                    messages=messages,
                    response_format={"type": "json_schema", "json_schema": schema},
                    temperature=0.2,
                )
                content = resp.choices[0].message.content or "{}"
                return json.loads(content)
            except Exception as exc:
                logger.error(
                    "AI 構造化呼び出し失敗 (schema=%s, attempt=%d): %s",
                    schema.get("name"),
                    attempt + 1,
                    exc,
                )
        return None

    # ------------------------------------------------------------------
    # (a) 週次レポート
    # ------------------------------------------------------------------
    def generate_report(
        self,
        week: str,
        metrics: dict[str, float],
        diff_digest: dict[str, Any],
        prev_kpt: dict[str, Any] | None,
        trend: dict[str, dict[str, float]],
    ) -> dict[str, Any]:
        """KPT / Fun-Done-Learn + Markdown サマリを返す。"""
        if self.enabled:
            payload = {
                "week": week,
                "metrics": metrics,
                "diff_digest": diff_digest,
                "previous_kpt": prev_kpt or {},
                "metrics_trend_last4w": trend,
            }
            result = self._structured_chat(_REPORT_SYSTEM, payload, _REPORT_SCHEMA)
            if result is not None:
                return result
        # フォールバック
        return _fallback_report(week, metrics, diff_digest, prev_kpt)

    # ------------------------------------------------------------------
    # (b) 潜在問題スキャン
    # ------------------------------------------------------------------
    def scan_risks(
        self,
        week: str,
        metrics: dict[str, float],
        diff_digest: dict[str, Any],
        trend: dict[str, dict[str, float]],
        actor_load: dict[str, int] | None = None,
    ) -> list[dict[str, Any]]:
        """risks[] を返す。"""
        if self.enabled:
            payload = {
                "week": week,
                "metrics": metrics,
                "diff_digest": diff_digest,
                "metrics_trend_last4w": trend,
                "actor_commit_load": actor_load or {},
            }
            result = self._structured_chat(_RISKS_SYSTEM, payload, _RISKS_SCHEMA)
            if result is not None:
                return result.get("risks", [])
        return _fallback_risks(week, metrics, trend, actor_load or {})

    # ------------------------------------------------------------------
    # (c) 暗黙知の抽出
    # ------------------------------------------------------------------
    def extract_decisions(
        self, week: str, posts: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Mattermost 投稿群から決定事項を抽出する。"""
        if not posts:
            return []
        if self.enabled:
            payload = {"week": week, "posts": posts}
            result = self._structured_chat(_DECISIONS_SYSTEM, payload, _DECISIONS_SCHEMA)
            if result is not None:
                return result.get("decisions", [])
        return _fallback_decisions(posts)

    # ------------------------------------------------------------------
    # (d) 埋め込み
    # ------------------------------------------------------------------
    def embed_texts(self, texts: list[str]) -> tuple[list[list[float]], str]:
        """テキスト群を埋め込みベクトルへ変換する。

        Returns:
            (ベクトルのリスト, 使用モデル名)。
        """
        if not texts:
            return [], self._embed_model if self.enabled else "hash-fallback"
        if self.enabled:
            for attempt in range(2):
                try:
                    resp = self._client.embeddings.create(  # type: ignore[union-attr]
                        model=self._embed_model, input=texts
                    )
                    return [d.embedding for d in resp.data], self._embed_model
                except Exception as exc:
                    logger.error("埋め込み呼び出し失敗 (attempt=%d): %s", attempt + 1, exc)
        # フォールバック: 決定的なハッシュ埋め込み
        return [hash_embedding(t) for t in texts], "hash-fallback"

    def embed_query(self, query: str) -> tuple[list[float], str]:
        """検索クエリ 1 件を埋め込む。"""
        vecs, model = self.embed_texts([query])
        return (vecs[0] if vecs else []), model

    # ------------------------------------------------------------------
    # RAG 回答生成
    # ------------------------------------------------------------------
    def answer_with_context(
        self, query: str, contexts: list[dict[str, Any]]
    ) -> str:
        """検索で得たチャンクを根拠に回答文を生成する。"""
        if not contexts:
            return "関連する記録が見つかりませんでした。"
        if self.enabled:
            joined = "\n\n".join(
                f"[{i + 1}] ({c['source']}:{c['ref']}) {c['text']}"
                for i, c in enumerate(contexts)
            )
            messages = [
                {
                    "role": "system",
                    "content": (
                        "以下の抜粋のみを根拠に、日本語で簡潔に回答してください。"
                        "抜粋に無いことは『記録から判断できません』と述べること。"
                        "根拠にした抜粋番号を文末に [1][2] のように示すこと。"
                    ),
                },
                {"role": "user", "content": f"質問: {query}\n\n抜粋:\n{joined}"},
            ]
            for attempt in range(2):
                try:
                    resp = self._client.chat.completions.create(  # type: ignore[union-attr]
                        model=self._chat_model, messages=messages, temperature=0.2
                    )
                    return resp.choices[0].message.content or ""
                except Exception as exc:
                    logger.error("RAG 回答生成失敗 (attempt=%d): %s", attempt + 1, exc)
        # フォールバック: 上位チャンクの要約列挙
        lines = [f"- ({c['source']}:{c['ref']}) {c['text'][:120]}" for c in contexts[:3]]
        return "AI 未接続のため、関連する記録を提示します:\n" + "\n".join(lines)


# ----------------------------------------------------------------------
# フォールバック実装(ルールベース)
# ----------------------------------------------------------------------
def _fallback_report(
    week: str,
    metrics: dict[str, float],
    diff_digest: dict[str, Any],
    prev_kpt: dict[str, Any] | None,
) -> dict[str, Any]:
    """AI 未接続時の簡易 KPT。指標から機械的に導出する。"""
    m = metrics
    ev = lambda name: [f"{name}@{week}"]  # noqa: E731

    keep: list[dict[str, Any]] = []
    problem: list[dict[str, Any]] = []
    done: list[dict[str, Any]] = []
    learned: list[dict[str, Any]] = []
    try_items: list[dict[str, Any]] = []

    if m.get("github_prs_merged", 0) > 0:
        keep.append({
            "title": f"PR を {int(m['github_prs_merged'])} 件マージ",
            "detail": "レビューからマージまで到達できた。",
            "evidence": ev("github_prs_merged"),
        })
    if m.get("trello_cards_done", 0) > 0:
        done.append({
            "title": f"カードを {int(m['trello_cards_done'])} 件完了",
            "detail": "Done リストへ移動したカード。",
            "evidence": ev("trello_cards_done"),
        })
    if m.get("github_stale_prs", 0) >= 3:
        problem.append({
            "title": f"レビュー待ち PR が {int(m['github_stale_prs'])} 件滞留",
            "detail": "オープンから 3 日以上マージされていない PR がある。",
            "evidence": ev("github_stale_prs"),
        })
        try_items.append({
            "title": "レビュー担当のローテーションを決める",
            "detail": "滞留 PR を毎朝トリアージする。",
            "followup_of": "",
        })
    if m.get("trello_cards_created", 0) > m.get("trello_cards_done", 0):
        problem.append({
            "title": "作成ペースが完了ペースを上回っている",
            "detail": (
                f"作成 {int(m['trello_cards_created'])} 件 / 完了 "
                f"{int(m['trello_cards_done'])} 件。"
            ),
            "evidence": ev("trello_cards_created") + ev("trello_cards_done"),
        })
    if m.get("github_issues_reopened", 0) > 0:
        problem.append({
            "title": f"issue の再オープンが {int(m['github_issues_reopened'])} 件",
            "detail": "修正が不十分だった可能性がある。",
            "evidence": ev("github_issues_reopened"),
        })
    learned.append({
        "title": "指標の推移を継続的に観察する",
        "detail": "投稿数・WIP・stale PR の変化が早期警告になる。",
        "evidence": ev("mattermost_posts"),
    })

    summary_md = (
        f"## {week} 週次サマリ(自動生成 / AI未接続)\n\n"
        f"- Mattermost 投稿: {int(m.get('mattermost_posts', 0))} 件 "
        f"(アクティブ {int(m.get('mattermost_active_users', 0))} 人)\n"
        f"- コミット: {int(m.get('github_commits', 0))} / PR マージ: "
        f"{int(m.get('github_prs_merged', 0))} / stale PR: "
        f"{int(m.get('github_stale_prs', 0))}\n"
        f"- カード作成 {int(m.get('trello_cards_created', 0))} / 完了 "
        f"{int(m.get('trello_cards_done', 0))} / WIP {int(m.get('trello_wip', 0))}\n"
        f"- GROWI 作成 {int(m.get('growi_pages_created', 0))} / 更新 "
        f"{int(m.get('growi_pages_updated', 0))}\n"
    )
    return {
        "keep": keep,
        "problem": problem,
        "done": done,
        "learned": learned,
        "try": try_items,
        "summary_md": summary_md,
    }


def _fallback_risks(
    week: str,
    metrics: dict[str, float],
    trend: dict[str, dict[str, float]],
    actor_load: dict[str, int],
) -> list[dict[str, Any]]:
    """AI 未接続時のルールベース リスク検出。"""
    m = metrics
    risks: list[dict[str, Any]] = []

    if m.get("github_stale_prs", 0) >= 3:
        risks.append({
            "category": "進捗の滞留",
            "severity": "high" if m["github_stale_prs"] >= 5 else "mid",
            "title": f"レビュー待ち PR が {int(m['github_stale_prs'])} 件",
            "detail": "オープンから 3 日以上マージされていない PR が積み上がっている。",
            "evidence": [f"github_stale_prs@{week}"],
        })
    if m.get("trello_cards_created", 0) > m.get("trello_cards_done", 0) * 1.5:
        risks.append({
            "category": "スコープ膨張",
            "severity": "mid",
            "title": "カード作成ペースが完了ペースを大きく上回る",
            "detail": (
                f"作成 {int(m['trello_cards_created'])} 件に対し完了 "
                f"{int(m['trello_cards_done'])} 件。WIP は {int(m.get('trello_wip', 0))}。"
            ),
            "evidence": [f"trello_cards_created@{week}", f"trello_cards_done@{week}"],
        })
    if m.get("github_issues_reopened", 0) > 0:
        risks.append({
            "category": "品質リスク",
            "severity": "mid",
            "title": f"issue の再オープンが {int(m['github_issues_reopened'])} 件",
            "detail": "同じ不具合が再発している可能性がある。",
            "evidence": [f"github_issues_reopened@{week}"],
        })
    # コミュニケーション低下: 直近週で投稿数が減少傾向か
    weeks_sorted = sorted(trend.keys())
    if len(weeks_sorted) >= 2:
        first = trend[weeks_sorted[0]].get("mattermost_posts", 0)
        last = trend[weeks_sorted[-1]].get("mattermost_posts", 0)
        if first > 0 and last < first * 0.6:
            risks.append({
                "category": "コミュニケーション低下",
                "severity": "mid",
                "title": "Mattermost 投稿数が減少傾向",
                "detail": f"{weeks_sorted[0]} の {int(first)} 件から {weeks_sorted[-1]} の {int(last)} 件へ減少。",
                "evidence": [f"mattermost_posts@{weeks_sorted[-1]}"],
            })
    # 負荷の偏り
    if actor_load:
        total = sum(actor_load.values())
        top_actor, top_n = max(actor_load.items(), key=lambda kv: kv[1])
        if total > 0 and top_n / total >= 0.5:
            risks.append({
                "category": "負荷の偏り",
                "severity": "high" if top_n / total >= 0.65 else "mid",
                "title": f"コミットが {top_actor} に集中",
                "detail": f"週内コミットの {round(top_n / total * 100)}% を 1 人が占める(バスファクター)。",
                "evidence": [f"github_commits@{week}"],
            })
    if m.get("github_commits", 0) > 0 and m.get("growi_pages_updated", 0) == 0:
        risks.append({
            "category": "ドキュメント腐敗",
            "severity": "low",
            "title": "コード変更に対し Wiki 更新なし",
            "detail": f"コミット {int(m['github_commits'])} 件に対し GROWI 更新は 0 件。",
            "evidence": [f"github_commits@{week}", f"growi_pages_updated@{week}"],
        })
    return risks


_DECISION_PATTERNS = [
    "することにした",
    "することにしました",
    "で合意",
    "に決定",
    "を採用",
    "は見送り",
    "はやめ",
    "で行く",
    "にしましょう",
    "に統一",
]


def _fallback_decisions(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """AI 未接続時: 決定パターンを含む投稿を素朴に抽出する。"""
    decisions: list[dict[str, Any]] = []
    for p in posts:
        text_val = p.get("text", "")
        if any(pat in text_val for pat in _DECISION_PATTERNS):
            decisions.append({
                "summary": text_val.strip(),
                "rationale": "",
                "participants": [p.get("actor", "unknown")],
                "source_refs": [p.get("ref", "")],
            })
    return decisions
