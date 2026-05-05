"""
https://www.kaggle.com/competitions/rossmann-store-sales/overview
Rossmann Store Sales - Optuna ハイパーパラメータ最適化
v2 ベース（店舗別統計量 + num_boost_round=8000）で Optuna を実行する。

設計:
  - v2 と同一の特徴量・データ前処理を使用
  - Optuna の目的関数: v2 と同じ Hold-out バリデーション（2015-06-20〜2015-07-31）の RMSPE
  - 各 trial で早期停止（early stopping）を使い最適な num_boost_round を自動決定
  - 最適パラメータで全データを再学習 → 提出ファイル作成

実行時間の目安:
  - 1 trial ≈ 1〜3 分（パラメータにより変動）
  - 50 trial ≈ 50〜150 分
  - 途中経過はリアルタイムに出力される
"""
import pandas as pd
import numpy as np
from pathlib import Path
import lightgbm as lgb
import optuna

optuna.logging.set_verbosity(optuna.logging.WARNING)  # Optuna 内部ログを抑制

DATA_DIR   = Path(__file__).parent.parent / "competitions" / "rossmann-store-sales"
OUTPUT_DIR = Path(__file__).parent
OUTPUT_DIR.mkdir(exist_ok=True)

N_TRIALS = 50  # 試行回数（増やすほど精度向上の可能性があるが時間もかかる）

# ── 評価指標 ────────────────────────────────────────────────────
def rmspe(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    mask = y_true != 0
    return np.sqrt(np.mean(((y_true[mask] - y_pred[mask]) / y_true[mask]) ** 2))

def rmspe_lgbm(preds: np.ndarray, train_data: lgb.Dataset):
    y_true = np.expm1(train_data.get_label())
    y_pred = np.expm1(preds)
    return "RMSPE", rmspe(y_true, y_pred), False

# ── データ読み込み ───────────────────────────────────────────────
print("=" * 60)
print("データ読み込み & 前処理")
print("=" * 60)

train = pd.read_csv(DATA_DIR / "train.csv", low_memory=False, parse_dates=["Date"])
test  = pd.read_csv(DATA_DIR / "test.csv",  low_memory=False, parse_dates=["Date"])
store = pd.read_csv(DATA_DIR / "store.csv")

train = train.merge(store, on="Store", how="left")
test  = test.merge(store,  on="Store", how="left")

test["Open"] = test["Open"].fillna(1).astype(int)
train["StateHoliday"] = train["StateHoliday"].astype(str).replace({"0": "none"})
test["StateHoliday"]  = test["StateHoliday"].astype(str).replace({"0": "none"})

# ── 特徴量エンジニアリング（v2 と同一） ─────────────────────────
MONTH_MAP = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May",  6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Year"]         = df["Date"].dt.year
    df["Month"]        = df["Date"].dt.month
    df["Day"]          = df["Date"].dt.day
    df["WeekOfYear"]   = df["Date"].dt.isocalendar().week.astype(int)
    df["IsWeekend"]    = (df["DayOfWeek"] >= 6).astype(int)
    df["IsMonthStart"] = (df["Day"] <= 5).astype(int)
    df["IsMonthEnd"]   = (df["Day"] >= 25).astype(int)
    comp_since_year    = df["CompetitionOpenSinceYear"].fillna(1900)
    comp_since_month   = df["CompetitionOpenSinceMonth"].fillna(1)
    df["CompetitionOpen"] = (
        12 * (df["Year"] - comp_since_year) + (df["Month"] - comp_since_month)
    ).clip(lower=0)
    df["CompetitionDistance"]    = df["CompetitionDistance"].fillna(200_000)
    df["LogCompetitionDistance"] = np.log1p(df["CompetitionDistance"])
    df["MonthStr"]     = df["Month"].map(MONTH_MAP)
    df["Promo2Active"] = 0
    promo2_mask = df["Promo2"] == 1
    df.loc[promo2_mask, "Promo2Active"] = [
        1 if isinstance(interval, str) and month_str in interval else 0
        for interval, month_str in zip(
            df.loc[promo2_mask, "PromoInterval"],
            df.loc[promo2_mask, "MonthStr"],
        )
    ]
    p2_year = df["Promo2SinceYear"].fillna(df["Year"])
    p2_week = df["Promo2SinceWeek"].fillna(0)
    df["Promo2OpenWeeks"] = (
        52 * (df["Year"] - p2_year) + (df["WeekOfYear"] - p2_week)
    ).clip(lower=0)
    return df

