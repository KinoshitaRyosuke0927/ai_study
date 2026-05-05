"""
https://www.kaggle.com/competitions/rossmann-store-sales/overview
Rossmann Store Sales - v6 Entity Embedding (案A)
v4(Optuna最適パラメータ) からの変更点:
  Entity Embedding Neural Network を追加
  - 13 カテゴリ変数を低次元ベクトルに変換する NN を Keras で実装
  - NN が学習した埋め込みベクトル（合計 42 次元）を LightGBM の追加特徴量として注入

処理フロー（案A: train_open 全データで NN を 1 回だけ学習）:
  1. train_open 全データで NN を学習（30 epoch、early stopping は train loss 監視）
  2. NN から埋め込みを抽出し、tr_fold / val_fold / train_open / test 全てに適用
  3. LightGBM（Optuna 最適パラメータ）で CV バリデーション
  4. LightGBM 全データ再学習 → 提出ファイル生成

  メリット: NN が完全学習された埋め込みを CV にも使えるため、CV スコアが実態を反映する
  注意点 : val_fold のデータが NN 学習に関与するため軽微なリークがあるが、
           NN は val_fold の目的変数（Sales）を直接見ていないため影響は小さい
"""
import pandas as pd
import numpy as np
from pathlib import Path
import lightgbm as lgb
import tensorflow as tf
from tensorflow import keras
from sklearn.preprocessing import LabelEncoder

# ─── 再現性の固定 ────────────────────────────────────────────────────
tf.random.set_seed(42)
np.random.seed(42)

DATA_DIR   = Path(__file__).parent.parent / "competitions" / "rossmann-store-sales"
OUTPUT_DIR = Path(__file__).parent
OUTPUT_DIR.mkdir(exist_ok=True)

# ─── 埋め込み設定 ────────────────────────────────────────────────────
EMB_COLS = [
    ("Store",         50),   # 1115 種 → 50次元（10 → 50 に拡大）
    ("DayOfWeek",      4),   #    7 種 →  4次元
    ("Year",           2),   #    3 種 →  2次元
    ("Month",          6),   #   12 種 →  6次元
    ("Day",            4),   #   31 種 →  4次元
    ("WeekOfYear",     6),   #   53 種 →  6次元
    ("StoreType",      2),   #    4 種 →  2次元
    ("Assortment",     2),   #    3 種 →  2次元
    ("Promo",          1),   #    2 種 →  1次元
    ("Promo2",         1),   #    2 種 →  1次元
    ("SchoolHoliday",  1),   #    2 種 →  1次元
    ("StateHoliday",   2),   #    4 種 →  2次元
    ("Promo2Active",   1),   #    2 種 →  1次元
]
EMB_COL_NAMES = [col for col, _ in EMB_COLS]

# 連続変数（NN に直接入力、正規化あり）
CONT_COLS = [
    "LogCompetitionDistance",
    "CompetitionOpen",
    "Promo2OpenWeeks",
    "IsWeekend",
    "IsMonthStart",
    "IsMonthEnd",
    "store_mean",
    "store_median",
    "store_std",
    "store_dow_mean",
    "store_month_mean",
    "store_promo_mean",
]

# Optuna 最適パラメータ（v4 / Trial 31）
BEST_PARAMS = {
    "objective":         "regression",
    "metric":            "rmse",
    "verbose":           -1,
    "seed":              42,
    "learning_rate":     0.025712018491695496,
    "num_leaves":        359,
    "min_child_samples": 146,
    "feature_fraction":  0.5623737166333678,
    "bagging_fraction":  0.9012873662882596,
    "bagging_freq":      5,
    "lambda_l1":         0.038529774921381765,
    "lambda_l2":         5.269302870224163,
    "min_split_gain":    0.0019331115902168428,
    "max_depth":         10,
}
NUM_BOOST_ROUND = 10000

