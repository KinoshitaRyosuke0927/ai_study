"""業務状況(オフィス / オフィス外 / 休み)の判定と、出社割合の計算。

判定の単位は「1人×1日×30分の枠」。勤務時間(既定 9:00〜18:00 から昼休み 12:00〜13:00 を除く16枠)の
枠ごとにラベルを決め、出社割合 = オフィスの枠の数 ÷ 枠の数 とする(勤務時間は8時間固定。休み・休日は0)。

判定の方法(優先順)
1. 保存済みのラベル(人が付けたもの)
2. 学習したモデル(data/office_model.joblib があれば)
3. キーワードによるルール

学習
- 保存済みのラベルには予定を含めない。学習するときに、ラベルのある日の予定を GROUPSESSION から読み込み直し、
  メモリ上でラベルと組み合わせて、枠ごとの分類モデル(ロジスティック回帰)を学習する(予定名はファイルに残らない)。
- 計算はすべてこのPCの中で行い、外部のサービスには送らない。
- 予定名は文字の並び(2〜3文字)をハッシュ化した特徴量にするため、モデルのファイルに単語の一覧は残らない。
- 人ごとの書き方の癖を学べるよう、「メンバー × 文字の並び」の特徴量も加える。
"""

from __future__ import annotations

import re
import threading
import unicodedata
from datetime import date as date_cls
from datetime import datetime, timedelta
from typing import Callable

import joblib
import numpy as np

from app import schedule_parser, status_store
from app.config import DATA_DIR

MODEL_FILE = DATA_DIR / "office_model.joblib"
SLOT_MINUTES = 30
N_FEATURES = 2 ** 18
# 学習に必要な最低限のラベル数(1人×1日の件数)
MIN_TRAIN_DAYS = 10

# ルールで使うキーワード
OFF_AM = re.compile(r"午前休|午前半休|AM休|ＡＭ休|前休")
OFF_PM = re.compile(r"午後休|午後半休|PM休|ＰＭ休|後休")
OFF = re.compile(r"休暇|有給|有休|年休|代休|振休|特休|夏休|冬休|慶弔|欠勤|(?<!昼)休み")
REMOTE_DAY = re.compile(r"在宅|テレワーク|ﾃﾚﾜｰｸ")
OUTSIDE = re.compile(r"在宅|テレワーク|ﾃﾚﾜｰｸ|リモート勤務|出張|外出|訪問|客先|直行|直帰|移動|常駐|現地")

_model_lock = threading.Lock()


# ============================================================================ 枠

def build_slots(business_start: str, business_end: str, lunch_start: str, lunch_end: str) -> list[str]:
    """
    勤務時間を30分ごとに区切った枠(昼休みを除く)の開始時刻を返す

    Args
    -----------------
    - business_start: str,  業務開始 "HH:MM"
    - business_end: str,    業務終了 "HH:MM"
    - lunch_start: str,     昼休み開始 "HH:MM"
    - lunch_end: str,       昼休み終了 "HH:MM"

    Returns
    -----------------
    - slots: list[str],  枠の開始時刻の一覧(例: ["09:00", "09:30", ..., "17:30"])

    """
    bs, be, ls, le = (_to_min(t) for t in (business_start, business_end, lunch_start, lunch_end))
    slots = []
    for s in range(bs, be - SLOT_MINUTES + 1, SLOT_MINUTES):
        if s < le and s + SLOT_MINUTES > ls:
            continue
        slots.append(_to_hhmm(s))
    return slots


def _to_min(hhmm: str) -> int:
    """
    "HH:MM" を0時からの分に変換する

    Args
    -----------------
    - hhmm: str,  時刻

    Returns
    -----------------
    - minutes: int,  分

    """
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _to_hhmm(minutes: int) -> str:
    """
    分を "HH:MM" に変換する

    Args
    -----------------
    - minutes: int,  0時からの分

    Returns
    -----------------
    - hhmm: str,  時刻

    """
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _overlaps(ev: dict, slot: str) -> bool:
    """
    時刻のある予定が枠と重なるか

    Args
    -----------------
    - ev: dict,    予定(start_time, end_time)
    - slot: str,   枠の開始時刻

    Returns
    -----------------
    - overlaps: bool,  重なれば True

    """
    if ev.get("all_day") or not ev.get("start_time") or not ev.get("end_time"):
        return False
    s = _to_min(slot)
    return _to_min(ev["start_time"]) < s + SLOT_MINUTES and _to_min(ev["end_time"]) > s


