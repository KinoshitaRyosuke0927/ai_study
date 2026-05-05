import pandas as pd


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """特徴量エンジニアリング。エンコード前のデータフレームに適用する。"""
    df = df.copy()

    # ── 気象・水分系 ───────────────────────────────────────────
    # 気温と湿度の複合：蒸発散量の代理変数（高いほど水が蒸発しやすい）
    df["Temp_x_Humidity"] = df["Temperature_C"] * df["Humidity"]

    # 降水量から土壌水分を引いた水分収支（負 → 灌漑が必要な状態）
    df["Water_balance"] = df["Rainfall_mm"] - df["Soil_Moisture"] * 10

    # 風速が強いほど蒸発が促進される → 気温×風速
    df["Temp_x_Wind"] = df["Temperature_C"] * df["Wind_Speed_kmh"]

    # 日照時間×気温：蒸発散量に直結
    df["Sun_x_Temp"] = df["Sunlight_Hours"] * df["Temperature_C"]

    # ── 土壌系 ────────────────────────────────────────────────
    # 土壌水分÷降水量：降水に対して土壌がどれだけ保水できているか
    df["Moisture_rain_ratio"] = df["Soil_Moisture"] / (df["Rainfall_mm"] + 1)

    # 有機炭素×土壌水分：保水力の複合指標
    df["OC_x_Moisture"] = df["Organic_Carbon"] * df["Soil_Moisture"]

    # ── 農地・作物系 ──────────────────────────────────────────
    # 単位面積あたりの降水量
    df["Rain_per_area"] = df["Rainfall_mm"] / (df["Field_Area_hectare"] + 1)

    # 前回灌漑量と現在の土壌水分の差：追加灌漑の必要度
    df["Irr_moisture_diff"] = df["Previous_Irrigation_mm"] - df["Soil_Moisture"]

    # ── 統計集約特徴量 ────────────────────────────────────────
    # 数値特徴量の行ごとの平均・標準偏差（外れ値レコードを検出）
    num_cols = [
        "Soil_pH", "Soil_Moisture", "Organic_Carbon", "Electrical_Conductivity",
        "Temperature_C", "Humidity", "Rainfall_mm", "Sunlight_Hours",
        "Wind_Speed_kmh", "Field_Area_hectare", "Previous_Irrigation_mm",
    ]
    df["num_mean"] = df[num_cols].mean(axis=1)
    df["num_std"]  = df[num_cols].std(axis=1)

    return df
