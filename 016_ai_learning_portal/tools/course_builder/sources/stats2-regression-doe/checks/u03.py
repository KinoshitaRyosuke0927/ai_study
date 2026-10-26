"""単元3(重回帰)の解説・演習に使う数値を計算して確かめる。"""
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

df = pd.read_csv("flats.csv")
print(df.describe().round(2))
print("相関\n", df.corr().round(3))
for f in ("price ~ age", "price ~ area", "price ~ area + age"):
    m = smf.ols(f, df).fit()
    print("=====", f)
    print(m.summary2().tables[1].round(4))
    if f.endswith("+ age"):
        print("予測 広さ70 築20", round(m.predict(pd.DataFrame({"area": [70], "age": [20]}))[0], 2))
    print("R2", round(m.rsquared, 4), "adjR2", round(m.rsquared_adj, 4), "F", round(m.fvalue, 3), "p", m.f_pvalue, "s", round(m.mse_resid ** 0.5, 2), "df_resid", m.df_resid)
print("t0.025(37)", round(stats.t.ppf(0.975, 37), 3))
