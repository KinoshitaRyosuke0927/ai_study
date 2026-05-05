import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import balanced_accuracy_score
import lightgbm as lgb
import optuna
from optuna.samplers import TPESampler

from features import add_features

optuna.logging.set_verbosity(optuna.logging.WARNING)

# ── パス設定 ──────────────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent / "competitions" / "playground-series-s6e4"
OUTPUT_DIR = Path(__file__).parent
OUTPUT_DIR.mkdir(exist_ok=True)

# ── データ読み込み・前処理 ─────────────────────────────────
train = pd.read_csv(DATA_DIR / "train.csv")
test  = pd.read_csv(DATA_DIR / "test.csv")

TARGET = "Irrigation_Need"
ID_COL = "id"

train = add_features(train)
test  = add_features(test)

cat_cols = train.select_dtypes(include="object").columns.tolist()
cat_cols = [c for c in cat_cols if c != TARGET]

encoders = {}
for col in cat_cols:
    le = LabelEncoder()
    train[col] = le.fit_transform(train[col].astype(str))
    test[col]  = le.transform(test[col].astype(str))
    encoders[col] = le

le_target = LabelEncoder()
train[TARGET] = le_target.fit_transform(train[TARGET])
print("Target classes:", le_target.classes_)

FEATURES = [c for c in train.columns if c not in [ID_COL, TARGET]]
X = train[FEATURES].values
y = train[TARGET].values
X_test = test[FEATURES].values

# ── Optuna 設定 ────────────────────────────────────────────
N_TRIALS   = 50   # 試行回数（増やすほど精度が上がるが時間がかかる）
N_CV_FOLDS = 3    # Optuna 中は 3-Fold で高速化（最終評価は 5-Fold）

def objective(trial: optuna.Trial) -> float:
    params = {
        "objective": "multiclass",
        "num_class": 3,
        "metric": "multi_logloss",
        "is_unbalance": True,
        "verbose": -1,
        "seed": 42,
        # ── 探索対象パラメータ ──
        "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.1, log=True),
        "num_leaves": trial.suggest_int("num_leaves", 31, 511),
        "min_child_samples": trial.suggest_int("min_child_samples", 5, 100),
        "feature_fraction": trial.suggest_float("feature_fraction", 0.5, 1.0),
        "bagging_fraction": trial.suggest_float("bagging_fraction", 0.5, 1.0),
        "bagging_freq": trial.suggest_int("bagging_freq", 1, 7),
        "lambda_l1": trial.suggest_float("lambda_l1", 1e-3, 10.0, log=True),
        "lambda_l2": trial.suggest_float("lambda_l2", 1e-3, 10.0, log=True),
        "min_split_gain": trial.suggest_float("min_split_gain", 0.0, 1.0),
    }

    skf = StratifiedKFold(n_splits=N_CV_FOLDS, shuffle=True, random_state=42)
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

        val_pred = np.argmax(model.predict(X_val), axis=1)
        scores.append(balanced_accuracy_score(y_val, val_pred))

    return np.mean(scores)


def progress_callback(study: optuna.Study, trial: optuna.Trial) -> None:
    """各試行終了後に進捗を表示する。学習処理には影響しない。"""
    best_mark = " ★ best" if trial.value == study.best_value else ""
    print(
        f"  [{trial.number + 1:>3}/{N_TRIALS}]"
        f"  score={trial.value:.5f}"
        f"  best={study.best_value:.5f}"
        f"{best_mark}"
    )


# ── Optuna 実行 ────────────────────────────────────────────
print(f"\nOptuna 探索開始（{N_TRIALS} trials × {N_CV_FOLDS}-Fold CV）")
print("─" * 50)

study = optuna.create_study(
    direction="maximize",
    sampler=TPESampler(seed=42),
)
study.optimize(
    objective,
    n_trials=N_TRIALS,
    callbacks=[progress_callback],
)

print("\n=== Optuna 結果 ===")
print(f"  Best CV score : {study.best_value:.5f}")
print(f"  Best params   :")
for k, v in study.best_params.items():
    print(f"    {k}: {v}")

# ── ベストパラメータで 5-Fold 最終評価 ────────────────────
best_params = {
    "objective": "multiclass",
    "num_class": 3,
    "metric": "multi_logloss",
    "is_unbalance": True,
    "verbose": -1,
    "seed": 42,
    **study.best_params,
}

print(f"\n最終評価（5-Fold CV）開始...")
skf5 = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

oof_probs  = np.zeros((len(X), 3))
test_probs = np.zeros((len(X_test), 3))
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

    val_prob = model.predict(X_val)
    oof_probs[val_idx] = val_prob

    val_pred = np.argmax(val_prob, axis=1)
    score = balanced_accuracy_score(y_val, val_pred)
    cv_scores.append(score)
    print(f"  Fold {fold}: {score:.4f}  (best iter={model.best_iteration})")

    test_probs += model.predict(X_test) / 5

# ── 結果サマリ ─────────────────────────────────────────────
oof_pred  = np.argmax(oof_probs, axis=1)
oof_score = balanced_accuracy_score(y, oof_pred)

print(f"\n=== 最終 5-Fold CV Balanced Accuracy ===")
for i, s in enumerate(cv_scores, 1):
    print(f"  Fold {i}: {s:.4f}")
print(f"  Mean : {np.mean(cv_scores):.4f}  ±{np.std(cv_scores):.4f}")
print(f"  OOF  : {oof_score:.4f}")

print(f"\n  lgbm+fe (前回) : 0.96163")
print(f"  lgbm+optuna    : {oof_score:.5f}  ({'+' if oof_score > 0.96163 else ''}{oof_score - 0.96163:+.5f})")

# ── 特徴量重要度 ──────────────────────────────────────────
importances = pd.Series(
    model.feature_importance(importance_type="gain"), index=FEATURES
)
print("\n=== Feature Importances / gain (Top 15) ===")
print(importances.nlargest(15).to_string())

# ── 提出ファイル生成 ───────────────────────────────────────
test_pred   = np.argmax(test_probs, axis=1)
pred_labels = le_target.inverse_transform(test_pred)

submission = pd.DataFrame({ID_COL: test[ID_COL], TARGET: pred_labels})
out_path = OUTPUT_DIR / "submission_optuna.csv"
submission.to_csv(out_path, index=False)
print(f"\nSubmission saved → {out_path}")
print(submission[TARGET].value_counts())