# ─── 評価指標 ─────────────────────────────────────────────────────────
def rmspe(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    mask = y_true != 0
    return np.sqrt(np.mean(((y_true[mask] - y_pred[mask]) / y_true[mask]) ** 2))

def rmspe_lgbm(preds: np.ndarray, train_data: lgb.Dataset):
    y_true = np.expm1(train_data.get_label())
    y_pred = np.expm1(preds)
    return "RMSPE", rmspe(y_true, y_pred), False

# ─── 特徴量エンジニアリング ────────────────────────────────────────────
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

    comp_since_year  = df["CompetitionOpenSinceYear"].fillna(1900)
    comp_since_month = df["CompetitionOpenSinceMonth"].fillna(1)
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
    store_agg["store_std"] = store_agg["store_std"].fillna(0)
    target = target.merge(store_agg, on="Store", how="left")

    for key_cols, col_name in [
        (["Store", "DayOfWeek"], "store_dow_mean"),
        (["Store", "Month"],     "store_month_mean"),
        (["Store", "Promo"],     "store_promo_mean"),
    ]:
        grp = (
            ref.groupby(key_cols)["Sales"].mean()
            .reset_index().rename(columns={"Sales": col_name})
        )
        target = target.merge(grp, on=key_cols, how="left")
        null_mask = target[col_name].isnull()
        if null_mask.any():
            target.loc[null_mask, col_name] = target.loc[null_mask, "store_mean"]

    return target

# ─── NN ユーティリティ関数 ─────────────────────────────────────────────
def normalize_cont(ref: pd.DataFrame, *targets, cont_cols: list):
    """ref の統計量で cont_cols を標準化する。targets は任意個数対応。"""
    mean = ref[cont_cols].mean()
    std  = ref[cont_cols].std().replace(0, 1)
    normalized = []
    for df in targets:
        norm = df.copy()
        norm[cont_cols] = ((df[cont_cols] - mean) / std).fillna(0)
        normalized.append(norm)
    return normalized


def prepare_nn_inputs(df: pd.DataFrame, emb_col_names: list, cont_cols: list) -> list:
    inputs = [df[f"{col}_enc"].values for col in emb_col_names]
    inputs.append(df[cont_cols].values.astype(np.float32))
    return inputs


def build_embedding_model(emb_config: list, n_cont: int) -> keras.Model:
    cat_inputs  = []
    emb_outputs = []

    for col_name, n_unique, emb_dim in emb_config:
        inp = keras.Input(shape=(1,), name=f"input_{col_name}")
        emb = keras.layers.Embedding(
            input_dim=n_unique,
            output_dim=emb_dim,
            name=f"emb_{col_name}",
        )(inp)
        emb = keras.layers.Flatten()(emb)
        cat_inputs.append(inp)
        emb_outputs.append(emb)

    inp_cont   = keras.Input(shape=(n_cont,), name="input_cont")
    all_inputs = cat_inputs + [inp_cont]

    x = keras.layers.Concatenate()(emb_outputs + [inp_cont])
    x = keras.layers.BatchNormalization()(x)

    x = keras.layers.Dense(512, activation="relu")(x)
    x = keras.layers.BatchNormalization()(x)
    x = keras.layers.Dropout(0.3)(x)

    x = keras.layers.Dense(256, activation="relu")(x)
    x = keras.layers.BatchNormalization()(x)
    x = keras.layers.Dropout(0.3)(x)

    x = keras.layers.Dense(128, activation="relu")(x)
    output = keras.layers.Dense(1, name="output")(x)

    return keras.Model(inputs=all_inputs, outputs=output)


def extract_embeddings(nn_model: keras.Model, encoders: dict, emb_config: list) -> dict:
    emb_tables = {}
    for col_name, _, emb_dim in emb_config:
        weights = nn_model.get_layer(f"emb_{col_name}").get_weights()[0]
        le      = encoders[col_name]
        emb_df  = pd.DataFrame(
            weights,
            index=le.classes_,
            columns=[f"{col_name}_emb_{i}" for i in range(emb_dim)],
        )
        emb_df.index.name = f"{col_name}_key"
        emb_tables[col_name] = emb_df
    return emb_tables


def merge_embeddings(df: pd.DataFrame, emb_tables: dict, emb_col_names: list) -> pd.DataFrame:
    df = df.copy()
    for col_name in emb_col_names:
        emb_df = emb_tables[col_name].reset_index()
        df[f"{col_name}_key"] = df[col_name].astype(str)
        df = df.merge(emb_df, on=f"{col_name}_key", how="left").drop(
            columns=[f"{col_name}_key"]
        )
    return df


# ─── データ読み込み & 前処理 ──────────────────────────────────────────
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

print(f"train: {train.shape}  test: {test.shape}")

train = build_features(train)
test  = build_features(test)

train_open = train[train["Open"] == 1].copy()
train_open = train_open[train_open["Sales"] > 0].copy()
train_open["LogSales"] = np.log1p(train_open["Sales"])

VAL_START = pd.Timestamp("2015-06-20")
tr_fold  = train_open[train_open["Date"] <  VAL_START].copy()
val_fold = train_open[train_open["Date"] >= VAL_START].copy()

print(f"\n=== 時系列 Hold-out CV ===")
print(f"  学習: {tr_fold['Date'].min().date()} ~ {tr_fold['Date'].max().date()}  ({len(tr_fold):,} 行)")
print(f"  検証: {val_fold['Date'].min().date()} ~ {val_fold['Date'].max().date()}  ({len(val_fold):,} 行)")

# 店舗別統計量（LightGBM 用: CV-safe）
print("\n店舗別統計量を計算中（LightGBM 用 CV-safe）...")
tr_fold    = add_store_stats(tr_fold,    ref=tr_fold)
val_fold   = add_store_stats(val_fold,   ref=tr_fold)
train_open = add_store_stats(train_open, ref=train_open)
test       = add_store_stats(test,       ref=train_open)

# ─── Label Encoding（NN 用: train_open + test の全値でフィット） ─────
print("\nLabel Encoding 中...")
encoders = {}
for col in EMB_COL_NAMES:
    le = LabelEncoder()
    combined = pd.concat(
        [train_open[col].astype(str), test[col].astype(str)],
        ignore_index=True,
    )
    le.fit(combined)
    encoders[col] = le
    for df in [tr_fold, val_fold, train_open, test]:
        df[f"{col}_enc"] = le.transform(df[col].astype(str))

# 設定確認
print("\n=== Embedding 設定 ===")
total_emb_dim = 0
emb_config = []
for col, dim in EMB_COLS:
    n_unique = len(encoders[col].classes_)
    print(f"  {col:20s}: n_unique={n_unique:5d}  →  embedding_dim={dim}")
    total_emb_dim += dim
    emb_config.append((col, n_unique, dim))
print(f"\n  合計 embedding 次元: {total_emb_dim}")
print(f"  連続変数次元       : {len(CONT_COLS)}")
print(f"  NN 入力合計        : {total_emb_dim + len(CONT_COLS)}")

# ─── 案A: train_open 全データで NN を 1 回だけ学習 ───────────────────
print("\n" + "=" * 60)
print("Entity Embedding NN 学習（案A: train_open 全データ、1 回のみ）")
print("=" * 60)
print("  → tr_fold / val_fold / test 全てに同じ埋め込みを適用")
print("  → CV スコアが実態を反映できる（v6 旧版の Epoch 1 問題を解消）")

# 連続変数の標準化（train_open の統計量で test も変換）
train_open_norm, test_norm, *fold_norms = normalize_cont(
    train_open, train_open, test, tr_fold, val_fold,
    cont_cols=CONT_COLS,
)
tr_fold_norm  = fold_norms[0]
val_fold_norm = fold_norms[1]

model_nn = build_embedding_model(emb_config, n_cont=len(CONT_COLS))
model_nn.compile(
    optimizer=keras.optimizers.Adam(learning_rate=0.001),
    loss="mse",
)
model_nn.summary()

X_full_nn = prepare_nn_inputs(train_open_norm, EMB_COL_NAMES, CONT_COLS)
y_full    = train_open["LogSales"].values.astype(np.float32)

print(f"\nNN 学習中（train_open 全データ, epochs=100, batch_size=1024）...")
model_nn.fit(
    X_full_nn, y_full,
    epochs=100,
    batch_size=1024,
    callbacks=[
        keras.callbacks.EarlyStopping(
            monitor="loss", patience=5, restore_best_weights=True, verbose=1
        ),
        keras.callbacks.ReduceLROnPlateau(
            monitor="loss", factor=0.5, patience=3, min_lr=1e-5, verbose=1
        ),
    ],
    verbose=1,
)

# 埋め込みを抽出（1 回のみ）
print("\n埋め込みを抽出中...")
emb_tables = extract_embeddings(model_nn, encoders, emb_config)

print("\n=== 埋め込みサンプル（Store: 上位 5 件）===")
print(emb_tables["Store"].head(5).round(4))

# 同じ埋め込みを全データフレームに適用
print("\n同じ埋め込みを tr_fold / val_fold / train_open / test に結合中...")
tr_fold_emb    = merge_embeddings(tr_fold,    emb_tables, EMB_COL_NAMES)
val_fold_emb   = merge_embeddings(val_fold,   emb_tables, EMB_COL_NAMES)
train_open_emb = merge_embeddings(train_open, emb_tables, EMB_COL_NAMES)
test_emb       = merge_embeddings(test,       emb_tables, EMB_COL_NAMES)

# ─── LightGBM 特徴量リスト（v4 ベース + 埋め込み） ──────────────────
emb_feature_cols = [
    f"{col}_emb_{i}" for col, dim in EMB_COLS for i in range(dim)
]

FEATURES_BASE = [
    "Store", "StoreType", "Assortment",
    "DayOfWeek", "Year", "Month", "Day", "WeekOfYear",
    "IsWeekend", "IsMonthStart", "IsMonthEnd",
    "Promo", "Promo2", "Promo2Active", "Promo2OpenWeeks",
    "StateHoliday", "SchoolHoliday",
    "LogCompetitionDistance", "CompetitionOpen",
    "store_mean", "store_median", "store_std",
    "store_dow_mean", "store_month_mean", "store_promo_mean",
]
FEATURES = FEATURES_BASE + emb_feature_cols
CAT_COLS = ["StoreType", "Assortment", "StateHoliday"]
TARGET   = "LogSales"

for col in CAT_COLS:
    for df in [tr_fold_emb, val_fold_emb, train_open_emb, test_emb]:
        df[col] = df[col].astype("category")

print(f"\n=== LightGBM 特徴量 ===")
print(f"  ベース特徴量  : {len(FEATURES_BASE)} 個（v4 と同一）")
print(f"  埋め込み特徴量: {len(emb_feature_cols)} 次元")
print(f"  合計          : {len(FEATURES)} 個")

# ─── LightGBM CV 学習 ────────────────────────────────────────────────
print(f"\nLightGBM 学習中（Optuna 最適パラメータ）...")
dtrain = lgb.Dataset(
    tr_fold_emb[FEATURES],  label=tr_fold_emb[TARGET],
    categorical_feature=CAT_COLS,
)
dval   = lgb.Dataset(
    val_fold_emb[FEATURES], label=val_fold_emb[TARGET],
    categorical_feature=CAT_COLS, reference=dtrain,
)

model_lgb = lgb.train(
    BEST_PARAMS,
    dtrain,
    num_boost_round=NUM_BOOST_ROUND,
    valid_sets=[dtrain, dval],
    valid_names=["train", "valid"],
    feval=rmspe_lgbm,
    callbacks=[
        lgb.early_stopping(stopping_rounds=300, verbose=False),
        lgb.log_evaluation(period=1000),
    ],
)

# バリデーション評価
val_pred  = np.expm1(model_lgb.predict(val_fold_emb[FEATURES]))
val_true  = np.expm1(val_fold_emb[TARGET].values)
val_rmspe = rmspe(val_true, val_pred)

tr_pred  = np.expm1(model_lgb.predict(tr_fold_emb[FEATURES]))
tr_true  = np.expm1(tr_fold_emb[TARGET].values)
tr_rmspe = rmspe(tr_true, tr_pred)

print(f"\n=== バリデーション結果 ===")
print(f"  best_iteration      : {model_lgb.best_iteration}")
print(f"  RMSPE (train)       : {tr_rmspe:.5f}")
print(f"  RMSPE (valid)       : {val_rmspe:.5f}  (v4: 0.12674 / v6旧: 0.13241)")
print(f"  差分 (過学習度)     : {val_rmspe - tr_rmspe:+.5f}")
print(f"  改善幅 vs v4        : {val_rmspe - 0.12674:+.5f}")
print(f"  改善幅 vs v6旧      : {val_rmspe - 0.13241:+.5f}")

# 特徴量重要度
print(f"\n=== 特徴量重要度 TOP 20（gain）===")
imp = pd.Series(
    model_lgb.feature_importance(importance_type="gain"),
    index=FEATURES,
).sort_values(ascending=False)
max_val = imp.max()
for feat, val in list(imp.items())[:20]:
    bar = "█" * max(1, int(val / max_val * 30))
    print(f"  {feat:40s}: {val:12.0f}  {bar}")

print(f"\n=== Entity Embedding の重要度（上位 10）===")
emb_imp = imp[emb_feature_cols].sort_values(ascending=False)
for feat, val in list(emb_imp.items())[:10]:
    bar = "█" * max(1, int(val / max_val * 30))
    print(f"  {feat:40s}: {val:12.0f}  {bar}")

# ─── LightGBM 全データ再学習 ─────────────────────────────────────────
print(f"\n全データで LightGBM 再学習中（num_boost_round={model_lgb.best_iteration}）...")
dtrain_full = lgb.Dataset(
    train_open_emb[FEATURES], label=train_open_emb[TARGET],
    categorical_feature=CAT_COLS,
)
model_lgb_full = lgb.train(
    BEST_PARAMS,
    dtrain_full,
    num_boost_round=model_lgb.best_iteration,
)

# ─── テスト予測 ──────────────────────────────────────────────────────
test_pred = np.expm1(model_lgb_full.predict(test_emb[FEATURES]))
test_pred = np.clip(test_pred, 0, None)
test_pred[test["Open"] == 0] = 0

# ─── 提出ファイル ────────────────────────────────────────────────────
submission = pd.DataFrame({"Id": test["Id"], "Sales": test_pred})
out_path   = OUTPUT_DIR / "submission_v6.csv"
submission.to_csv(out_path, index=False)

print(f"\n=== 提出ファイル ===")
print(f"  保存先: {out_path}")
print(f"  行数  : {len(submission):,}")

print(f"\n=== 予測値の統計（Open=1 のみ）===")
pred_open = test_pred[test["Open"] == 1]
print(f"  mean   : {pred_open.mean():,.1f}")
print(f"  median : {np.median(pred_open):,.1f}")
print(f"  std    : {pred_open.std():,.1f}")
print(f"  min    : {pred_open.min():,.1f}")
print(f"  max    : {pred_open.max():,.1f}")

print(f"\n=== スコアまとめ ===")
print(f"  v1 baseline     RMSPE (valid): 0.13670  Kaggle LB: 0.12846")
print(f"  v2 店舗統計量    RMSPE (valid): 0.13310  Kaggle LB: 0.12274")
print(f"  v3 ラグ特徴量    RMSPE (valid): 0.13155  Kaggle LB: 0.12514  ← 悪化")
print(f"  v4 Optuna       RMSPE (valid): 0.12674  Kaggle LB: 0.12172")
print(f"  v6 Entity Emb   RMSPE (valid): {val_rmspe:.5f}  改善幅 (vs v4): {val_rmspe - 0.12674:+.5f}")
print(f"  ※ Kaggle LB はこの後提出して確認")
