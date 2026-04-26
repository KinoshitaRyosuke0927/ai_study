import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
import seaborn as sns
from pathlib import Path

matplotlib.rcParams['font.family'] = 'MS Gothic'

DATA_DIR = Path(__file__).parent.parent / "competitions" / "spaceship-titanic"

df = pd.read_csv(DATA_DIR / "train.csv")

# --- 前処理: 列分割 ---
df[['Deck', 'CabinNum', 'Side']] = df['Cabin'].str.split('/', expand=True)
df['Group'] = df['PassengerId'].str.split('_').str[0]
df['GroupSize'] = df.groupby('Group')['Group'].transform('count')

AMENITIES = ['RoomService', 'FoodCourt', 'ShoppingMall', 'Spa', 'VRDeck']
df['TotalSpend'] = df[AMENITIES].sum(axis=1)

# ==============================================================
# 1. 基本情報
# ==============================================================
print("=" * 60)
print("1. データ概要")
print("=" * 60)
print(f"行数: {len(df):,}  列数: {df.shape[1]}")
print()
print("--- 欠損値 ---")
missing = df.isnull().sum()
print(missing[missing > 0].to_string())
print()
print("--- 数値列の統計量 ---")
print(df.describe().T.to_string())

# ==============================================================
# 2. ターゲット分布
# ==============================================================
fig, axes = plt.subplots(1, 2, figsize=(10, 4))
fig.suptitle("2. ターゲット (Transported) の分布", fontsize=13)

counts = df['Transported'].value_counts()
axes[0].pie(counts, labels=['False', 'True'], autopct='%1.1f%%', startangle=90,
            colors=['#5B9BD5', '#ED7D31'])
axes[0].set_title("転送あり/なし の割合")

axes[1].bar(['False', 'True'], counts.values, color=['#5B9BD5', '#ED7D31'])
axes[1].set_title("転送あり/なし の件数")
axes[1].set_ylabel("件数")
for i, v in enumerate(counts.values):
    axes[1].text(i, v + 30, str(v), ha='center', fontweight='bold')

plt.tight_layout()
plt.savefig(DATA_DIR / "eda_target.png", dpi=100)
plt.show()

# ==============================================================
# 3. カテゴリ列 × 転送率
# ==============================================================
CAT_COLS = ['HomePlanet', 'CryoSleep', 'Destination', 'VIP', 'Deck', 'Side']

fig, axes = plt.subplots(2, 3, figsize=(15, 9))
fig.suptitle("3. カテゴリ列ごとの転送率", fontsize=13)

for ax, col in zip(axes.flatten(), CAT_COLS):
    rate = df.groupby(col)['Transported'].mean().sort_values(ascending=False)
    bars = ax.bar(rate.index.astype(str), rate.values, color='#5B9BD5')
    ax.axhline(df['Transported'].mean(), color='red', linestyle='--', linewidth=1, label='全体平均')
    ax.set_title(col)
    ax.set_ylabel("転送率")
    ax.set_ylim(0, 1)
    ax.legend(fontsize=8)
    for bar, v in zip(bars, rate.values):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 0.02,
                f'{v:.2f}', ha='center', fontsize=9)

plt.tight_layout()
plt.savefig(DATA_DIR / "eda_categorical.png", dpi=100)
plt.show()

print("\n--- カテゴリ列ごとの転送率 ---")
for col in CAT_COLS:
    print(f"\n[{col}]")
    print(df.groupby(col)['Transported'].agg(['mean', 'count'])
          .rename(columns={'mean': '転送率', 'count': '件数'}).to_string())

# ==============================================================
# 4. 数値列の分布 (転送あり vs なし)
# ==============================================================
NUM_COLS = ['Age', 'TotalSpend'] + AMENITIES

fig, axes = plt.subplots(2, 4, figsize=(18, 9))
fig.suptitle("4. 数値列の分布 (転送あり vs なし)", fontsize=13)

for ax, col in zip(axes.flatten(), NUM_COLS):
    for transported, color, label in [(True, '#ED7D31', 'Transported'), (False, '#5B9BD5', 'Not Transported')]:
        data = df[df['Transported'] == transported][col].dropna()
        ax.hist(data, bins=40, alpha=0.6, color=color, label=label, density=True)
    ax.set_title(col)
    ax.set_xlabel(col)
    ax.set_ylabel("密度")
    ax.legend(fontsize=8)

axes.flatten()[-1].set_visible(False)
plt.tight_layout()
plt.savefig(DATA_DIR / "eda_numeric.png", dpi=100)
plt.show()

# ==============================================================
# 5. 相関ヒートマップ
# ==============================================================
num_df = df[['Age', 'TotalSpend'] + AMENITIES + ['GroupSize']].copy()
num_df['Transported'] = df['Transported'].astype(int)

fig, ax = plt.subplots(figsize=(10, 8))
sns.heatmap(num_df.corr(), annot=True, fmt='.2f', cmap='coolwarm',
            center=0, ax=ax, square=True)
ax.set_title("5. 数値列の相関ヒートマップ (Transported含む)", fontsize=13)
plt.tight_layout()
plt.savefig(DATA_DIR / "eda_correlation.png", dpi=100)
plt.show()

print("\n--- Transported との相関 (上位順) ---")
corr = num_df.corr()['Transported'].drop('Transported').sort_values(key=abs, ascending=False)
print(corr.to_string())

# ==============================================================
# 6. Feature Importance (RandomForest)
# ==============================================================
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder

print("\n" + "=" * 60)
print("6. RandomForest Feature Importance")
print("=" * 60)

rf_df = df[['HomePlanet', 'CryoSleep', 'Destination', 'Age', 'VIP',
            'TotalSpend'] + AMENITIES + ['Deck', 'Side', 'GroupSize', 'Transported']].copy()

for col in ['HomePlanet', 'CryoSleep', 'Destination', 'VIP', 'Deck', 'Side']:
    rf_df[col] = LabelEncoder().fit_transform(rf_df[col].astype(str))

rf_df = rf_df.fillna(rf_df.median(numeric_only=True))

X = rf_df.drop('Transported', axis=1)
y = rf_df['Transported'].astype(int)

model = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
model.fit(X, y)

importances = pd.Series(model.feature_importances_, index=X.columns).sort_values(ascending=True)

fig, ax = plt.subplots(figsize=(9, 6))
importances.plot(kind='barh', ax=ax, color='#5B9BD5')
ax.set_title("6. RandomForest Feature Importance", fontsize=13)
ax.set_xlabel("重要度")
plt.tight_layout()
plt.savefig(DATA_DIR / "eda_feature_importance.png", dpi=100)
plt.show()

print(importances.sort_values(ascending=False).to_string())
