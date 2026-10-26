"""講座「統計検定2級対策 1:記述統計」の演習データを作る(Pyodide で実行し、CSV を出力する)。"""

import numpy as np
import pandas as pd

rng = np.random.default_rng(20261025)

# ---------- households.csv: 世帯の年収など(右に裾が長い分布・ジニ係数・クロス表用) ----------
n = 200
regions = ["北日本", "関東", "中部", "近畿", "西日本"]
region = rng.choice(regions, size=n, p=[0.15, 0.32, 0.18, 0.17, 0.18])
members = rng.choice([1, 2, 3, 4, 5, 6], size=n, p=[0.28, 0.30, 0.18, 0.15, 0.07, 0.02])
region_effect = pd.Series({"北日本": -0.12, "関東": 0.15, "中部": 0.02, "近畿": 0.04, "西日本": -0.08})
log_income = 6.05 + region_effect[region].to_numpy() + 0.07 * (members - 1) + rng.normal(0, 0.55, n)
income = np.clip(np.round(np.exp(log_income)), 80, None).astype(int)
# 持ち家の確率は、年収が高いほど、関東以外ほど高い
logit = -2.2 + 0.0045 * income + np.where(region == "関東", -0.9, 0.3) + 0.25 * (members - 1)
owner = rng.random(n) < 1 / (1 + np.exp(-logit))
housing = np.where(owner, "持ち家", "賃貸")
satisfaction = np.clip(np.round(2.6 + 0.0012 * income + rng.normal(0, 0.9, n)), 1, 5).astype(int)
households = pd.DataFrame(
    {
        "id": np.arange(1, n + 1),
        "region": region,
        "members": members,
        "income": income,
        "housing": housing,
        "satisfaction": satisfaction,
    }
)
households.to_csv("households.csv", index=False)

# ---------- students.csv: 学習時間とテストの点数(標準化・相関・単回帰用) ----------
n = 120
cls = np.repeat(["A", "B", "C"], n // 3)
study = np.round(np.clip(rng.gamma(4.0, 2.0, n), 0.5, 25), 1)
ability = rng.normal(0, 1, n)
math = np.clip(np.round(38 + 1.9 * study + 7 * ability + rng.normal(0, 6, n)), 0, 100).astype(int)
english = np.clip(np.round(52 + 0.9 * study + 5 * ability + rng.normal(0, 9, n)), 0, 100).astype(int)
science = np.clip(np.round(45 + 1.2 * study + 6 * ability + rng.normal(0, 8, n)), 0, 100).astype(int)
sleep = np.round(np.clip(7.4 - 0.06 * study + rng.normal(0, 0.6, n), 4.5, 9.5), 1)
students = pd.DataFrame(
    {
        "id": np.arange(1, n + 1),
        "class": cls,
        "study_hours": study,
        "math": math,
        "english": english,
        "science": science,
        "sleep_hours": sleep,
    }
)
students.to_csv("students.csv", index=False)

# ---------- kids.csv: 小学生の足の大きさと語彙数(見かけの相関・偏相関・層別用) ----------
rows = []
for grade in range(1, 7):
    for _ in range(15):
        foot = 17.0 + 0.85 * grade + rng.normal(0, 0.8)
        vocab = 2500 + 1600 * grade + rng.normal(0, 900)
        rows.append((grade, round(foot, 1), int(round(vocab, -1))))
kids = pd.DataFrame(rows, columns=["grade", "foot_cm", "vocab"])
kids.to_csv("kids.csv", index=False)

# ---------- monthly_sales.csv: 月次売上(移動平均・成長率・自己相関用) ----------
months = pd.period_range("2018-01", "2025-12", freq="M")
t = np.arange(len(months))
season = np.array([-8, -12, 2, 0, 3, 6, 10, 14, 1, -2, 0, 18], dtype=float)
sales = 120 * 1.006 ** t + season[months.month.to_numpy() - 1] + rng.normal(0, 4, len(t))
monthly = pd.DataFrame({"month": months.astype(str), "sales": np.round(sales, 1)})
monthly.to_csv("monthly_sales.csv", index=False)

print(households.describe().round(1).to_string())
print(students.describe().round(1).to_string())
print(kids.groupby("grade").mean().round(1).to_string())
print(monthly.head(13).to_string())
