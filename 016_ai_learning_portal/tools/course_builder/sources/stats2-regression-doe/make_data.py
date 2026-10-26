"""図と統計ソフトの出力の材料のデータを作る(架空のデータ)。

- flats.csv : 中古マンション 40 件の価格(万円)・広さ(m²)・築年数(年)。
              広い物件ほど築年数が古い傾向があり、単回帰と重回帰で築年数の係数の符号が変わる。
"""
import numpy as np
import pandas as pd

rng = np.random.default_rng(7)
n = 40
age = rng.uniform(2, 35, n).round()
area = (45 + 1.2 * age + rng.normal(0, 8, n)).round(1)
price = (800 + 45 * area - 40 * age + rng.normal(0, 250, n)).round(-1)
pd.DataFrame({"price": price, "area": area, "age": age.astype(int)}).to_csv("flats.csv", index=False)
print("saved flats.csv")