def office_ratio(labels: list[str]) -> float:
    """
    出社割合(オフィスの枠の数 ÷ 枠の数)を求める

    Args
    -----------------
    - labels: list[str],  枠ごとのラベル

    Returns
    -----------------
    - ratio: float,  0〜1(小数第3位まで)

    """
    if not labels:
        return 0.0
    return round(sum(1 for v in labels if v == "office") / len(labels), 3)


def day_events_of(events: list[dict], uid: str, date: str) -> list[dict]:
    """
    予定の一覧から、その人のその日の予定を取り出す(期間予定は日をまたぐので multi_day を付ける)

    Args
    -----------------
    - events: list[dict],  予定(uid, start_date, end_date, ...)
    - uid: str,            メンバーのID
    - date: str,           日付 "YYYY-MM-DD"

    Returns
    -----------------
    - day_events: list[dict],  その人のその日の予定

    """
    return [
        {**e, "multi_day": e["start_date"] != e["end_date"]}
        for e in events
        if e["uid"] == uid and e["start_date"] <= date <= e["end_date"]
    ]


# ============================================================================ ルール

def rule_labels(events: list[dict], slots: list[str]) -> list[str]:
    """
    キーワードによるルールで、枠ごとのラベルを決める(何も当てはまらなければオフィス)

    Args
    -----------------
    - events: list[dict],  その人のその日の予定(title, start_time, end_time, all_day)
    - slots: list[str],    枠の開始時刻

    Returns
    -----------------
    - labels: list[str],  枠ごとのラベル("office" / "outside" / "off")

    """
    labels = ["office"] * len(slots)
    noon = 12 * 60

    def mark(index: int, value: str) -> None:
        # 休み > オフィス外 > オフィス の順に優先する
        order = {"office": 0, "outside": 1, "off": 2}
        if order[value] > order[labels[index]]:
            labels[index] = value

    for ev in events:
        title = unicodedata.normalize("NFKC", ev.get("title") or "")
        if ev.get("all_day"):
            # 時刻のない予定: 半休は午前・午後だけ、休暇は終日休み、在宅・出張などは終日オフィス外
            if OFF_AM.search(title):
                for i, s in enumerate(slots):
                    if _to_min(s) < noon:
                        mark(i, "off")
            elif OFF_PM.search(title):
                for i, s in enumerate(slots):
                    if _to_min(s) >= noon:
                        mark(i, "off")
            elif OFF.search(title):
                for i in range(len(slots)):
                    mark(i, "off")
            elif OUTSIDE.search(title):
                for i in range(len(slots)):
                    mark(i, "outside")
            continue

        # 時刻のある予定: 在宅・テレワークの予定は終日オフィス外、それ以外は重なる枠だけ
        if REMOTE_DAY.search(title):
            for i in range(len(slots)):
                mark(i, "outside")
        for i, s in enumerate(slots):
            if not _overlaps(ev, s):
                continue
            if OFF.search(title) or OFF_AM.search(title) or OFF_PM.search(title):
                mark(i, "off")
            elif OUTSIDE.search(title):
                mark(i, "outside")
    return labels


# ============================================================================ 特徴量

def _ngrams(text: str) -> list[str]:
    """
    予定名を、2〜3文字の並びに分ける(表記ゆれを減らすため、全角・半角などをそろえる)

    Args
    -----------------
    - text: str,  予定名

    Returns
    -----------------
    - grams: list[str],  文字の並びの一覧

    """
    t = re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or "").lower())
    grams = [t[i:i + 2] for i in range(len(t) - 1)] + [t[i:i + 3] for i in range(len(t) - 2)]
    return grams or ([t] if t else [])


