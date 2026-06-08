import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import KFold

# 定数
TARGET = "去年の貸出数"
N_SPLITS = 5
RANDOM_STATE = 42


# データ読み込み
train = pd.read_csv("train_data.csv", encoding="utf-8")
test  = pd.read_csv("test_data.csv",  encoding="utf-8")


# 日付特徴量の追加
def add_date_features(df: pd.DataFrame) -> pd.DataFrame:

    pub = pd.to_datetime(df["刊行年月日"], errors="coerce")
    buy = pd.to_datetime(df["購入年月日"], errors="coerce")
    df = df.copy()
    df["刊行年"]           = pub.dt.year
    df["購入年"]           = buy.dt.year
    df["刊行経過年数"]     = 2024 - df["刊行年"]
    df["購入経過年数"]     = 2024 - df["購入年"]
    df["刊行から購入日数"] = (buy - pub).dt.days

    return df


# 特徴量追加
train = add_date_features(train)
test  = add_date_features(test)

# 目的変数
y_train = train[TARGET]


# 集約特徴量エンコーディング
def group_agg_encode(
    train_col: pd.Series,
    test_col: pd.Series,
    y: pd.Series,
    agg: str,
    n_splits: int = N_SPLITS,
) -> tuple[pd.Series, pd.Series]:

    if agg == "count":
        counts    = train_col.value_counts()
        enc_train = train_col.map(counts).fillna(0).astype(int)
        enc_test  = test_col.map(counts).fillna(0).astype(int)
        enc_test.index = test_col.index
        return enc_train, enc_test

    # 全体の統計値計算
    global_val = y.agg(agg)
    # 入れ物用意
    enc_train = pd.Series(np.nan, index=train_col.index)
    # K-Fold
    kf = KFold(n_splits=n_splits, shuffle=True, random_state=RANDOM_STATE)
    for tr_idx, val_idx in kf.split(train_col):
        tmp   = pd.DataFrame({"key": train_col.iloc[tr_idx].values, "y": y.iloc[tr_idx].values})
        stats = tmp.groupby("key")["y"].agg(agg)
        enc_train.iloc[val_idx] = train_col.iloc[val_idx].map(stats).fillna(global_val).values

    # グループごとの統計値計算
    all_stats = (
        pd.DataFrame({"key": train_col.values, "y": y.values})
        .groupby("key")["y"]
        .agg(agg)
    )
    # 置き換え
    enc_test = test_col.map(all_stats).fillna(global_val)
    enc_test.index = test_col.index

    return enc_train, enc_test


