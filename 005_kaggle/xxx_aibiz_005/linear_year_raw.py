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
def _(test_data, train_data):
    ## 前処理
    # 空欄を0埋め
    train_data["quarter"] = train_data["quarter"].fillna(0)
    test_data["quarter"] = test_data["quarter"].fillna(0)

    categorical_cols = ["session_type", "player_id", "course_id"]
    return (categorical_cols,)


@app.cell
def _(categorical_cols, pd, train_data):
    import numpy as np
    from sklearn.metrics import mean_squared_error
    from sklearn.linear_model import LinearRegression

    ## 外挿性能の検証
    ## year<=4 で学習し、year==5 を「訓練データにない未知の年」とみなして評価する
    fit_part = train_data[train_data["year"] <= 4]
    valid_part = train_data[train_data["year"] == 5]

    def make_xy(feature_cols, fit_df, valid_df):
        combined = pd.concat(
            [fit_df[feature_cols + categorical_cols], valid_df[feature_cols + categorical_cols]],
            keys=["fit", "valid"],
        )
        dummies = pd.get_dummies(combined, columns=categorical_cols)
        return dummies.loc["fit"], dummies.loc["valid"]

    X_fit, X_valid = make_xy(["year", "quarter"], fit_part, valid_part)
    m = LinearRegression().fit(X_fit, fit_part["time_seconds"])
    rmse_valid = np.sqrt(mean_squared_error(valid_part["time_seconds"], m.predict(X_valid)))

    print("=== year=5を未知年に見立てた検証RMSE (線形回帰 / yearそのまま) ===")
    print(f"RMSE: {rmse_valid:.3f}")

    return LinearRegression, make_xy, mean_squared_error, np


@app.cell
def _(LinearRegression, categorical_cols, make_xy, mean_squared_error, np, pd, test_data, train_data):
    ## 本番学習: year 1-5 の全データで学習し、test (year=6) を予測
    features = ["year", "quarter"]

    X_train, X_test = make_xy(features, train_data, test_data)
    y_train = train_data["time_seconds"]

    model = LinearRegression()
    model.fit(X_train, y_train)

    # 学習誤差計算
    y_pred_train = model.predict(X_train)
    rmse = np.sqrt(mean_squared_error(y_train, y_pred_train))
    print(f"Linear (yearそのまま) Train RMSE: {rmse}")

    # 予測
    y_pred_test = model.predict(X_test)

    submission_linear = pd.DataFrame({"record_id": test_data["record_id"], "time_seconds": y_pred_test})
    submission_linear.to_csv("submission_linear.csv", index=False)
    print(f"予測完了: submission_linear.csv ({len(submission_linear)}件)")
    return


if __name__ == "__main__":
    app.run()