def slot_features(uid: str, date: str, events: list[dict], slots: list[str]) -> list[list[str]]:
    """
    1人×1日の各枠の特徴量(文字列の一覧)を作る

    Args
    -----------------
    - uid: str,            メンバーのID
    - date: str,           日付 "YYYY-MM-DD"
    - events: list[dict],  その人のその日の予定(title を含む。メモリ上でのみ使う)
    - slots: list[str],    枠の開始時刻

    Returns
    -----------------
    - features: list[list[str]],  枠ごとの特徴量

    """
    weekday = date_cls.fromisoformat(date).weekday()
    all_day = [e for e in events if e.get("all_day")]
    timed = [e for e in events if not e.get("all_day")]

    # 日全体の特徴(時刻のない予定・その日の時刻のある予定の文字)。人ごとの癖も学べるようメンバー付きも加える
    day_tokens = [f"wd={weekday}", f"uid={uid}", f"n_timed={min(len(timed), 5)}", f"n_allday={min(len(all_day), 3)}"]
    for e in all_day:
        day_tokens += ["ad", f"ad_color={e.get('color', '')}", "ad_multi" if e.get("multi_day") else "ad_single"]
        for g in _ngrams(e.get("title", "")):
            day_tokens += [f"ad:{g}", f"u{uid}:ad:{g}"]
    for e in timed:
        day_tokens.append(f"dy_color={e.get('color', '')}")
        for g in _ngrams(e.get("title", "")):
            day_tokens += [f"dy:{g}", f"u{uid}:dy:{g}"]

    # 枠ごとの特徴(時間帯・その枠に重なる予定の文字)
    features = []
    for slot in slots:
        half = "am" if _to_min(slot) < 12 * 60 else "pm"
        tokens = [f"slot={slot}", f"half={half}", f"u{uid}:half={half}", f"wd{weekday}:{half}", *day_tokens]
        overlapping = [e for e in timed if _overlaps(e, slot)]
        tokens.append(f"n_ov={min(len(overlapping), 3)}")
        for e in overlapping:
            tokens.append(f"ov_color={e.get('color', '')}")
            for g in _ngrams(e.get("title", "")):
                tokens += [f"ov:{g}", f"u{uid}:ov:{g}"]
        features.append(tokens)
    return features


def _hasher():
    """
    特徴量(文字列)をハッシュ化して数値の行列にする変換器を返す

    Returns
    -----------------
    - hasher: FeatureHasher,  変換器

    """
    from sklearn.feature_extraction import FeatureHasher

    return FeatureHasher(n_features=N_FEATURES, input_type="string", alternate_sign=False)


# ============================================================================ 学習・推定

def model_info() -> dict | None:
    """
    学習済みモデルの情報を返す

    Returns
    -----------------
    - info: dict | None,  {"trained_at", "n_days", "n_slots", "metrics"}。モデルが無ければ None

    """
    if not MODEL_FILE.exists():
        return None
    bundle = _load_model()
    return {k: bundle[k] for k in ("trained_at", "n_days", "n_slots", "metrics")}


_model_cache: dict = {}


def _load_model() -> dict:
    """
    学習済みモデルを読み込む(ファイルが更新されていなければ読み込み済みのものを使う)

    Returns
    -----------------
    - bundle: dict,  {"model", "trained_at", "n_days", "n_slots", "metrics"}

    """
    mtime = MODEL_FILE.stat().st_mtime
    with _model_lock:
        if _model_cache.get("mtime") != mtime:
            _model_cache.update({"mtime": mtime, "bundle": joblib.load(MODEL_FILE)})
        return _model_cache["bundle"]


def date_ranges(dates: list[str], max_gap_days: int = 7) -> list[tuple[date_cls, date_cls]]:
    """
    ラベルのある日付を、まとめて読み込む期間に分ける(間が max_gap_days 日以内なら同じ期間にする)

    Args
    -----------------
    - dates: list[str],    日付 "YYYY-MM-DD" の一覧
    - max_gap_days: int,   同じ期間にまとめる日付の間隔の上限

    Returns
    -----------------
    - ranges: list[tuple[date, date]],  [(開始日, 終了日)]

    """
    ranges: list[list[date_cls]] = []
    for d in sorted({date_cls.fromisoformat(x) for x in dates}):
        if ranges and d - ranges[-1][1] <= timedelta(days=max_gap_days):
            ranges[-1][1] = d
        else:
            ranges.append([d, d])
    return [(s, e) for s, e in ranges]


