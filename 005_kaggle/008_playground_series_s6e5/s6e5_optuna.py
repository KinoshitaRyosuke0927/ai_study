"""
F1 ピットストップ予測 - Optuna ハイパーパラメータ最適化
ベースライン (s6e5_baseline.py) と同じ特徴量を使用し、LightGBM の
パラメータを Optuna で自動探索する。

探索戦略:
  - Optuna フェーズ: 3-Fold CV × 50 trials（速度優先）
  - 最終評価フェーズ: 5-Fold CV（ベースラインと同条件で比較）
"""
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score
import lightgbm as lgb
import optuna
from optuna.samplers import TPESampler

optuna.logging.set_verbosity(optuna.logging.WARNING)

# ── パス設定 ──────────────────────────────────────────────
DATA_DIR   = Path(__file__).parent.parent / "competitions" / "playground-series-s6e5"
OUTPUT_DIR = Path(__file__).parent
OUTPUT_DIR.mkdir(exist_ok=True)

# ── データ読み込み ─────────────────────────────────────────
train = pd.read_csv(DATA_DIR / "train.csv")
test  = pd.read_csv(DATA_DIR / "test.csv")

TARGET = "PitNextLap"
ID_COL = "id"

print(f"Train: {train.shape}  Test: {test.shape}")

# ── ベースラインと同じ特徴量エンジニアリング ─────────────────
def add_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["TyreLife_sq"]         = df["TyreLife"] ** 2
    df["TyreLife_sqrt"]       = np.sqrt(df["TyreLife"].clip(0))
    df["Degradation_Rate"]    = df["Cumulative_Degradation"] / (df["TyreLife"] + 1)
    compound_durability       = {"SOFT": 1, "MEDIUM": 2, "HARD": 3, "INTERMEDIATE": 4, "WET": 5}
    df["Compound_Dur"]        = df["Compound"].map(compound_durability).fillna(2)
    df["TyreLife_x_Dur"]      = df["TyreLife"] / df["Compound_Dur"]
    df["LapTime_Norm"]        = df["LapTime (s)"] / df["LapTime (s)"].mean()
    df["Position_sq"]         = df["Position"] ** 2
    df["Progress_x_TyreLife"] = df["RaceProgress"] * df["TyreLife"]
    return df

train = add_features(train)
test  = add_features(test)

# ── カテゴリ変数のエンコード ────────────────────────────────
cat_cols = ["Driver", "Compound", "Race"]
encoders = {}
for col in cat_cols:
    le = LabelEncoder()
    combined = pd.concat([train[col], test[col]], axis=0).astype(str)
    le.fit(combined)
    train[col] = le.transform(train[col].astype(str))
    test[col]  = le.transform(test[col].astype(str))
    encoders[col] = le

FEATURES = [c for c in train.columns if c not in [ID_COL, TARGET]]
X        = train[FEATURES].values
y        = train[TARGET].values
X_test   = test[FEATURES].values

print(f"使用特徴量: {len(FEATURES)} 個")

# ── Optuna 設定 ────────────────────────────────────────────
N_TRIALS   = 50   # 試行回数
N_CV_FOLDS = 3    # Optuna 中は 3-Fold で高速化

def objective(trial: optuna.Trial) -> float:
    params = {
        "objective":         "binary",
        "metric":            "auc",
        "is_unbalance":      True,
        "verbose":           -1,
        "seed":              42,
        # ── 探索対象パラメータ ──────────────────────────
        "learning_rate":     trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
        "num_leaves":        trial.suggest_int("num_leaves", 63, 511),
        "min_child_samples": trial.suggest_int("min_child_samples", 10, 100),
        "feature_fraction":  trial.suggest_float("feature_fraction", 0.5, 1.0),
        "bagging_fraction":  trial.suggest_float("bagging_fraction", 0.5, 1.0),
        "bagging_freq":      trial.suggest_int("bagging_freq", 1, 7),
        "lambda_l1":         trial.suggest_float("lambda_l1", 1e-3, 10.0, log=True),
        "lambda_l2":         trial.suggest_float("lambda_l2", 1e-3, 10.0, log=True),
        "min_split_gain":    trial.suggest_float("min_split_gain", 0.0, 1.0),
        "max_depth":         trial.suggest_int("max_depth", 5, 12),
    }

    skf    = StratifiedKFold(n_splits=N_CV_FOLDS, shuffle=True, random_state=42)
    scores = []

    for tr_idx, val_idx in skf.split(X, y):
        X_tr, X_val = X[tr_idx], X[val_idx]
        y_tr, y_val = y[tr_idx], y[val_idx]

        dtrain = lgb.Dataset(X_tr, label=y_tr)
        dval   = lgb.Dataset(X_val, label=y_val, reference=dtrain)

        model = lgb.train(
            params,
            dtrain,
            num_boost_round=3000,
            valid_sets=[dval],
            callbacks=[
                lgb.early_stopping(stopping_rounds=50, verbose=False),
                lgb.log_evaluation(period=-1),
            ],
        )

        scores.append(roc_auc_score(y_val, model.predict(X_val)))

    return float(np.mean(scores))


