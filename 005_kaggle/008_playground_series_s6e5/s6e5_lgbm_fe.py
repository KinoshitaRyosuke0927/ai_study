"""
F1 ピットストップ予測 - 特徴量エンジニアリング版
ベースライン (s6e5_baseline.py) からの変更点:
  1. グループ集計特徴量: (Compound, Race) ごとの標準的スティント長を推定
     → CV-safe: 各フォールドの訓練データのみから計算してリーク防止
  2. TyreLife_Ratio: 現在のタイヤが想定寿命の何%まで来ているか
  3. ラグ特徴量: 直前2周のLapTime / 劣化トレンドの方向と加速度
  4. ドライバー別ピット傾向: 攻め型(短スティント)/守り型(長スティント)の特性

ターゲットリーク対策:
  - PitNextLap=1 から計算するグループ統計はCVループ内（訓練折のみ）で算出
  - ラグ特徴量はLapTimeなど目的変数に依存しない値のみ使用→ループ外でOK
"""
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score
import lightgbm as lgb

# ── パス設定 ──────────────────────────────────────────────
DATA_DIR   = Path(__file__).parent.parent / "competitions" / "playground-series-s6e5"
OUTPUT_DIR = Path(__file__).parent
OUTPUT_DIR.mkdir(exist_ok=True)

# ── データ読み込み ─────────────────────────────────────────
train_raw = pd.read_csv(DATA_DIR / "train.csv")
test_raw  = pd.read_csv(DATA_DIR / "test.csv")

TARGET = "PitNextLap"
ID_COL = "id"

print(f"Train: {train_raw.shape}  Test: {test_raw.shape}")

# ── Step 1: ターゲット非依存の特徴量（ループ外で計算） ────────
# ラグ特徴量・ベースライン特徴量は PitNextLap を使わないため安全

COMPOUND_DUR = {"SOFT": 1, "MEDIUM": 2, "HARD": 3, "INTERMEDIATE": 4, "WET": 5}

def add_static_features(df: pd.DataFrame, global_mean_laptime: float) -> pd.DataFrame:
    """PitNextLap に依存しない特徴量（ループ外で一度だけ計算）"""
    df = df.copy()
    df["TyreLife_sq"]         = df["TyreLife"] ** 2
    df["TyreLife_sqrt"]       = np.sqrt(df["TyreLife"].clip(0))
    df["Degradation_Rate"]    = df["Cumulative_Degradation"] / (df["TyreLife"] + 1)
    df["Compound_Dur"]        = df["Compound"].map(COMPOUND_DUR).fillna(2)
    df["TyreLife_x_Dur"]      = df["TyreLife"] / df["Compound_Dur"]
    df["LapTime_Norm"]        = df["LapTime (s)"] / global_mean_laptime
    df["Position_sq"]         = df["Position"] ** 2
    df["Progress_x_TyreLife"] = df["RaceProgress"] * df["TyreLife"]
    return df


def add_lag_features(df: pd.DataFrame) -> pd.DataFrame:
    """ラグ特徴量（LapTimeなどの実測値のみ使用→ターゲットリークなし）"""
    df = df.copy()
    df = df.sort_values(["Driver", "Race", "Year", "LapNumber"])
    grp = df.groupby(["Driver", "Race", "Year"])

    df["LapTime_Lag1"]  = grp["LapTime (s)"].shift(1)
    df["LapTime_Lag2"]  = grp["LapTime (s)"].shift(2)
    df["LapTime_Trend"] = df["LapTime (s)"] - df["LapTime_Lag1"]
    df["LapTime_Trend2"]= df["LapTime_Lag1"] - df["LapTime_Lag2"]
    df["LapTime_Accel"] = df["LapTime_Trend"] - df["LapTime_Trend2"]
    df["Delta_Change"]  = grp["LapTime_Delta"].diff()

    lag_cols = ["LapTime_Lag1", "LapTime_Lag2", "LapTime_Trend",
                "LapTime_Trend2", "LapTime_Accel", "Delta_Change"]
    for col in lag_cols:
        df[col] = df[col].fillna(df[col].median())

    return df