def attach_events(records: list[dict], fetch: Callable[[str, date_cls, date_cls], dict],
                  default_group: str) -> tuple[list[dict], int]:
    """
    保存済みのラベルに、GROUPSESSION から読み込み直したその日の予定を組み合わせる(メモリ上のみ)

    Args
    -----------------
    - records: list[dict],  保存済みのラベル
    - fetch:                (グループ, 開始日, 終了日) → {"members", "events"} を返す関数(GROUPSESSION から読み込む)
    - default_group: str,   グループが記録されていないラベルに使うマイグループ(画面で選んでいるもの)

    Returns
    -----------------
    - (joined, skipped):  予定を付けたラベルの一覧と、メンバーが見つからず使えなかったラベルの件数

    """
    # 1. グループごとにラベルをまとめる
    by_group: dict[str, list[dict]] = {}
    for r in records:
        by_group.setdefault(r.get("group") or default_group, []).append(r)

    joined, skipped = [], 0
    for group, recs in by_group.items():
        if not group:
            skipped += len(recs)
            continue
        # 2. ラベルのある日付を期間に分けて、期間ごとに予定を読み込む
        for start, end in date_ranges([r["date"] for r in recs]):
            schedule = fetch(group, start, end)
            uids = {m["uid"] for m in schedule["members"]}
            # 3. その期間のラベルに、その人のその日の予定を付ける(グループにいない人は使わない)
            for r in recs:
                if not start.isoformat() <= r["date"] <= end.isoformat():
                    continue
                if r["uid"] not in uids:
                    skipped += 1
                    continue
                joined.append({**r, "events": day_events_of(schedule["events"], r["uid"], r["date"])})
    return joined, skipped


def _dataset(records: list[dict]):
    """
    予定を付けたラベルから、学習用のデータ(特徴量・ラベル・日付)を作る

    Args
    -----------------
    - records: list[dict],  ラベルの一覧(attach_events で予定を付けたもの)

    Returns
    -----------------
    - (X, y, groups, owners): 特徴量の行列、枠ごとのラベル、枠ごとの日付(評価の分割用)、枠ごとの所属(1人×1日の番号)

    """
    feats, y, groups, owners = [], [], [], []
    for n, r in enumerate(records):
        for tokens, label in zip(slot_features(r["uid"], r["date"], r["events"], r["slots"]), r["labels"]):
            feats.append(tokens)
            y.append(label)
            groups.append(r["date"])
            owners.append(n)
    return _hasher().transform(feats), np.array(y), np.array(groups), np.array(owners)


def _new_model():
    """
    分類モデルを作る(ロジスティック回帰)

    Returns
    -----------------
    - model: LogisticRegression,  未学習のモデル

    """
    from sklearn.linear_model import LogisticRegression

    return LogisticRegression(max_iter=3000, C=2.0)