def add_store_stats(target: pd.DataFrame, ref: pd.DataFrame) -> pd.DataFrame:
    target = target.copy()
    store_agg = ref.groupby("Store")["Sales"].agg(
        store_mean="mean", store_median="median", store_std="std"
    ).reset_index()
    target = target.merge(store_agg, on="Store", how="left")
    dow_mean = (
        ref.groupby(["Store", "DayOfWeek"])["Sales"].mean()
        .reset_index().rename(columns={"Sales": "store_dow_mean"})
    )
    target = target.merge(dow_mean, on=["Store", "DayOfWeek"], how="left")
    month_mean = (
        ref.groupby(["Store", "Month"])["Sales"].mean()
        .reset_index().rename(columns={"Sales": "store_month_mean"})
    )
    target = target.merge(month_mean, on=["Store", "Month"], how="left")
    promo_mean = (
        ref.groupby(["Store", "Promo"])["Sales"].mean()
        .reset_index().rename(columns={"Sales": "store_promo_mean"})
    )
    target = target.merge(promo_mean, on=["Store", "Promo"], how="left")
    for col in ["store_dow_mean", "store_month_mean", "store_promo_mean"]:
        null_mask = target[col].isnull()
        if null_mask.any():
            target.loc[null_mask, col] = target.loc[null_mask, "store_mean"]
    return target

print("特徴量エンジニアリング中...")
train = build_features(train)
test  = build_features(test)

train_open = train[train["Open"] == 1].copy()
train_open = train_open[train_open["Sales"] > 0].copy()
train_open["LogSales"] = np.log1p(train_open["Sales"])

VAL_START = pd.Timestamp("2015-06-20")
tr_fold   = train_open[train_open["Date"] <  VAL_START].copy()
val_fold  = train_open[train_open["Date"] >= VAL_START].copy()

print("店舗別統計量を計算中...")
tr_fold    = add_store_stats(tr_fold,  ref=tr_fold)
val_fold   = add_store_stats(val_fold, ref=tr_fold)
train_open = add_store_stats(train_open, ref=train_open)
test       = add_store_stats(test, ref=train_open)

FEATURES = [
    "Store", "StoreType", "Assortment",
    "DayOfWeek", "Year", "Month", "Day", "WeekOfYear",
    "IsWeekend", "IsMonthStart", "IsMonthEnd",
    "Promo", "Promo2", "Promo2Active", "Promo2OpenWeeks",
    "StateHoliday", "SchoolHoliday",
    "LogCompetitionDistance", "CompetitionOpen",
    "store_mean", "store_median", "store_std",
    "store_dow_mean", "store_month_mean", "store_promo_mean",
]
CAT_COLS = ["StoreType", "Assortment", "StateHoliday"]
TARGET   = "LogSales"

for col in CAT_COLS:
    for df in [tr_fold, val_fold, train_open, test]:
        df[col] = df[col].astype("category")

print(f"  使用特徴量: {len(FEATURES)} 個")
print(f"  学習: {tr_fold['Date'].min().date()} ~ {tr_fold['Date'].max().date()}  ({len(tr_fold):,} 行)")
print(f"  検証: {val_fold['Date'].min().date()} ~ {val_fold['Date'].max().date()}  ({len(val_fold):,} 行)")

# ── Optuna 用データセット（trial ごとに使い回す） ─────────────────
X_tr  = tr_fold[FEATURES]
y_tr  = tr_fold[TARGET]
X_val = val_fold[FEATURES]
y_val = val_fold[TARGET]

dtrain_optuna = lgb.Dataset(X_tr, label=y_tr, categorical_feature=CAT_COLS)
dval_optuna   = lgb.Dataset(X_val, label=y_val, categorical_feature=CAT_COLS,
                             reference=dtrain_optuna)

