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
    df["刊行年"] = pub.dt.year
    df["購入年"] = buy.dt.year
    df["刊行経過年数"] = 2024 - df["刊行年"]
    df["購入経過年数"] = 2024 - df["購入年"]
    df["刊行から購入日数"] = (buy - pub).dt.days

    return df


# 特徴量追加
train = add_date_features(train)
test  = add_date_features(test)

# 目的変数
y_train = train[TARGET]


# Target Encoding
def target_encode(
    train_col: pd.Series,
    test_col: pd.Series,
    y: pd.Series,
    n_splits: int = N_SPLITS,
) -> tuple[pd.Series, pd.Series]:

    # 全体平均計算
    global_mean = y.mean()
    # 入れ物用意
    te_train = pd.Series(np.nan, index=train_col.index)
    # K-Fold
    kf = KFold(n_splits=n_splits, shuffle=True, random_state=RANDOM_STATE)
    for tr_idx, val_idx in kf.split(train_col):
        tmp   = pd.DataFrame({"key": train_col.iloc[tr_idx].values, "y": y.iloc[tr_idx].values})
        means = tmp.groupby("key")["y"].mean()
        te_train.iloc[val_idx] = train_col.iloc[val_idx].map(means).fillna(global_mean).values

    # グループごとの平均値計算
    all_means = pd.DataFrame({"key": train_col.values, "y": y.values}).groupby("key")["y"].mean()
    # 置き換え
    te_test   = test_col.map(all_means).fillna(global_mean)
    te_test.index = test_col.index

    return te_train, te_test


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
        feat["刊行年"] = df["刊行年"]
        feat["購入年"] = df["購入年"]
        # 経過年数
        feat["刊行経過年数"] = df["刊行経過年数"]
        feat["購入経過年数"] = df["購入経過年数"]
        # 刊行から購入までの期間
        feat["刊行から購入日数"] = df["刊行から購入日数"]
        # NDC分類
        feat["NDC大分類"] = (df["NDC分類"] // 100) * 100
        feat["NDC細分類"] = df["NDC分類"]
        # シリーズ有無・巻数
        feat["シリーズ"] = df["巻数"].notna().astype(int)
        feat["巻数"] = df["巻数"].fillna(0)
        # 蔵書数・ページ数
        feat["蔵書数"] = df["蔵書数"]
        feat["ページ数"] = df["ページ数"]
        # タイトル言語
        feat["英語タイトル"] = df["タイトル"].str.match(r"^[A-Za-z]").astype(int)

        return feat

    # 特徴量選択
    X_tr = extract(train_df)
    X_te = extract(test_df)

    # 著者名・出版社・NDC分類名 を Target Encoding で数値化
    for col in ["著者名", "出版社", "NDC分類名"]:
        te_tr, te_te = target_encode(train_df[col], test_df[col], y)
        X_tr[f"{col}_te"] = te_tr.values
        X_te[f"{col}_te"] = te_te.values

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
kf = KFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)
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
submission = pd.DataFrame({"タイトル":  test["タイトル"], "予測貸出数": np.round(test_pred).astype(int)})
# 提出用ファイル作成
submission.to_csv("submission_fe_v1.csv", index=False, encoding="utf-8-sig")
print("\nsubmission_fe_v1.csv を出力しました。")
