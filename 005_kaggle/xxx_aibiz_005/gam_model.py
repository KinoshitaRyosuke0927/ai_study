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

    # GAMはカテゴリ変数をダミー化ではなく、整数コードに変換して f() 項として扱う
    categorical_cols = ["session_type", "player_id", "course_id", "quarter"]
    return (categorical_cols,)


@app.cell
def _(categorical_cols, pd):
    from pygam import LinearGAM, s, f

    ## GAM用の前処理関数
    ## year は s() で滑らかな非線形カーブとしてフィットする(収穫逓減カーブを手動変換せずに表現できる)
    ## session_type, player_id, course_id, quarter は f() でカテゴリごとの効果として扱う
    def encode_categoricals(fit_df, other_df):
        fit_df = fit_df.copy()
        other_df = other_df.copy()
        for col in categorical_cols:
            categories = pd.concat([fit_df[col], other_df[col]]).astype(str).unique()
            cat_type = pd.CategoricalDtype(categories=sorted(categories))
            fit_df[col + "_code"] = fit_df[col].astype(str).astype(cat_type).cat.codes
            other_df[col + "_code"] = other_df[col].astype(str).astype(cat_type).cat.codes
        return fit_df, other_df

    def build_X(df):
        code_cols = [c + "_code" for c in categorical_cols]
        return df[["year"] + code_cols].to_numpy(dtype=float)

    # X列の並び: [year, session_type_code, player_id_code, course_id_code, quarter_code]
    gam_terms = s(0) + f(1) + f(2) + f(3) + f(4)

    return LinearGAM, build_X, encode_categoricals, gam_terms


@app.cell
def _(LinearGAM, build_X, encode_categoricals, gam_terms, train_data):
    import numpy as np
    from sklearn.metrics import mean_squared_error

    ## 外挿性能の検証
    ## year<=4 で学習し、year==5 を「訓練データにない未知の年」とみなして評価する
    ## (本番のtest.csvもyear=6という訓練データにない年なので、同じ状況を模擬できる)
    fit_part = train_data[train_data["year"] <= 4]
    valid_part = train_data[train_data["year"] == 5]
    fit_enc, valid_enc = encode_categoricals(fit_part, valid_part)

    X_fit = build_X(fit_enc)
    X_valid = build_X(valid_enc)

    gam = LinearGAM(gam_terms).fit(X_fit, fit_enc["time_seconds"])
    rmse_valid = np.sqrt(mean_squared_error(valid_enc["time_seconds"], gam.predict(X_valid)))

    print("=== year=5を未知年に見立てた検証RMSE (GAM) ===")
    print(f"RMSE: {rmse_valid:.3f}")

    return mean_squared_error, np


@app.cell
def _(LinearGAM, build_X, encode_categoricals, gam_terms, mean_squared_error, np, pd, test_data, train_data):
    ## 本番学習: year 1-5 の全データで学習し、test (year=6) を予測
    train_enc, test_enc = encode_categoricals(train_data, test_data)

    X_train = build_X(train_enc)
    X_test = build_X(test_enc)
    y_train = train_enc["time_seconds"]

    model = LinearGAM(gam_terms)
    model.fit(X_train, y_train)

    # 学習誤差計算
    y_pred_train = model.predict(X_train)
    rmse = np.sqrt(mean_squared_error(y_train, y_pred_train))
    print(f"GAM Train RMSE: {rmse}")

    # 予測
    y_pred_test = model.predict(X_test)

    submission_gam = pd.DataFrame({"record_id": test_data["record_id"], "time_seconds": y_pred_test})
    submission_gam.to_csv("submission_gam.csv", index=False)
    print(f"予測完了: submission_gam.csv ({len(submission_gam)}件)")
    return


if __name__ == "__main__":
    app.run()
