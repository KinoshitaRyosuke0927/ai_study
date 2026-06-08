import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import cross_val_score


# データ読み込み
train = pd.read_csv("train_data.csv", encoding="utf-8")
test  = pd.read_csv("test_data.csv",  encoding="utf-8")


# 特徴量選択
def build_features(df: pd.DataFrame) -> pd.DataFrame:
    # 入れ物用意
    feat = pd.DataFrame()
    # 刊行年・購入年
    feat["刊行年"] = pd.to_datetime(df["刊行年月日"], errors="coerce").dt.year
    feat["購入年"] = pd.to_datetime(df["購入年月日"], errors="coerce").dt.year
    # NDC大分類
    feat["NDC大分類"] = (df["NDC分類"] // 100) * 100
    # NDC細分類
    feat["NDC細分類"] = df["NDC分類"]
    # シリーズ有無
    feat["シリーズ"] = df["巻数"].notna().astype(int)
    # 蔵書数
    feat["蔵書数"] = df["蔵書数"]
    # タイトルの言語（先頭文字がアルファベットなら英語=1）
    feat["英語タイトル"] = df["タイトル"].str.match(r"^[A-Za-z]").astype(int)

    return feat


# 特徴量設定
X_train = build_features(train)
X_test = build_features(test)

# 目的変数
y_train = train["去年の貸出数"]

# モデル用意
model = RandomForestRegressor(
    n_estimators=300,
    max_depth=None,
    min_samples_leaf=5,
    random_state=42,
    n_jobs=-1,
)

# CV
cv_scores = cross_val_score(
    model, X_train, y_train,
    cv=5,
    scoring="neg_mean_absolute_error",
)
print(f"CV MAE: {-cv_scores.mean():.4f} ± {cv_scores.std():.4f}")
model.fit(X_train, y_train)

# 学習データでMAE計算
y_pred_train = model.predict(X_train)
train_mae = mean_absolute_error(y_train, y_pred_train)
print(f"Train MAE: {train_mae:.4f}")

# 特徴量重要度
importances = pd.Series(model.feature_importances_, index=X_train.columns)
print("\n--- 特徴量重要度 ---")
print(importances.sort_values(ascending=False).to_string())

# 予測
test_pred = model.predict(X_test)
# 提出用ファイル作成
submission = pd.DataFrame({"タイトル": test["タイトル"], "予測貸出数": np.round(test_pred).astype(int)})
submission.to_csv("submission_baseline.csv", index=False, encoding="utf-8-sig")
print("\nsubmission_baseline.csv を出力しました。")