def train(fetch: Callable[[str, date_cls, date_cls], dict], default_group: str) -> dict:
    """
    保存済みのラベルと、GROUPSESSION から読み込み直した予定からモデルを学習して保存する。
    あわせて、日付ごとに分けた交差検証で精度を求める

    Args
    -----------------
    - fetch:               (グループ, 開始日, 終了日) → 予定 を返す関数(attach_events を参照)
    - default_group: str,  グループが記録されていないラベルに使うマイグループ

    Returns
    -----------------
    - info: dict,  {"trained_at", "n_days", "n_slots", "metrics", "skipped"}

    """
    from sklearn.model_selection import GroupKFold

    # 1. 保存済みのラベルを読み込み、その日の予定を付ける(予定はメモリ上だけで使い、保存しない)
    saved = list(status_store.load_all().values())
    if len(saved) < MIN_TRAIN_DAYS:
        raise ValueError(f"学習には{MIN_TRAIN_DAYS}件(1人×1日)以上のラベルが必要です(現在 {len(saved)}件)")
    # 土日・祝日のラベルは使わない(休日は常に出社割合0として扱うため、学習すると平日の判定がぶれる)
    saved = [r for r in saved if not schedule_parser.is_holiday(r["date"])]
    records, skipped = attach_events(saved, fetch, default_group)
    if len(records) < MIN_TRAIN_DAYS:
        raise ValueError(f"予定を読み込めたラベルが{len(records)}件のため学習できません(メンバーが見つからないラベル {skipped}件)")
    X, y, groups, owners = _dataset(records)
    if len(set(y)) < 2:
        raise ValueError("ラベルが1種類しかないため学習できません(オフィス・オフィス外などが混ざるようにラベルを付けてください)")

    # 精度の確認: 日付で分けて学習・評価し、枠の正解率と、1人×1日の出社割合の平均誤差を求める
    metrics = None
    n_dates = len(set(groups))
    if n_dates >= 3:
        pred = np.empty_like(y)
        for tr, te in GroupKFold(n_splits=min(5, n_dates)).split(X, y, groups):
            if len(set(y[tr])) < 2:
                pred[te] = y[tr][0]
                continue
            pred[te] = _new_model().fit(X[tr], y[tr]).predict(X[te])
        errors = []
        for n in np.unique(owners):
            idx = owners == n
            errors.append(abs(np.mean(y[idx] == "office") - np.mean(pred[idx] == "office")))
        metrics = {
            "slot_accuracy": round(float(np.mean(pred == y)), 3),
            "ratio_mae": round(float(np.mean(errors)), 3),
        }

    # 2. すべてのラベルで学習し直して保存する(保存するのはモデルの重みだけ)
    model = _new_model().fit(X, y)
    info = {
        "trained_at": datetime.now().isoformat(timespec="seconds"),
        "n_days": len(records),
        "n_slots": int(len(y)),
        "metrics": metrics,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, **info}, MODEL_FILE)
    return {**info, "skipped": skipped}


def estimate(members: list[dict], days: list[dict], events: list[dict], slots: list[str]) -> list[dict]:
    """
    メンバー×日付ごとに、枠ごとのラベルと出社割合を求める(保存済みラベル > モデル > ルール。休日は休み)

    Args
    -----------------
    - members: list[dict],  メンバー(uid, name)
    - days: list[dict],     日付(date, holiday)
    - events: list[dict],   予定(uid, start_date, end_date, start_time, end_time, all_day, color, title)。
                            画面から送られたもので、判定に使うだけで保存しない
    - slots: list[str],     枠の開始時刻

    Returns
    -----------------
    - results: list[dict],  [{"uid", "date", "labels", "ratio", "source"}]。source は label / model / rule / holiday

    """
    if not days:
        return []
    dates = [d["date"] for d in days]
    saved = {(r["uid"], r["date"]): r for r in status_store.get_range(
        [m["uid"] for m in members], min(dates), max(dates))}
    bundle = _load_model() if MODEL_FILE.exists() else None

    results, pending = [], []
    for d in days:
        for m in members:
            uid, date = m["uid"], d["date"]
            # 休日は終日休み(出社割合0)
            if d.get("holiday"):
                results.append({"uid": uid, "date": date, "labels": ["off"] * len(slots), "ratio": 0.0, "source": "holiday"})
                continue
            # 保存済みのラベルがあればそれを使う(枠の区切りが今の設定と同じ場合)
            rec = saved.get((uid, date))
            if rec and rec["slots"] == slots:
                results.append({"uid": uid, "date": date, "labels": rec["labels"], "ratio": office_ratio(rec["labels"]), "source": "label"})
                continue
            # その人のその日の予定
            day_events = day_events_of(events, uid, date)
            if bundle is None:
                labels = rule_labels(day_events, slots)
                results.append({"uid": uid, "date": date, "labels": labels, "ratio": office_ratio(labels), "source": "rule"})
            else:
                pending.append((uid, date, day_events, len(results)))
                results.append(None)

    # モデルでまとめて推定する
    if pending:
        feats = [t for uid, date, evs, _ in pending for t in slot_features(uid, date, evs, slots)]
        pred = bundle["model"].predict(_hasher().transform(feats))
        n = len(slots)
        for k, (uid, date, _, pos) in enumerate(pending):
            labels = [str(v) for v in pred[k * n:(k + 1) * n]]
            results[pos] = {"uid": uid, "date": date, "labels": labels, "ratio": office_ratio(labels), "source": "model"}
    return results
