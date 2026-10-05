"""「リマインド対象の投稿には特定の単語が含まれているのではないか」という仮説を検証する
調査用スクリプト。

以下の3つを行う。
1. 単語ごとの出現傾向の集計: 各単語が「リマインド必要(1)」「不要(0)」の投稿に
   それぞれ何割含まれるか、その単語を含む投稿のうち何割が1か(適合率)を算出し、
   1側に偏っている単語をオッズ比のz値で順位付けする
2. 人手で用意したキーワード辞書による判定: 「締切」「提出」などの直感的な語を
   1つでも含めば1と判定するルールの精度を測る
3. データから選んだキーワードによる判定: 学習用データで1側に偏っている上位K語を選び、
   評価用データで「含まれるキーワード数」をスコアとして判定する(層化5分割交差検証)。
   compare_light_models.py の機械学習モデル(TF-IDF + ロジスティック回帰など)と比べて、
   「キーワードの有無だけでどこまで判定できるか」を確認する

実行方法: 011_chat_linkage ディレクトリで
    python -m app.model.analyze_keywords
結果は app/model/compare_results/ にCSVで保存される。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, precision_recall_curve, precision_recall_fscore_support
from sklearn.model_selection import StratifiedKFold

from app.model.compare_light_models import (
    N_SPLITS,
    RESULT_DIR,
    TARGET_PRECISION,
    normalize_text,
)
from app.model.train_model import RANDOM_SEED, load_labeled_posts

# 集計対象とする単語の最低出現投稿数(少なすぎる単語は偶然の偏りが大きいため除外)
MIN_DOC_FREQ = 10
# データから選ぶキーワード数の候補
TOP_K_LIST = [5, 10, 20, 50, 100]
# 内容語として扱う品詞(助詞・助動詞・記号などを除いた、人が読んで意味のわかる語)
CONTENT_POS = ("名詞", "動詞", "形容詞", "副詞")

# 人手で用意したキーワード辞書(締め切り・提出物・依頼・注意喚起を表す直感的な語)
HAND_KEYWORDS = [
    "締切", "締め切り", "〆切", "期限", "期日", "までに", "提出", "回答", "申請", "登録",
    "入力", "お願いします", "お願いいたします", "各自", "必ず", "忘れず", "ご確認", "ご注意", "注意",
    "実施", "対応",
]

_tagger = None


def tokenize_terms(text: str) -> tuple[set[str], set[str]]:
    """
    テキストを形態素解析し、投稿内に含まれる単語の集合を2種類返す

    Args
    -----------------
    - text: str,   正規化済みのテキスト

    Returns
    -----------------
    - all_terms: set[str],       全単語の1gram・2gram(記号・助詞なども含む)
    - content_terms: set[str],   内容語(名詞・動詞・形容詞・副詞)の1gram

    """
    global _tagger
    # Taggerは生成コストが高いため、初回のみ生成してモジュール内に保持する
    if _tagger is None:
        import fugashi

        _tagger = fugashi.Tagger()
    words = [w for w in _tagger(text) if w.surface.strip()]
    surfaces = [w.surface for w in words]
    # 全単語: 1gramと、隣り合う2単語をつなげた2gram
    all_terms = set(surfaces) | {f"{a} {b}" for a, b in zip(surfaces, surfaces[1:])}
    # 内容語: 品詞が名詞・動詞・形容詞・副詞の単語のみ(数字だけの語は除く)
    content_terms = {
        w.surface for w in words if w.feature.pos1 in CONTENT_POS and not w.surface.isdigit()
    }
    return all_terms, content_terms


def term_statistics(term_sets: list[set[str]], y: np.ndarray, min_df: int = MIN_DOC_FREQ) -> pd.DataFrame:
    """
    単語ごとに、1/0それぞれの投稿での出現割合・適合率・1側への偏り(オッズ比のz値)を集計する

    Args
    -----------------
    - term_sets: list[set[str]],   投稿ごとの単語集合
    - y: np.ndarray,               投稿ごとのラベル(0/1)
    - min_df: int,                 集計対象とする最低出現投稿数

    Returns
    -----------------
    - stats: pd.DataFrame,   単語ごとの集計結果(z値の降順)

    """
    n_pos = int(y.sum())
    n_neg = len(y) - n_pos
    # 単語ごとに、1の投稿・0の投稿それぞれで何件に含まれるかを数える
    df_pos: dict[str, int] = {}
    df_neg: dict[str, int] = {}
    for terms, label in zip(term_sets, y):
        target = df_pos if label == 1 else df_neg
        for term in terms:
            target[term] = target.get(term, 0) + 1

    rows = []
    for term in set(df_pos) | set(df_neg):
        a, c = df_pos.get(term, 0), df_neg.get(term, 0)
        # 出現投稿数が少ない単語は除外
        if a + c < min_df:
            continue
        b, d = n_pos - a, n_neg - c
        # 2×2分割表から対数オッズ比とその標準誤差を算出(0件対策で各セルに0.5を加える)
        log_or = np.log((a + 0.5) * (d + 0.5) / ((b + 0.5) * (c + 0.5)))
        se = np.sqrt(1 / (a + 0.5) + 1 / (b + 0.5) + 1 / (c + 0.5) + 1 / (d + 0.5))
        rows.append(
            {
                "term": term,
                "docs_1": a,
                "docs_0": c,
                "coverage_1": a / n_pos,
                "coverage_0": c / n_neg,
                "precision": a / (a + c),
                "z": log_or / se,
            }
        )
    return pd.DataFrame(rows).sort_values("z", ascending=False).reset_index(drop=True)


def rule_scores(y_true: np.ndarray, hits: np.ndarray) -> dict:
    """
    「含まれるキーワード数」をスコアとしたルール判定の評価指標を算出する

    Args
    -----------------
    - y_true: np.ndarray,   正解ラベル(0/1)
    - hits: np.ndarray,     投稿ごとの含まれるキーワード数

    Returns
    -----------------
    - scores: dict,   評価指標名 → 値

    """
    scores: dict = {"PR-AUC": average_precision_score(y_true, hits)}
    # 「1語でも含めば1」と判定した場合の精度
    p, r, f, _ = precision_recall_fscore_support(y_true, (hits >= 1).astype(int), average="binary", zero_division=0)
    scores.update({"P@hit>=1": p, "R@hit>=1": r, "F1@hit>=1": f})
    # 「何語以上含めば1」とするかを動かしたときのF1最大値
    precision, recall, thresholds = precision_recall_curve(y_true, hits)
    f1 = 2 * precision * recall / np.clip(precision + recall, 1e-12, None)
    best_idx = int(np.argmax(f1[:-1]))
    scores["bestF1"] = f1[best_idx]
    scores["bestF1_hits"] = thresholds[best_idx]
    # 適合率TARGET_PRECISION以上を保てる中での最大の再現率
    ok = precision[:-1] >= TARGET_PRECISION
    scores[f"R@P>={TARGET_PRECISION}"] = recall[:-1][ok].max() if ok.any() else 0.0
    return scores


def evaluate_hand_keywords(norm_texts: list[str], y: np.ndarray) -> tuple[pd.DataFrame, dict, np.ndarray]:
    """
    人手キーワード辞書(HAND_KEYWORDS)の各語の傾向と、辞書全体でのルール判定精度を算出する
    (辞書はデータを見ずに決めたものなので、全データでそのまま評価できる)

    Args
    -----------------
    - norm_texts: list[str],   正規化済みのテキスト
    - y: np.ndarray,           ラベル(0/1)

    Returns
    -----------------
    - per_word: pd.DataFrame,   キーワードごとの出現割合・適合率
    - scores: dict,             辞書全体でのルール判定の評価指標
    - hits: np.ndarray,         投稿ごとの含まれるキーワード数

    """
    n_pos = int(y.sum())
    n_neg = len(y) - n_pos
    # 投稿×キーワードの「含む/含まない」行列(部分一致)を作成
    contains = np.array([[kw in text for kw in HAND_KEYWORDS] for text in norm_texts])
    rows = []
    # キーワードごとに、1/0それぞれの投稿での出現割合と適合率を算出
    for j, kw in enumerate(HAND_KEYWORDS):
        a = int(contains[y == 1, j].sum())
        c = int(contains[y == 0, j].sum())
        rows.append(
            {
                "keyword": kw,
                "docs_1": a,
                "docs_0": c,
                "coverage_1": a / n_pos,
                "coverage_0": c / n_neg,
                "precision": a / (a + c) if a + c else np.nan,
            }
        )
    hits = contains.sum(axis=1)
    return pd.DataFrame(rows).sort_values("coverage_1", ascending=False), rule_scores(y, hits), hits


def evaluate_data_keywords(term_sets: list[set[str]], y: np.ndarray, label: str) -> pd.DataFrame:
    """
    学習用データで選んだ上位K語によるルール判定を、層化K分割交差検証で評価する
    (キーワード選定に評価用データを使わないよう、分割ごとに選び直す)

    Args
    -----------------
    - term_sets: list[set[str]],   投稿ごとの単語集合
    - y: np.ndarray,               ラベル(0/1)
    - label: str,                  結果表に記載する単語の種類名

    Returns
    -----------------
    - result: pd.DataFrame,   キーワード数Kごとの評価指標の表

    """
    skf = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_SEED)
    hits = {k: np.zeros(len(y)) for k in TOP_K_LIST}
    # 分割ごとに、学習用データだけで単語の偏りを集計し、上位K語を評価用データに当てはめる
    for train_idx, test_idx in skf.split(np.zeros(len(y)), y):
        stats = term_statistics([term_sets[i] for i in train_idx], y[train_idx], min_df=5)
        for k in TOP_K_LIST:
            keywords = set(stats["term"].head(k))
            for i in test_idx:
                hits[k][i] = len(term_sets[i] & keywords)
    rows = [{"terms": label, "K": k, **rule_scores(y, hits[k])} for k in TOP_K_LIST]
    return pd.DataFrame(rows)


def main() -> None:
    """
    単語の出現傾向の集計・人手辞書の評価・データ由来キーワードの評価を順に実行し、
    結果を表示・保存する
    """
    # ラベル付けCSVから全データを読み込み、メンション・URLを正規化
    texts, labels = load_labeled_posts()
    y = np.array(labels)
    norm_texts = [normalize_text(t) for t in texts]
    print(f"データ: {len(texts)}件 (1={y.sum()}件, 0={len(y) - y.sum()}件, 1の割合={y.mean():.1%})")
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 20)
    pd.set_option("display.float_format", "{:.3f}".format)

    # 投稿ごとに単語の集合(全単語 / 内容語)を作成
    tokenized = [tokenize_terms(t) for t in norm_texts]
    all_sets = [t[0] for t in tokenized]
    content_sets = [t[1] for t in tokenized]

    # 1. 単語ごとの出現傾向(全データ)
    for name, sets in (("content", content_sets), ("all", all_sets)):
        stats = term_statistics(sets, y)
        stats.to_csv(RESULT_DIR / f"keyword_stats_{name}.csv", encoding="utf-8-sig", index=False)
        print(f"\n=== 1側に偏っている単語 上位30({name}) ===")
        print(stats.head(30).to_string())
        print(f"\n=== 0側に偏っている単語 上位15({name}) ===")
        print(stats.tail(15).iloc[::-1].to_string())

    # 2. 人手キーワード辞書による判定
    per_word, hand_scores, hand_hits = evaluate_hand_keywords(norm_texts, y)
    per_word.to_csv(RESULT_DIR / "keyword_hand_dictionary.csv", encoding="utf-8-sig", index=False)
    print("\n=== 人手キーワード辞書: 各語の傾向 ===")
    print(per_word.to_string(index=False))
    print("\n=== 人手キーワード辞書: 辞書全体でのルール判定 ===")
    print({k: round(float(v), 3) for k, v in hand_scores.items()})
    # 辞書のどの語も含まない「1」の投稿、どれかを含む「0」の投稿の件数
    print(f"どの語も含まない1の投稿: {int(((hand_hits == 0) & (y == 1)).sum())}件 / {y.sum()}件")
    print(f"どれかを含む0の投稿    : {int(((hand_hits >= 1) & (y == 0)).sum())}件 / {len(y) - y.sum()}件")

    # 3. データから選んだ上位K語によるルール判定(交差検証)
    print(f"\n=== データから選んだ上位K語によるルール判定(層化{N_SPLITS}分割交差検証) ===")
    rule_result = pd.concat(
        [evaluate_data_keywords(content_sets, y, "content"), evaluate_data_keywords(all_sets, y, "all")]
    )
    print(rule_result.to_string(index=False))
    rule_result.to_csv(RESULT_DIR / "keyword_rule_cv.csv", encoding="utf-8-sig", index=False)
    print(f"\n結果を {RESULT_DIR} に保存しました。")


if __name__ == "__main__":
    main()