# train+test を結合してラグ計算（test 行の直前周が train 内の場合も正確に取得）
global_mean_laptime = train_raw["LapTime (s)"].mean()
test_raw[TARGET] = np.nan
combined = pd.concat([train_raw, test_raw], ignore_index=True)
combined = add_static_features(combined, global_mean_laptime)
combined = add_lag_features(combined)

train_base = combined[combined[TARGET].notna()].sort_values(ID_COL).reset_index(drop=True)
test_base  = combined[combined[TARGET].isna()].sort_values(ID_COL).reset_index(drop=True)


# ── Step 2: CV-safe グループ統計の計算関数 ─────────────────
# この関数は各フォールドの訓練データのみを受け取り、統計を計算して返す。
# バリデーション/テストへの適用時は未知の組み合わせにフォールバックを使う。

def compute_group_stats(train_fold: pd.DataFrame):
    """訓練折のみから (Compound, Race) 別のスティント長統計を計算"""
    pit = train_fold[train_fold[TARGET] == 1]

    stint_stats = (
        pit.groupby(["Compound", "Race"])["TyreLife"]
        .agg(median="median", std="std")
        .rename(columns={"median": "Expected_Stint_Len", "std": "Stint_Len_Std"})
        .reset_index()
    )
    compound_median = pit.groupby("Compound")["TyreLife"].median()
    compound_std    = pit.groupby("Compound")["TyreLife"].std()
    driver_style    = pit.groupby("Driver")["TyreLife"].median()
    overall_median  = float(pit["TyreLife"].median())
    return stint_stats, compound_median, compound_std, driver_style, overall_median


def apply_group_stats(df: pd.DataFrame, stint_stats, compound_median,
                      compound_std, driver_style, overall_median) -> pd.DataFrame:
    """計算済みのグループ統計を df に付与する"""
    df = df.copy()

    df = df.merge(stint_stats, on=["Compound", "Race"], how="left")

    # (Compound, Race) 未登場 → Compound 単位で補完
    mask = df["Expected_Stint_Len"].isna()
    df.loc[mask, "Expected_Stint_Len"] = df.loc[mask, "Compound"].map(compound_median)
    df.loc[mask, "Stint_Len_Std"]      = df.loc[mask, "Compound"].map(compound_std)

    # それでも欠損 → 全体中央値
    df["Expected_Stint_Len"] = df["Expected_Stint_Len"].fillna(overall_median)
    df["Stint_Len_Std"]      = df["Stint_Len_Std"].fillna(df["Stint_Len_Std"].median())

    df["TyreLife_Ratio"]       = df["TyreLife"] / df["Expected_Stint_Len"].clip(lower=1)
    df["Laps_To_Expected_Pit"] = df["Expected_Stint_Len"] - df["TyreLife"]
    df["Stint_Uncertainty"]    = df["Stint_Len_Std"] / df["Expected_Stint_Len"].clip(lower=1)

    df["Driver_Avg_Pit_Life"] = df["Driver"].map(driver_style).fillna(overall_median)
    df["TyreLife_vs_Driver"]  = df["TyreLife"] - df["Driver_Avg_Pit_Life"]

    return df


# ── カテゴリ変数のエンコード ────────────────────────────────
cat_cols = ["Driver", "Compound", "Race"]
encoders = {}
for col in cat_cols:
    le = LabelEncoder()
    combined_vals = pd.concat([train_base[col], test_base[col]], axis=0).astype(str)
    le.fit(combined_vals)
    train_base[col] = le.transform(train_base[col].astype(str))
    test_base[col]  = le.transform(test_base[col].astype(str))
    encoders[col] = le

# ── 特徴量リスト（グループ統計の列は後でCVループ内で追加） ──
GROUP_STAT_COLS = ["Expected_Stint_Len", "Stint_Len_Std", "TyreLife_Ratio",
                   "Laps_To_Expected_Pit", "Stint_Uncertainty",
                   "Driver_Avg_Pit_Life", "TyreLife_vs_Driver"]
STATIC_COLS = [c for c in train_base.columns if c not in [ID_COL, TARGET]]
FEATURES    = STATIC_COLS  # GROUP_STAT_COLS は後で追加
print(f"\nStatic 特徴量: {len(FEATURES)} 個")
print(f"Group 統計特徴量 (CV-safe): {GROUP_STAT_COLS}")

