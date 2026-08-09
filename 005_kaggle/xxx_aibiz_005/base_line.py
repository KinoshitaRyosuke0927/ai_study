import marimo

__generated_with = "0.23.16"
app = marimo.App(width="medium")


@app.cell
def _():
    import pandas as pd

    ## データ読み込み
    # 学習データ
    train_data = pd.read_csv("train_data.csv")
    # テストデータ
    test_data = pd.read_csv("test_data.csv")

    # 学習データ表示
    train_data
    # test_data
    return pd, test_data, train_data


@app.cell
def _(pd, train_data):
    ## データの整形
    # 目的変数をpivot
    time_seconds_df = train_data.pivot(index="record_id", columns="course_id", values="time_seconds")
    # 整形
    df = pd.merge(train_data.drop(columns=["course_id", "time_seconds"], axis=1), time_seconds_df, on=["record_id"], how="left")
    # session_typeがtournamentの行はquarterが設定されていないので0で埋める
    df["quarter"].values[df["quarter"].isna()] = 0
    # 不要な行を整理
    df = df.drop(columns=["record_id", "date"], axis=1).groupby(["year", "session_type", "quarter", "player_id"], as_index=False).sum()

    # course_idごとの分析
    df.describe()
    return


@app.cell
def _(pd, test_data, train_data):
    import numpy as np
    from sklearn.metrics import mean_squared_error
    from sklearn.linear_model import LinearRegression

    ## 前処理
    # 空欄を0埋め
    train_data["quarter"] = train_data["quarter"].fillna(0)
    test_data["quarter"] = test_data["quarter"].fillna(0)
    # カテゴリー変数をダミー化して分割
    features = ["year", "quarter"]
    categorical = ["session_type", "player_id", "course_id"]
    combined = pd.concat([train_data[features + categorical], test_data[features + categorical]], keys=["train", "test"])
    combined_dummies = pd.get_dummies(combined, columns=categorical)
    X_train = combined_dummies.loc["train"]
    X_test = combined_dummies.loc["test"]
    # 目的変数
    y_train = train_data["time_seconds"]

    ## まずは線形回帰
    # 学習
    model = LinearRegression()
    model.fit(X_train, y_train)
    # 学習誤差計算
    y_pred_train = model.predict(X_train)
    rmse = np.sqrt(mean_squared_error(y_train, y_pred_train))
    print(f"Linear Train RMSE: {rmse}")

    # 予測
    y_pred_test = model.predict(X_test)

    submission_linear = pd.DataFrame({"record_id": test_data["record_id"], "time_seconds": y_pred_test})
    submission_linear.to_csv("submission_linear.csv", index=False)
    print(f"予測完了: submission_linear.csv ({len(submission_linear)}件)")
    return X_test, X_train, mean_squared_error, np, y_train


@app.cell
def _(X_test, X_train, mean_squared_error, np, pd, test_data, y_train):
    from sklearn.linear_model import Ridge

    ## 続いてRidge回帰
    # alphaの値を探索
    for alpha in [0.01, 0.1, 1.0, 10.0, 50.0, 100.0]:
        # 学習
        ridge = Ridge(alpha=alpha)
        ridge.fit(X_train, y_train)
        # 学習誤差計算
        y_pred_train_ridge = ridge.predict(X_train)
        rmse_ridge = np.sqrt(mean_squared_error(y_train, y_pred_train_ridge))
        print(f"Ridge Train RMSE: {rmse_ridge}, alpha={alpha}")

    # alphaが10など大きい場合は差が出るが、1以下になると線形回帰との差は見られない
    #  → ほとんど線形

    # 予測
    ridge = Ridge(alpha=0.01)
    ridge.fit(X_train, y_train)
    y_pred_test_ridge = ridge.predict(X_test)

    submission_ridge = pd.DataFrame({"record_id": test_data["record_id"], "time_seconds": y_pred_test_ridge})
    submission_ridge.to_csv("submission_ridge.csv", index=False)
    print(f"予測完了: submission_ridge.csv ({len(submission_ridge)}件)")
    return


if __name__ == "__main__":
    app.run()
