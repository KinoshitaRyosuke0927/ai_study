"""単元7(クロス集計)の解説・演習に使う数値を計算して確かめる。"""
import pandas as pd

# 解説: 地域 × 住居のクロス表(households.csv)
hh = pd.read_csv("households.csv")
order = ["北日本", "関東", "中部", "近畿", "西日本"]
ct = pd.crosstab(hh["region"], hh["housing"], margins=True, margins_name="計").reindex(order + ["計"])
print(ct.to_string())
print((pd.crosstab(hh["region"], hh["housing"], normalize="index") * 100).reindex(order).round(1).to_string())
print((pd.crosstab(hh["region"], hh["housing"], normalize="columns") * 100).reindex(order).round(1).to_string())
print("全体の持ち家率", round((hh["housing"] == "持ち家").mean() * 100, 1))
# 解説: 満足度の度数表
sat = hh["satisfaction"].value_counts().sort_index()
print(pd.DataFrame({"度数": sat, "相対度数": (sat / sat.sum()).round(3), "累積相対度数": (sat / sat.sum()).cumsum().round(3)}).to_string())
# 解説: 独立なときの期待度数(関東 × 持ち家)
print("期待度数 関東×持ち家", 67 * 111 / 200)

# 演習1・2: 性別 × 購入
t = pd.DataFrame({"あり": [12, 27], "なし": [28, 33]}, index=["男性", "女性"])
print("演習 男性購入率", 12 / 40, "女性購入率", 27 / 60, "購入者のうち女性", round(27 / 39, 4), "全体のうち購入男性", 12 / 100)
# 演習4: 店舗別の満足度(帯グラフ)
stores = {"P": (200, [50, 30, 20]), "Q": (50, [30, 40, 30]), "R": (100, [60, 25, 15])}
for k, (n, p) in stores.items():
    print("演習4", k, "人数", [n * x // 100 for x in p])
# 演習5: 期待度数
print("演習5", 80 * 60 / 200)
