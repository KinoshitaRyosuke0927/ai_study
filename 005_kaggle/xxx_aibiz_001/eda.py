import pandas as pd
import numpy as np

train = pd.read_csv("pre_eval.csv")
test = pd.read_csv("test_eval.csv")

print("=" * 60)
print("【学習データ概要】")
print(f"行数: {len(train)}, 列数: {len(train.columns)}")
print(f"カラム: {list(train.columns)}")

print("\n【テストデータ概要】")
print(f"行数: {len(test)}, 列数: {len(test.columns)}")
print(f"カラム: {list(test.columns)}")

print("\n" + "=" * 60)
print("【学習データ 基本統計量】")
print(train.describe().T.to_string())

print("\n" + "=" * 60)
print("【欠損値確認】")
print("学習データ:", train.isnull().sum().to_dict())
print("テストデータ:", test.isnull().sum().to_dict())

print("\n" + "=" * 60)
print("【カテゴリ・バイナリ特徴量の分布】")
binary_cols = ["is_south_facing", "has_parking", "renovation_done"]
for col in binary_cols:
    vc = train[col].value_counts()
    print(f"  {col}: {vc.to_dict()}")

print(f"\n  ward_type: {train['ward_type'].value_counts().sort_index().to_dict()}")

print("\n" + "=" * 60)
print("【目的変数 price_10kyen の分布】")
p = train["price_10kyen"]
print(f"  min={p.min()}, max={p.max()}, mean={p.mean():.1f}, median={p.median():.1f}, std={p.std():.1f}")

print("\n" + "=" * 60)
print("【各特徴量と price_10kyen の相関】")
corr = train.corr(numeric_only=True)["price_10kyen"].drop("price_10kyen").sort_values(ascending=False)
print(corr.to_string())

print("\n" + "=" * 60)
print("【連続値特徴量の範囲】")
cont_cols = ["area_m2", "age_years", "station_walk_min", "floor", "rooms", "school_walk_min"]
for col in cont_cols:
    print(f"  {col}: min={train[col].min()}, max={train[col].max()}, mean={train[col].mean():.1f}")