# ── 5-Fold CV（グループ統計を各折の訓練データから計算） ────
skf        = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
X_arr      = train_base[FEATURES].values
y_arr      = train_base[TARGET].values

# テストへの適用は全訓練データから計算した統計を使う（CV終了後）
oof_probs  = np.zeros(len(X_arr))
test_probs = np.zeros(len(test_base))
cv_scores  = []

print("\n=== 5-Fold Cross Validation ===")

all_features = None  # 最終的な特徴量リスト（最初のfoldで確定）

for fold, (tr_idx, val_idx) in enumerate(skf.split(X_arr, y_arr), 1):
    train_fold = train_base.iloc[tr_idx].copy()
    val_fold   = train_base.iloc[val_idx].copy()

    # ターゲットが見える訓練折からのみグループ統計を計算
    stint_stats, compound_median, compound_std, driver_style, overall_median = \
        compute_group_stats(train_fold)

    train_fold = apply_group_stats(train_fold, stint_stats, compound_median,
                                   compound_std, driver_style, overall_median)
    val_fold   = apply_group_stats(val_fold,   stint_stats, compound_median,
                                   compound_std, driver_style, overall_median)

    if all_features is None:
        all_features = [c for c in train_fold.columns if c not in [ID_COL, TARGET]]
        print(f"全特徴量数: {len(all_features)} 個")

    X_tr  = train_fold[all_features].values
    y_tr  = train_fold[TARGET].values
    X_val = val_fold[all_features].values
    y_val = val_fold[TARGET].values

    dtrain = lgb.Dataset(X_tr,  label=y_tr,  feature_name=all_features)
    dval   = lgb.Dataset(X_val, label=y_val, reference=dtrain)

    model = lgb.train(
        {
            "objective": "binary", "metric": "auc",
            "learning_rate": 0.05, "num_leaves": 127,
            "min_child_samples": 20,
            "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1,
            "lambda_l1": 0.1, "lambda_l2": 0.1,
            "is_unbalance": True, "verbose": -1, "seed": 42,
        },
        dtrain,
        num_boost_round=2000,
        valid_sets=[dval],
        callbacks=[
            lgb.early_stopping(stopping_rounds=100, verbose=False),
            lgb.log_evaluation(period=200),
        ],
    )

    val_pred = model.predict(X_val)
    fold_auc = roc_auc_score(y_val, val_pred)
    cv_scores.append(fold_auc)
    oof_probs[val_idx] = val_pred

    # テスト予測: この折の統計でグループ特徴量を付与してから予測
    test_fold = apply_group_stats(test_base.copy(), stint_stats, compound_median,
                                  compound_std, driver_style, overall_median)
    test_probs += model.predict(test_fold[all_features].values) / skf.n_splits

    print(f"  Fold {fold}  best_iter={model.best_iteration:4d}  AUC={fold_auc:.5f}")

oof_auc = roc_auc_score(y_arr, oof_probs)
print(f"\nOOF AUC : {oof_auc:.5f}  (各Fold平均: {np.mean(cv_scores):.5f} +/- {np.std(cv_scores):.5f})")
print(f"Baseline: 0.94840")
print(f"改善幅  : {oof_auc - 0.94840:+.5f}")

# ── 特徴量重要度 ───────────────────────────────────────────
fi = pd.DataFrame({"feature": all_features, "importance": model.feature_importance("gain")})
fi = fi.sort_values("importance", ascending=False)
print("\n=== 特徴量重要度 (Top 20) ===")
print(fi.head(20).to_string(index=False))

# ── 提出ファイル作成 ──────────────────────────────────────
submission = pd.DataFrame({"id": test_base[ID_COL], "PitNextLap": test_probs})
out_path   = OUTPUT_DIR / "submission_lgbm_fe.csv"
submission.to_csv(out_path, index=False)
print(f"\nSubmission saved -> {out_path}")
print(f"予測確率の統計: mean={test_probs.mean():.4f}  min={test_probs.min():.4f}  max={test_probs.max():.4f}")