def progress_callback(study: optuna.Study, trial: optuna.Trial) -> None:
    best_mark = " * best" if trial.value == study.best_value else ""
    print(
        f"  [{trial.number + 1:>3}/{N_TRIALS}]"
        f"  AUC={trial.value:.5f}"
        f"  best={study.best_value:.5f}"
        f"{best_mark}"
    )


# ── Optuna 実行 ────────────────────────────────────────────
print(f"\nOptuna 探索開始（{N_TRIALS} trials x {N_CV_FOLDS}-Fold CV）")
print("-" * 55)

study = optuna.create_study(direction="maximize", sampler=TPESampler(seed=42))
study.optimize(objective, n_trials=N_TRIALS, callbacks=[progress_callback])

print("\n=== Optuna 結果 ===")
print(f"  Best 3-Fold AUC: {study.best_value:.5f}")
print(f"  Best params:")
for k, v in study.best_params.items():
    print(f"    {k}: {v}")

# ── ベストパラメータで 5-Fold 最終評価 ────────────────────
best_params = {
    "objective":    "binary",
    "metric":       "auc",
    "is_unbalance": True,
    "verbose":      -1,
    "seed":         42,
    **study.best_params,
}

print(f"\n最終評価（5-Fold CV）開始...")
print("-" * 55)

skf5       = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
oof_probs  = np.zeros(len(X))
test_probs = np.zeros(len(X_test))
cv_scores  = []

for fold, (tr_idx, val_idx) in enumerate(skf5.split(X, y), 1):
    X_tr, X_val = X[tr_idx], X[val_idx]
    y_tr, y_val = y[tr_idx], y[val_idx]

    dtrain = lgb.Dataset(X_tr, label=y_tr, feature_name=FEATURES)
    dval   = lgb.Dataset(X_val, label=y_val, reference=dtrain)

    model = lgb.train(
        best_params,
        dtrain,
        num_boost_round=3000,
        valid_sets=[dval],
        callbacks=[
            lgb.early_stopping(stopping_rounds=50, verbose=False),
            lgb.log_evaluation(period=200),
        ],
    )

    val_pred = model.predict(X_val)
    fold_auc = roc_auc_score(y_val, val_pred)
    cv_scores.append(fold_auc)
    oof_probs[val_idx] = val_pred
    test_probs += model.predict(X_test) / 5

    print(f"  Fold {fold}  best_iter={model.best_iteration:4d}  AUC={fold_auc:.5f}")

oof_auc = roc_auc_score(y, oof_probs)
print(f"\n=== 最終結果 ===")
print(f"  OOF AUC  : {oof_auc:.5f}  (各Fold平均: {np.mean(cv_scores):.5f} +/- {np.std(cv_scores):.5f})")
print(f"  Baseline : 0.94840")
print(f"  改善幅   : {oof_auc - 0.94840:+.5f}")

# ── 特徴量重要度 ───────────────────────────────────────────
fi = pd.DataFrame({"feature": FEATURES, "importance": model.feature_importance("gain")})
fi = fi.sort_values("importance", ascending=False)
print("\n=== 特徴量重要度 (Top 15) ===")
print(fi.head(15).to_string(index=False))

# ── 提出ファイル作成 ──────────────────────────────────────
submission = pd.DataFrame({"id": test[ID_COL], "PitNextLap": test_probs})
out_path   = OUTPUT_DIR / "submission_optuna.csv"
submission.to_csv(out_path, index=False)
print(f"\nSubmission saved -> {out_path}")
print(f"予測確率の統計: mean={test_probs.mean():.4f}  min={test_probs.min():.4f}  max={test_probs.max():.4f}")
