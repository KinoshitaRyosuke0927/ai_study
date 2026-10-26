"""単元3〜5(重回帰の演習、決定係数と F 検定、多重共線性とダミー変数)の数値を計算して確かめる。"""
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

T, F = stats.t, stats.f

# 単元3 の演習
print("u3 演習 予測 120 + 3.5*40 - 2.0*15", 120 + 3.5 * 40 - 2.0 * 15, "残差自由度 n=50 p=4", 50 - 4 - 1)
for name, coef, se in (("const", 52.0, 8.0), ("x1", 2.40, 0.60), ("x2", -0.90, 0.75)):
    tv = coef / se
    print("u3 演習の出力", name, "t", round(tv, 3), "p", round(2 * T.sf(abs(tv), 27), 4))
print("t0.025(27)", round(T.ppf(0.975, 27), 3))


# 単元4
def table(n, p, st, se):
    sr = st - se
    r2 = sr / st
    adj = 1 - (se / (n - p - 1)) / (st / (n - 1))
    f = (sr / p) / (se / (n - p - 1))
    return round(r2, 4), round(adj, 4), round(f, 3), "F0.05", round(F.ppf(0.95, p, n - p - 1), 3), "p", F.sf(f, p, n - p - 1)


print("u4 例 n=30 p=2 ST=500 SE=150", table(30, 2, 500, 150))
print("u4 演習 n=25 p=3 ST=800 SE=200", table(25, 3, 800, 200))
print("u4 演習 調整済み A(p=2,R2=.60) B(p=5,R2=.62) n=20", round(1 - 0.40 * 19 / 17, 4), round(1 - 0.38 * 19 / 14, 4))

# 単元5
df = pd.read_csv("flats.csv")
r2 = smf.ols("area ~ age", df).fit().rsquared
print("u5 例 広さを築年数で回帰した R2", round(r2, 4), "VIF", round(1 / (1 - r2), 3), "相関", round(df.area.corr(df.age), 3))
print("u5 例 R2=0.9 VIF", round(1 / (1 - 0.9), 4))
print("u5 演習 R2=0.8 VIF", round(1 / (1 - 0.8), 4), "VIF=20 R2", 1 - 1 / 20)
print("u5 例 ダミー 150+2.0*30+40", 150 + 2.0 * 30 + 40, "郊外", 150 + 2.0 * 30)
print("u5 演習 ダミー 200+5*10-20", 200 + 5 * 10 - 20)
print("u3 演習 t 6.3/1.8", round(6.3 / 1.8, 4), "t0.025(45)", round(T.ppf(0.975, 45), 3))
