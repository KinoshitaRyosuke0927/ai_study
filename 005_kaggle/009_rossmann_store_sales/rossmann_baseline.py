"""
https://www.kaggle.com/competitions/rossmann-store-sales/overview
Rossmann Store Sales - Baseline Model
LightGBM + 時系列 Hold-out CV（最後の6週間を検証）

ポイント:
  - 評価指標は RMSPE → log1p(Sales) を目的変数にして学習し、予測後に expm1 で戻す
  - Open=0（閉店日）は Sales=0 が確定 → 学習から除外し、予測は 0 を割り当て
  - 時系列データなのでランダム分割は不可 → 直近 6 週を Hold-out バリデーションに使う
"""
import pandas as pd
import numpy as np
from pathlib import Path
import lightgbm as lgb

DATA_DIR   = Path(__file__).parent.parent / "competitions" / "rossmann-store-sales"
OUTPUT_DIR = Path(__file__).parent
OUTPUT_DIR.mkdir(exist_ok=True)

# ── 評価指標 ────────────────────────────────────────────────────
def rmspe(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Root Mean Square Percentage Error（Sales=0 の行は除外）"""
    mask = y_true != 0
    return np.sqrt(np.mean(((y_true[mask] - y_pred[mask]) / y_true[mask]) ** 2))

def rmspe_lgbm(preds: np.ndarray, train_data: lgb.Dataset):
    """LightGBM custom eval: log空間の予測 → 元スケールに戻して RMSPE を計算"""
    y_true = np.expm1(train_data.get_label())
    y_pred = np.expm1(preds)
    score  = rmspe(y_true, y_pred)
    return "RMSPE", score, False  # (name, value, is_higher_better)

# ── データ読み込み ───────────────────────────────────────────────
print("=" * 60)
print("データ読み込み & 前処理")
print("=" * 60)

train = pd.read_csv(DATA_DIR / "train.csv", low_memory=False, parse_dates=["Date"])
test  = pd.read_csv(DATA_DIR / "test.csv",  low_memory=False, parse_dates=["Date"])
store = pd.read_csv(DATA_DIR / "store.csv")

train = train.merge(store, on="Store", how="left")
test  = test.merge(store,  on="Store", how="left")

print(f"train: {train.shape}  test: {test.shape}")

# ── 前処理 ──────────────────────────────────────────────────────
# test の Open 欠損（11件）→ 1 で補完（EDAで該当店舗は store 622 と判明）
test["Open"] = test["Open"].fillna(1).astype(int)

# StateHoliday: 文字列 "0" と整数 0 が混在しているため統一
train["StateHoliday"] = train["StateHoliday"].astype(str).replace({"0": "none"})
test["StateHoliday"]  = test["StateHoliday"].astype(str).replace({"0": "none"})

# ── 特徴量エンジニアリング ───────────────────────────────────────
MONTH_MAP = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May",  6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # 日付系
    df["Year"]         = df["Date"].dt.year
    df["Month"]        = df["Date"].dt.month
    df["Day"]          = df["Date"].dt.day
    df["WeekOfYear"]   = df["Date"].dt.isocalendar().week.astype(int)
    df["IsWeekend"]    = (df["DayOfWeek"] >= 6).astype(int)
    df["IsMonthStart"] = (df["Day"] <= 5).astype(int)
    df["IsMonthEnd"]   = (df["Day"] >= 25).astype(int)

    # 競合店：オープンからの経過月数（欠損は「遠い過去」= 競合なし扱いで 0）
    comp_since_year  = df["CompetitionOpenSinceYear"].fillna(1900)
    comp_since_month = df["CompetitionOpenSinceMonth"].fillna(1)
    df["CompetitionOpen"] = (
        12 * (df["Year"] - comp_since_year) + (df["Month"] - comp_since_month)
    ).clip(lower=0)

    # 競合距離: 欠損は「競合なし」= 非常に遠い距離として補完後 log 変換
    df["CompetitionDistance"]    = df["CompetitionDistance"].fillna(200_000)
    df["LogCompetitionDistance"] = np.log1p(df["CompetitionDistance"])

    # Promo2 が現在の月に実施中かどうか
    # PromoInterval 例: "Jan,Apr,Jul,Oct" → 該当月が含まれていれば Promo2 実施中
    df["MonthStr"]    = df["Month"].map(MONTH_MAP)
    df["Promo2Active"] = 0
    promo2_mask = df["Promo2"] == 1
    df.loc[promo2_mask, "Promo2Active"] = [
        1 if isinstance(interval, str) and month_str in interval else 0
        for interval, month_str in zip(
            df.loc[promo2_mask, "PromoInterval"],
            df.loc[promo2_mask, "MonthStr"],
        )
    ]

    # Promo2 開始からの経過週数（参加していない店は 0）
    p2_year = df["Promo2SinceYear"].fillna(df["Year"])
    p2_week = df["Promo2SinceWeek"].fillna(0)
    df["Promo2OpenWeeks"] = (
        52 * (df["Year"] - p2_year) + (df["WeekOfYear"] - p2_week)
    ).clip(lower=0)

    return df

print("特徴量エンジニアリング中...")
train = build_features(train)
test  = build_features(test)

# ── 学習データの準備 ─────────────────────────────────────────────
# 閉店日（Open=0）は Sales が必ず 0 → RMSPE の分母が 0 になるため学習から除外
train_open = train[train["Open"] == 1].copy()
train_open["LogSales"] = np.log1p(train_open["Sales"])

# Open=1 なのに Sales=0 の異常値（EDAで54件確認）→ 除外
train_open = train_open[train_open["Sales"] > 0]

print(f"学習データ（Open=1 & Sales>0）: {len(train_open):,} 行")

FEATURES = [
    # 店舗属性
    "Store", "StoreType", "Assortment",
    # 日付
    "DayOfWeek", "Year", "Month", "Day", "WeekOfYear",
    "IsWeekend", "IsMonthStart", "IsMonthEnd",
    # プロモーション
    "Promo", "Promo2", "Promo2Active", "Promo2OpenWeeks",
    # 祝日・休暇
    "StateHoliday", "SchoolHoliday",
    # 競合
    "LogCompetitionDistance", "CompetitionOpen",
]

CAT_COLS = ["StoreType", "Assortment", "StateHoliday"]
TARGET   = "LogSales"

for col in CAT_COLS:
    train_open[col] = train_open[col].astype("category")
    test[col]       = test[col].astype("category")

print(f"使用特徴量: {len(FEATURES)} 個  カテゴリ変数: {CAT_COLS}")

# ── 時系列 Hold-out CV ───────────────────────────────────────────
# test 期間（2015-08-01〜09-17）に合わせ、直近 6 週を検証に切り出す
VAL_START = pd.Timestamp("2015-06-20")

tr_fold  = train_open[train_open["Date"] <  VAL_START]
val_fold = train_open[train_open["Date"] >= VAL_START]

print(f"\n=== 時系列 Hold-out CV ===")
print(f"  学習: {tr_fold['Date'].min().date()} ~ {tr_fold['Date'].max().date()}  ({len(tr_fold):,} 行)")
print(f"  検証: {val_fold['Date'].min().date()} ~ {val_fold['Date'].max().date()}  ({len(val_fold):,} 行)")

X_tr  = tr_fold[FEATURES]
y_tr  = tr_fold[TARGET]
X_val = val_fold[FEATURES]
y_val = val_fold[TARGET]

# ── LightGBM 学習 ────────────────────────────────────────────────
LGBM_PARAMS = {
    "objective":         "regression",
    "metric":            "rmse",       # 学習ログは log 空間の RMSE（RMSPE は feval で追加）
    "verbose":           -1,
    "seed":              42,
    "learning_rate":     0.05,
    "num_leaves":        127,
    "min_child_samples": 20,
    "feature_fraction":  0.8,
    "bagging_fraction":  0.8,
    "bagging_freq":      5,
    "lambda_l1":         0.1,
    "lambda_l2":         0.1,
}

dtrain = lgb.Dataset(X_tr,  label=y_tr,  categorical_feature=CAT_COLS)
dval   = lgb.Dataset(X_val, label=y_val, categorical_feature=CAT_COLS, reference=dtrain)

print("\nLightGBM 学習中...")
model = lgb.train(
    LGBM_PARAMS,
    dtrain,
    num_boost_round=3000,
    valid_sets=[dtrain, dval],
    valid_names=["train", "valid"],
    feval=rmspe_lgbm,
    callbacks=[
        lgb.early_stopping(stopping_rounds=100, verbose=False),
        lgb.log_evaluation(period=200),
    ],
)

# ── バリデーションスコア ─────────────────────────────────────────
val_pred  = np.expm1(model.predict(X_val))
val_true  = np.expm1(y_val.values)
val_rmspe = rmspe(val_true, val_pred)

train_pred_check = np.expm1(model.predict(X_tr))
train_true_check = np.expm1(y_tr.values)
tr_rmspe = rmspe(train_true_check, train_pred_check)

print(f"\n=== バリデーション結果 ===")
print(f"  best_iteration : {model.best_iteration}")
print(f"  RMSPE (train)  : {tr_rmspe:.5f}")
print(f"  RMSPE (valid)  : {val_rmspe:.5f}")
print(f"  差分 (過学習度): {val_rmspe - tr_rmspe:+.5f}  (大きい場合は正則化強化を検討)")

# ── 特徴量重要度 ─────────────────────────────────────────────────
print(f"\n=== 特徴量重要度 TOP {len(FEATURES)}（gain） ===")
imp = pd.Series(
    model.feature_importance(importance_type="gain"),
    index=FEATURES,
).sort_values(ascending=False)
max_val = imp.max()
for feat, val in imp.items():
    bar = "█" * max(1, int(val / max_val * 30))
    print(f"  {feat:35s}: {val:12.0f}  {bar}")

print(f"\n=== 特徴量重要度 TOP {len(FEATURES)}（split） ===")
imp_split = pd.Series(
    model.feature_importance(importance_type="split"),
    index=FEATURES,
).sort_values(ascending=False)
max_val_s = imp_split.max()
for feat, val in imp_split.items():
    bar = "█" * max(1, int(val / max_val_s * 30))
    print(f"  {feat:35s}: {val:8.0f}  {bar}")

# ── 全データで再学習 ─────────────────────────────────────────────
print(f"\n全データで再学習中（num_boost_round={model.best_iteration}）...")
dtrain_full = lgb.Dataset(
    train_open[FEATURES], label=train_open[TARGET],
    categorical_feature=CAT_COLS,
)
model_full = lgb.train(
    LGBM_PARAMS,
    dtrain_full,
    num_boost_round=model.best_iteration,
)

# ── テスト予測 ───────────────────────────────────────────────────
test_pred = np.expm1(model_full.predict(test[FEATURES]))
test_pred = np.clip(test_pred, 0, None)  # 負の予測を 0 にクリップ

# Open=0 の店舗は Sales=0 が確定
test_pred[test["Open"] == 0] = 0

# ── 提出ファイル ─────────────────────────────────────────────────
submission = pd.DataFrame({"Id": test["Id"], "Sales": test_pred})
out_path   = OUTPUT_DIR / "submission_baseline.csv"
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

print(f"\n=== スコアの目安 ===")
print(f"  今回のベースライン RMSPE (valid): {val_rmspe:.5f}")
print(f"  コンペ上位（top 10%）の目安     : ~0.105 前後")
print(f"  コンペ優勝スコア                : ~0.100 前後")
print(f"  ※ Kaggle LB スコアはこの val RMSPE より高く（悪く）なることが多い")