# 特徴量構築
def build_features(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    y: pd.Series,
) -> tuple[pd.DataFrame, pd.DataFrame]:

    def extract(df: pd.DataFrame) -> pd.DataFrame:

        # 入れ物用意
        feat = pd.DataFrame(index=df.index)
        # 刊行・購入年
        feat["刊行年"]           = df["刊行年"]
        feat["購入年"]           = df["購入年"]
        # 経過年数
        feat["刊行経過年数"]     = df["刊行経過年数"]
        feat["購入経過年数"]     = df["購入経過年数"]
        # 刊行から購入までの期間
        feat["刊行から購入日数"] = df["刊行から購入日数"]
        # NDC分類
        feat["NDC大分類"]        = (df["NDC分類"] // 100) * 100
        feat["NDC細分類"]        = df["NDC分類"]
        # シリーズ有無・巻数
        feat["シリーズ"]         = df["巻数"].notna().astype(int)
        feat["巻数"]             = df["巻数"].fillna(0)
        # 蔵書数・ページ数
        feat["蔵書数"]           = df["蔵書数"]
        feat["ページ数"]         = df["ページ数"]
        # タイトル言語
        feat["英語タイトル"]     = df["タイトル"].str.match(r"^[A-Za-z]").astype(int)

        return feat

    # 特徴量選択
    X_tr = extract(train_df)
    X_te = extract(test_df)

    global_mean = y.mean()

    # 著者名・出版社・NDC分類名 を Target Encoding で数値化
    for col in ["著者名", "出版社", "NDC分類名"]:
        tr_mean, te_mean = group_agg_encode(train_df[col], test_df[col], y, "mean")
        X_tr[f"{col}_mean"] = tr_mean.values
        X_te[f"{col}_mean"] = te_mean.values

    # 著者名の集約特徴量
    tr_cnt, te_cnt = group_agg_encode(train_df["著者名"], test_df["著者名"], y, "count")
    X_tr["著者名_count"] = tr_cnt.values
    X_te["著者名_count"] = te_cnt.values

    tr_std, te_std = group_agg_encode(train_df["著者名"], test_df["著者名"], y, "std")
    X_tr["著者名_std"]       = tr_std.values
    X_te["著者名_std"]       = te_std.values
    X_tr["著者名_mean_diff"] = X_tr["著者名_mean"] - global_mean
    X_te["著者名_mean_diff"] = X_te["著者名_mean"] - global_mean

    # 出版社の集約特徴量
    tr_cnt, te_cnt = group_agg_encode(train_df["出版社"], test_df["出版社"], y, "count")
    X_tr["出版社_count"] = tr_cnt.values
    X_te["出版社_count"] = te_cnt.values

    tr_std, te_std = group_agg_encode(train_df["出版社"], test_df["出版社"], y, "std")
    X_tr["出版社_std"] = tr_std.values
    X_te["出版社_std"] = te_std.values

    # NDC細分類の集約特徴量
    tr_mean, te_mean = group_agg_encode(train_df["NDC分類"], test_df["NDC分類"], y, "mean")
    X_tr["NDC細分類_mean"] = tr_mean.values
    X_te["NDC細分類_mean"] = te_mean.values

    tr_std, te_std = group_agg_encode(train_df["NDC分類"], test_df["NDC分類"], y, "std")
    X_tr["NDC細分類_std"]       = tr_std.values
    X_te["NDC細分類_std"]       = te_std.values
    X_tr["NDC細分類_mean_diff"] = X_tr["NDC細分類_mean"] - global_mean
    X_te["NDC細分類_mean_diff"] = X_te["NDC細分類_mean"] - global_mean

    # NDC大分類の集約特徴量
    ndc_large_tr = train_df["NDC分類"].floordiv(100).mul(100).astype(str)
    ndc_large_te = test_df["NDC分類"].floordiv(100).mul(100).astype(str)

    tr_mean, te_mean = group_agg_encode(ndc_large_tr, ndc_large_te, y, "mean")
    X_tr["NDC大分類_mean"] = tr_mean.values
    X_te["NDC大分類_mean"] = te_mean.values

    tr_std, te_std = group_agg_encode(ndc_large_tr, ndc_large_te, y, "std")
    X_tr["NDC大分類_std"] = tr_std.values
    X_te["NDC大分類_std"] = te_std.values

    return X_tr, X_te


# 前処理
X_train, X_test = build_features(train, test, y_train)

# LightGBM
params = {
    "objective": "regression_l1",
    "metric": "mae",
    "num_leaves": 31,
    "learning_rate": 0.05,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "min_child_samples": 10,
    "random_state": RANDOM_STATE,
    "verbose": -1,
}

# CV + OOF予測
kf        = KFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)
oof_pred  = np.zeros(len(X_train))
test_pred = np.zeros(len(X_test))
for fold, (tr_idx, val_idx) in enumerate(kf.split(X_train), 1):
    X_tr, X_val = X_train.iloc[tr_idx], X_train.iloc[val_idx]
    y_tr, y_val = y_train.iloc[tr_idx], y_train.iloc[val_idx]

    dtrain = lgb.Dataset(X_tr, label=y_tr)
    dvalid = lgb.Dataset(X_val, label=y_val, reference=dtrain)

    model = lgb.train(
        params,
        dtrain,
        num_boost_round=2000,
        valid_sets=[dvalid],
        callbacks=[
            lgb.early_stopping(stopping_rounds=100, verbose=False),
        ],
    )
    oof_pred[val_idx]  = model.predict(X_val)
    test_pred         += model.predict(X_test) / N_SPLITS

    fold_mae = mean_absolute_error(y_val, oof_pred[val_idx])
    print(f"Fold {fold} MAE: {fold_mae:.4f}  (best iteration: {model.best_iteration})")

cv_mae = mean_absolute_error(y_train, oof_pred)
print(f"\nCV MAE (OOF): {cv_mae:.4f}")

# 特徴量重要度
importances = pd.Series(
    model.feature_importance(importance_type="gain"),
    index=X_train.columns,
)
print("\n--- 特徴量重要度 (gain) ---")
print(importances.sort_values(ascending=False).to_string())

# 予測
submission = pd.DataFrame({"タイトル": test["タイトル"], "予測貸出数": np.round(test_pred).astype(int)})
# 提出用ファイル作成
submission.to_csv("submission_fe_v2.csv", index=False, encoding="utf-8-sig")
print("\nsubmission_fe_v2.csv を出力しました。")