# ── Optuna 目的関数 ──────────────────────────────────────────────
def objective(trial: optuna.Trial) -> float:
    params = {
        "objective":         "regression",
        "metric":            "rmse",
        "verbose":           -1,
        "seed":              42,
        # trial ごとに min_child_samples が変わるため、Dataset のキャッシュ済み
        # feature_pre_filter との競合を防ぐ（これがないと trial 間で LightGBMError が発生する）
        "feature_pre_filter": False,
        # ── Optuna が探索するパラメータ ──────────────────────────
        "learning_rate":     trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
        "num_leaves":        trial.suggest_int("num_leaves", 63, 511),
        "min_child_samples": trial.suggest_int("min_child_samples", 10, 200),
        "feature_fraction":  trial.suggest_float("feature_fraction", 0.5, 1.0),
        "bagging_fraction":  trial.suggest_float("bagging_fraction", 0.5, 1.0),
        "bagging_freq":      trial.suggest_int("bagging_freq", 1, 10),
        "lambda_l1":         trial.suggest_float("lambda_l1", 1e-3, 10.0, log=True),
        "lambda_l2":         trial.suggest_float("lambda_l2", 1e-3, 10.0, log=True),
        "min_split_gain":    trial.suggest_float("min_split_gain", 0.0, 1.0),
        "max_depth":         trial.suggest_int("max_depth", 4, 12),
    }

    model = lgb.train(
        params,
        dtrain_optuna,
        num_boost_round=5000,
        valid_sets=[dval_optuna],
        feval=rmspe_lgbm,
        callbacks=[
            lgb.early_stopping(stopping_rounds=100, verbose=False),
            lgb.log_evaluation(period=-1),  # 各 trial の学習ログは非表示
        ],
    )

    # best_iteration を trial の属性として保存（後で使う）
    trial.set_user_attr("best_iteration", model.best_iteration)

    val_pred = np.expm1(model.predict(X_val))
    val_true = np.expm1(y_val.values)
    return rmspe(val_true, val_pred)

# ── Optuna 最適化実行 ────────────────────────────────────────────
print(f"\n{'=' * 60}")
print(f"Optuna ハイパーパラメータ探索（{N_TRIALS} trials）")
print(f"{'=' * 60}")
print(f"{'Trial':>6}  {'RMSPE':>8}  {'Best':>8}  パラメータ")
print("-" * 60)

# v2 ベースライン（比較用）
V2_RMSPE = 0.13310
best_so_far = float("inf")

def print_trial_result(study: optuna.Study, trial: optuna.Trial):
    global best_so_far
    is_best = trial.value < best_so_far
    if is_best:
        best_so_far = trial.value
    marker = "★" if is_best else " "
    lr   = trial.params.get("learning_rate", 0)
    nl   = trial.params.get("num_leaves", 0)
    md   = trial.params.get("max_depth", 0)
    best_iter = trial.user_attrs.get("best_iteration", 0)
    print(
        f"{marker}{trial.number:5d}  {trial.value:8.5f}  {study.best_value:8.5f}  "
        f"lr={lr:.4f} leaves={nl:3d} depth={md:2d} iter={best_iter:4d}"
    )

study = optuna.create_study(
    direction="minimize",
    sampler=optuna.samplers.TPESampler(seed=42),
)
study.optimize(objective, n_trials=N_TRIALS, callbacks=[print_trial_result])

# ── 最適パラメータのログ ─────────────────────────────────────────
best_params = study.best_trial.params
best_iter   = study.best_trial.user_attrs["best_iteration"]
best_rmspe  = study.best_value

print(f"\n{'=' * 60}")
print("Optuna 最適化結果")
print(f"{'=' * 60}")
print(f"  最良 RMSPE (valid): {best_rmspe:.5f}")
print(f"  v2 ベースライン   : {V2_RMSPE:.5f}")
print(f"  改善幅            : {best_rmspe - V2_RMSPE:+.5f}")
print(f"  最適 num_boost_round: {best_iter}")
print(f"\n  最適パラメータ:")
for k, v in best_params.items():
    print(f"    {k:25s}: {v}")

# 上位5試行の比較
print(f"\n  上位 5 試行:")
trials_sorted = sorted(study.trials, key=lambda t: t.value)
for t in trials_sorted[:5]:
    print(f"    Trial {t.number:3d}: RMSPE={t.value:.5f}  iter={t.user_attrs.get('best_iteration',0):4d}  "
          f"lr={t.params['learning_rate']:.4f}  leaves={t.params['num_leaves']:3d}")

# ── 最適パラメータで再バリデーション ────────────────────────────
print(f"\n{'=' * 60}")
print("最適パラメータで再バリデーション（詳細確認）")
print(f"{'=' * 60}")

BEST_PARAMS = {
    "objective":         "regression",
    "metric":            "rmse",
    "verbose":           -1,
    "seed":              42,
    **best_params,
}

dtrain_cv = lgb.Dataset(X_tr,  label=y_tr,  categorical_feature=CAT_COLS)
dval_cv   = lgb.Dataset(X_val, label=y_val, categorical_feature=CAT_COLS, reference=dtrain_cv)

print("学習中...")
model_cv = lgb.train(
    BEST_PARAMS,
    dtrain_cv,
    num_boost_round=5000,
    valid_sets=[dtrain_cv, dval_cv],
    valid_names=["train", "valid"],
    feval=rmspe_lgbm,
    callbacks=[
        lgb.early_stopping(stopping_rounds=100, verbose=False),
        lgb.log_evaluation(period=500),
    ],
)

