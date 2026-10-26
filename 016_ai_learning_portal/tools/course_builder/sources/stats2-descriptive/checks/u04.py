"""単元4(歪度・尖度・ジニ係数・カイ二乗値)の解説・演習に使う数値を計算して確かめる。"""
import numpy as np
from scipy import stats


def gini(values):
    """ローレンツ曲線の下の面積(台形の和)からジニ係数を求める。"""
    x = np.sort(np.asarray(values, dtype=float))
    L = np.concatenate([[0], np.cumsum(x) / x.sum()])
    area = np.sum((L[:-1] + L[1:]) / 2) / len(x)
    return L, area, 1 - 2 * area


# 解説: 歪度・尖度の例(図に使う分布と同じ乱数)
rng = np.random.default_rng(0)
samples = {
    "normal": rng.normal(0, 1, 5000),
    "right": rng.lognormal(0, 0.6, 5000),
    "uniform": rng.uniform(0, 1, 5000),
    "heavy(t5)": rng.standard_t(5, 5000),
}
for k, v in samples.items():
    print(k, "歪度", round(stats.skew(v), 2), "尖度", round(stats.kurtosis(v), 2))

# 解説: 歪度の手計算の例
x = np.array([1, 2, 2, 3, 7])
z = (x - x.mean()) / x.std()
print("歪度例 平均", x.mean(), "SD(n)", round(x.std(), 4), "z", z.round(3).tolist(), "歪度", round((z ** 3).mean(), 3))

# 解説: ローレンツ曲線の例
L, area, g = gini([100, 200, 300, 400, 1000])
print("ローレンツ例 累積比率", L.round(3).tolist(), "面積", round(area, 4), "ジニ", round(g, 4))

# 演習: ジニ係数(4 世帯)
L, area, g = gini([100, 100, 300, 500])
print("演習ジニ 累積比率", L.round(3).tolist(), "台形", ((L[:-1] + L[1:]) / 2).round(3).tolist(), "面積", round(area, 4), "ジニ", round(g, 4))

# 演習: 3 本のローレンツ曲線(図に使う所得分布)のジニ係数
groups = {
    "A": [300, 320, 340, 350, 360, 380, 400, 420, 440, 460],
    "B": [100, 150, 200, 250, 300, 350, 400, 500, 650, 900],
    "C": [20, 30, 40, 50, 60, 80, 100, 150, 300, 1500],
}
for k, v in groups.items():
    print("曲線", k, "ジニ", round(gini(v)[2], 3))

# 解説: カイ二乗値(サイコロ 60 回)
o = np.array([8, 12, 9, 11, 6, 14])
e = np.full(6, 10)
print("サイコロ", ((o - e) ** 2 / e).tolist(), "合計", ((o - e) ** 2 / e).sum())

# 演習: カイ二乗値(4 カテゴリ、100 人)
o = np.array([30, 20, 25, 25])
e = np.full(4, 25)
print("演習カイ二乗", ((o - e) ** 2 / e).tolist(), "合計", ((o - e) ** 2 / e).sum())

# 演習: 歪度の符号(図に使う分布)
rng = np.random.default_rng(5)
shape = {"A": rng.normal(50, 10, 2000), "B": 100 - rng.gamma(2, 8, 2000), "C": rng.gamma(2, 8, 2000)}
for k, v in shape.items():
    print("歪度の符号", k, round(stats.skew(v), 2))