val_pred  = np.expm1(model_cv.predict(X_val))
val_true  = np.expm1(y_val.values)
val_rmspe = rmspe(val_true, val_pred)

tr_pred  = np.expm1(model_cv.predict(X_tr))
tr_true  = np.expm1(y_tr.values)
tr_rmspe = rmspe(tr_true, tr_pred)

print(f"\n=== 再バリデーション結果 ===")
print(f"  best_iteration      : {model_cv.best_iteration}")
print(f"  RMSPE (train)       : {tr_rmspe:.5f}  (v2: 0.10520)")
print(f"  RMSPE (valid)       : {val_rmspe:.5f}  (v2: 0.13310)")
print(f"  差分 (過学習度)     : {val_rmspe - tr_rmspe:+.5f}")
print(f"  改善幅 (vs v2)      : {val_rmspe - V2_RMSPE:+.5f}")

# ── 特徴量重要度 ─────────────────────────────────────────────────
print(f"\n=== 特徴量重要度（gain）===")
imp = pd.Series(
    model_cv.feature_importance(importance_type="gain"),
    index=FEATURES,
).sort_values(ascending=False)
max_val = imp.max()
for feat, val in imp.items():
    bar = "█" * max(1, int(val / max_val * 30))
    print(f"  {feat:35s}: {val:12.0f}  {bar}")

# ── 全データで再学習 ─────────────────────────────────────────────
print(f"\n全データで再学習中（num_boost_round={model_cv.best_iteration}）...")
dtrain_full = lgb.Dataset(
    train_open[FEATURES], label=train_open[TARGET],
    categorical_feature=CAT_COLS,
)
model_full = lgb.train(
    BEST_PARAMS,
    dtrain_full,
    num_boost_round=model_cv.best_iteration,
)

# ── テスト予測 ───────────────────────────────────────────────────
test_pred = np.expm1(model_full.predict(test[FEATURES]))
test_pred = np.clip(test_pred, 0, None)
test_pred[test["Open"] == 0] = 0

# ── 提出ファイル ─────────────────────────────────────────────────
submission = pd.DataFrame({"Id": test["Id"], "Sales": test_pred})
out_path   = OUTPUT_DIR / "submission_optuna.csv"
submission.to_csv(out_path, index=False)

print(f"\n=== 提出ファイル ===")
print(f"  保存先: {out_path}")
print(f"  行数  : {len(submission):,}")

print(f"\n=== 予測値の統計（Open=1 のみ） ===")
pred_open = test_pred[test["Open"] == 1]
print(f"  mean   : {pred_open.mean():,.1f}")
print(f"  median : {np.median(pred_open):,.1f}")
print(f"  std    : {pred_open.std():,.1f}")
print(f"  min    : {pred_open.min():,.1f}")
print(f"  max    : {pred_open.max():,.1f}")

print(f"\n=== スコアまとめ ===")
print(f"  v1 baseline RMSPE (valid): 0.13670  Kaggle LB: 0.12846")
print(f"  v2 店舗統計量   RMSPE (valid): 0.13310  Kaggle LB: 0.12274")
print(f"  v3 ラグ特徴量   RMSPE (valid): 0.13155  Kaggle LB: 0.12514  ← 悪化")
print(f"  v4 Optuna最適化 RMSPE (valid): {val_rmspe:.5f}  改善幅 (vs v2): {val_rmspe - V2_RMSPE:+.5f}")
print(f"  ※ Kaggle LB はこの後提出して確認")

# ── 最適パラメータの保存（次回以降の参照用） ─────────────────────
params_out = OUTPUT_DIR / "best_params_optuna.txt"
with open(params_out, "w", encoding="utf-8") as f:
    f.write(f"# Optuna 最適パラメータ（{N_TRIALS} trials）\n")
    f.write(f"# valid RMSPE: {val_rmspe:.5f}  best_iteration: {model_cv.best_iteration}\n\n")
    f.write("BEST_PARAMS = {\n")
    f.write(f'    "objective":         "regression",\n')
    f.write(f'    "metric":            "rmse",\n')
    f.write(f'    "verbose":           -1,\n')
    f.write(f'    "seed":              42,\n')
    for k, v in best_params.items():
        if isinstance(v, float):
            f.write(f'    "{k}": {v},\n')
        else:
            f.write(f'    "{k}": {v},\n')
    f.write("}\n")
print(f"\n最適パラメータを保存: {params_out}")
