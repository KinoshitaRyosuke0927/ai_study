"""
https://www.kaggle.com/competitions/rossmann-store-sales/overview
Rossmann Store Sales - EDA
目的: 精度向上に必要な情報をログに出力する
"""
import pandas as pd
import numpy as np
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "competitions" / "rossmann-store-sales"

# ── データ読み込み ─────────────────────────────────────────────
print("=" * 60)
print("【1】データ読み込み & 基本情報")
print("=" * 60)

train = pd.read_csv(DATA_DIR / "train.csv", low_memory=False, parse_dates=["Date"])
test  = pd.read_csv(DATA_DIR / "test.csv",  low_memory=False, parse_dates=["Date"])
store = pd.read_csv(DATA_DIR / "store.csv")

print(f"train shape : {train.shape}")
print(f"test  shape : {test.shape}")
print(f"store shape : {store.shape}")
print(f"train 期間  : {train.Date.min().date()} ~ {train.Date.max().date()}")
print(f"test  期間  : {test.Date.min().date()} ~ {test.Date.max().date()}")
print(f"店舗数 (train) : {train.Store.nunique()}")
print(f"店舗数 (test)  : {test.Store.nunique()}")

# ── データ結合 ────────────────────────────────────────────────
train = train.merge(store, on="Store", how="left")
test  = test.merge(store,  on="Store", how="left")

# ── 欠損値 ───────────────────────────────────────────────────
print("\n" + "=" * 60)
print("【2】欠損値分析")
print("=" * 60)

print("\n--- train + store 結合後の欠損 ---")
null_info = train.isnull().sum()
null_info = null_info[null_info > 0]
for col, cnt in null_info.items():
    print(f"  {col:35s}: {cnt:6,} ({cnt/len(train)*100:.2f}%)")

print("\n--- test + store 結合後の欠損 ---")
null_test = test.isnull().sum()
null_test = null_test[null_test > 0]
for col, cnt in null_test.items():
    print(f"  {col:35s}: {cnt:6,} ({cnt/len(test)*100:.2f}%)")

# Open 列の欠損（test のみ）
open_null = test["Open"].isnull().sum()
print(f"\n  [注意] test の Open 欠損: {open_null} 件 → 開店日と仮定して 1 を補完するのが定番")

# ── 目的変数 Sales の分布 ────────────────────────────────────
print("\n" + "=" * 60)
print("【3】目的変数 Sales の分布")
print("=" * 60)

open_train = train[train.Open == 1]
closed_train = train[train.Open == 0]

print(f"\n全 train 行数         : {len(train):,}")
print(f"  Open=1（開店日）    : {len(open_train):,} ({len(open_train)/len(train)*100:.1f}%)")
print(f"  Open=0（閉店日）    : {len(closed_train):,} ({len(closed_train)/len(train)*100:.1f}%)")
print(f"  Sales=0 のうち Open=1: {((train.Sales==0) & (train.Open==1)).sum()} 件 (異常値候補)")

print(f"\n開店日の Sales 統計:")
s = open_train["Sales"]
print(f"  mean   : {s.mean():,.1f}")
print(f"  median : {s.median():,.1f}")
print(f"  std    : {s.std():,.1f}")
print(f"  min    : {s.min():,.1f}")
print(f"  25%    : {s.quantile(0.25):,.1f}")
print(f"  75%    : {s.quantile(0.75):,.1f}")
print(f"  max    : {s.max():,.1f}")
print(f"  歪度   : {s.skew():.3f}  (正の歪み → log変換が有効な可能性)")

print(f"\nlog(Sales+1) 統計:")
ls = np.log1p(open_train["Sales"])
print(f"  mean   : {ls.mean():.4f}")
print(f"  std    : {ls.std():.4f}")
print(f"  skew   : {ls.skew():.4f}  (絶対値が小さいほど正規分布に近い)")

# ── 曜日パターン ──────────────────────────────────────────────
print("\n" + "=" * 60)
print("【4】曜日別 Sales パターン（開店日のみ）")
print("=" * 60)

dow_map = {1:"月", 2:"火", 3:"水", 4:"木", 5:"金", 6:"土", 7:"日"}
dow_stats = open_train.groupby("DayOfWeek")["Sales"].agg(["mean","median","count"])
dow_stats.index = dow_stats.index.map(dow_map)
print(dow_stats.round(0).to_string())
print("\n  [ヒント] 日曜は閉店が多い → DayOfWeek は強力な特徴量")

# ── 月・年パターン ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("【5】月別・年別 Sales パターン")
print("=" * 60)

open_train = open_train.copy()
open_train["Month"] = open_train["Date"].dt.month
open_train["Year"]  = open_train["Date"].dt.year
open_train["Week"]  = open_train["Date"].dt.isocalendar().week.astype(int)

print("\n--- 月別平均 Sales ---")
month_stats = open_train.groupby("Month")["Sales"].mean().round(0)
for m, v in month_stats.items():
    bar = "█" * int(v / 500)
    print(f"  {m:2d}月: {v:6.0f}  {bar}")

print("\n--- 年別平均 Sales ---")
year_stats = open_train.groupby("Year")["Sales"].agg(["mean","count"]).round(0)
print(year_stats.to_string())
print("  [ヒント] 年トレンドが存在する場合、時系列 CV が必要")

# ── プロモーション効果 ────────────────────────────────────────
print("\n" + "=" * 60)
print("【6】プロモーション効果")
print("=" * 60)

print("\n--- Promo（当日プロモ）の効果 ---")
promo_stats = open_train.groupby("Promo")["Sales"].agg(["mean","median","count"])
print(promo_stats.round(0).to_string())
promo_lift = (
    open_train[open_train.Promo==1]["Sales"].mean() /
    open_train[open_train.Promo==0]["Sales"].mean() - 1
) * 100
print(f"  Promo=1 の売上は Promo=0 より平均 {promo_lift:.1f}% 高い")

print("\n--- Promo2（継続プロモ参加店）の有無別 Sales ---")
promo2_stats = open_train.groupby("Promo2")["Sales"].agg(["mean","median","count"])
print(promo2_stats.round(0).to_string())

# Promo × Promo2 クロス集計
print("\n--- Promo × Promo2 クロス集計（平均 Sales）---")
cross = open_train.groupby(["Promo","Promo2"])["Sales"].mean().unstack().round(0)
print(cross.to_string())

# ── 祝日・学校休暇効果 ────────────────────────────────────────
print("\n" + "=" * 60)
print("【7】祝日・学校休暇の効果")
print("=" * 60)

print("\n--- StateHoliday 別 Sales（開店日のみ） ---")
sh_stats = open_train.groupby("StateHoliday")["Sales"].agg(["mean","median","count"])
sh_map = {"0":"なし", "a":"祝日", "b":"イースター", "c":"クリスマス"}
sh_stats.index = [sh_map.get(str(i), str(i)) for i in sh_stats.index]
print(sh_stats.round(0).to_string())

print("\n--- SchoolHoliday 別 Sales ---")
school_stats = open_train.groupby("SchoolHoliday")["Sales"].agg(["mean","median","count"])
print(school_stats.round(0).to_string())
school_lift = (
    open_train[open_train.SchoolHoliday==1]["Sales"].mean() /
    open_train[open_train.SchoolHoliday==0]["Sales"].mean() - 1
) * 100
print(f"  SchoolHoliday=1 の売上は 0 より平均 {school_lift:.1f}% {'高い' if school_lift > 0 else '低い'}")

# ── 店舗タイプ・品揃え ────────────────────────────────────────
print("\n" + "=" * 60)
print("【8】店舗タイプ・品揃え別 Sales")
print("=" * 60)

print("\n--- StoreType 別 Sales ---")
st_stats = open_train.groupby("StoreType")["Sales"].agg(["mean","median","std","count"])
print(st_stats.round(0).to_string())
print("  [ヒント] StoreType b は件数が少ないが高売上 → 強力な特徴量")

print("\n--- Assortment 別 Sales ---")
assort_stats = open_train.groupby("Assortment")["Sales"].agg(["mean","median","count"])
assort_map = {"a":"basic", "b":"extra", "c":"extended"}
assort_stats.index = [assort_map.get(i, i) for i in assort_stats.index]
print(assort_stats.round(0).to_string())

print("\n--- StoreType × Assortment クロス集計（平均 Sales）---")
cross2 = open_train.groupby(["StoreType","Assortment"])["Sales"].mean().unstack().round(0)
print(cross2.to_string())

# ── 競合距離 ─────────────────────────────────────────────────
print("\n" + "=" * 60)
print("【9】競合店との距離 (CompetitionDistance)")
print("=" * 60)

open_train["CompDist_bin"] = pd.cut(
    open_train["CompetitionDistance"].fillna(999999),
    bins=[0, 500, 1000, 2000, 5000, 10000, 999999],
    labels=["~500m","~1km","~2km","~5km","~10km","10km超"]
)
dist_stats = open_train.groupby("CompDist_bin", observed=True)["Sales"].agg(["mean","count"])
print(dist_stats.round(0).to_string())
print("  [ヒント] 近距離競合が多い店 → 売上が低い傾向を確認")
corr_dist = open_train[["CompetitionDistance","Sales"]].dropna().corr().iloc[0,1]
print(f"  CompetitionDistance と Sales の相関: {corr_dist:.4f}")

# ── 店舗別 Sales のばらつき ───────────────────────────────────
print("\n" + "=" * 60)
print("【10】店舗別 Sales のばらつき")
print("=" * 60)

store_stats = open_train.groupby("Store")["Sales"].agg(["mean","std","median"])
store_stats["cv"] = store_stats["std"] / store_stats["mean"]  # 変動係数

print(f"店舗別平均 Sales の統計:")
print(f"  min    : {store_stats['mean'].min():,.0f}")
print(f"  median : {store_stats['mean'].median():,.0f}")
print(f"  max    : {store_stats['mean'].max():,.0f}")
print(f"  std    : {store_stats['mean'].std():,.0f}")
print(f"\n店舗別 変動係数（CV = std/mean）の統計:")
print(f"  mean CV: {store_stats['cv'].mean():.3f}")
print(f"  max CV : {store_stats['cv'].max():.3f}")
print(f"\n上位10店舗（平均 Sales 降順）:")
print(store_stats.sort_values("mean", ascending=False).head(10).round(0).to_string())
print(f"\n下位10店舗（平均 Sales 昇順）:")
print(store_stats.sort_values("mean").head(10).round(0).to_string())
print("  [ヒント] 店舗 ID 自体、または店舗別の統計量が強力な特徴量になる")

# ── Customers との相関（リーク注意） ─────────────────────────
print("\n" + "=" * 60)
print("【11】Customers（来客数）との関係 ※テストデータに存在しない")
print("=" * 60)

corr_cust = open_train[["Customers","Sales"]].corr().iloc[0,1]
print(f"Customers と Sales の相関: {corr_cust:.4f}")
print("  [警告] Customers はテストデータに存在しない → 直接使用は不可")
print("  [ヒント] 店舗別の過去平均来客数は特徴量として使える可能性あり")

# ── 特徴量と Sales の相関 ─────────────────────────────────────
print("\n" + "=" * 60)
print("【12】数値特徴量と Sales の相関（開店日のみ）")
print("=" * 60)

num_cols = ["DayOfWeek","Promo","SchoolHoliday","Promo2",
            "CompetitionDistance","CompetitionOpenSinceMonth",
            "CompetitionOpenSinceYear","Promo2SinceWeek","Promo2SinceYear"]
corr_series = open_train[num_cols + ["Sales"]].corr()["Sales"].drop("Sales").sort_values(key=abs, ascending=False)
print(corr_series.round(4).to_string())

# ── 時系列構造の確認（CV 設計ヒント）────────────────────────
print("\n" + "=" * 60)
print("【13】時系列構造の確認（CV 設計のヒント）")
print("=" * 60)

print(f"\ntrain 期間: {train.Date.min().date()} ~ {train.Date.max().date()}")
print(f"test  期間: {test.Date.min().date()} ~ {test.Date.max().date()}")
print(f"予測ホライゾン: {(test.Date.max() - test.Date.min()).days + 1} 日間（約 6 週）")
print()

# 直近 6 週（test と同じ長さ）の期間を train から切り出す
cutoff = train.Date.max() - pd.Timedelta(weeks=6)
recent_val = open_train[open_train.Date > cutoff]
older_train = open_train[open_train.Date <= cutoff]
print(f"時系列バリデーション案:")
print(f"  学習: {older_train.Date.min().date()} ~ {older_train.Date.max().date()} ({len(older_train):,} 行)")
print(f"  検証: {recent_val.Date.min().date()} ~ {recent_val.Date.max().date()} ({len(recent_val):,} 行)")
print()
print("  [重要] 時系列データは StratifiedKFold を使うと未来→過去方向のリークが発生する")
print("  [重要] 代わりに TimeSeriesSplit または「直近N週を検証」とする単一 Hold-out が安全")
print("  [重要] ランダム分割は NG（翌日データが学習に入るとリークになる）")

# ── test に存在する store のチェック ─────────────────────────
print("\n" + "=" * 60)
print("【14】train / test の店舗カバレッジ")
print("=" * 60)

train_stores = set(train.Store.unique())
test_stores  = set(test.Store.unique())
only_in_train = train_stores - test_stores
only_in_test  = test_stores  - train_stores
print(f"train にのみ存在する店舗: {len(only_in_train)} 店舗")
print(f"test にのみ存在する店舗 : {len(only_in_test)} 店舗  ← これがあると未知店舗問題")
print(f"共通店舗                : {len(train_stores & test_stores)} 店舗")

# ── test の Open=NaN 確認 ─────────────────────────────────────
print("\n" + "=" * 60)
print("【15】test データの注意点")
print("=" * 60)

test_open_null = test["Open"].isnull()
print(f"test の Open=NaN: {test_open_null.sum()} 件")
if test_open_null.sum() > 0:
    nan_stores = test[test_open_null]["Store"].unique()
    print(f"  該当店舗: {sorted(nan_stores)}")
    print(f"  → train の同店舗・同曜日の Open 値で補完 or 1 で補完する")

# ── 週次トレンドの安定性チェック ─────────────────────────────
print("\n" + "=" * 60)
print("【16】週次売上トレンド（直近 26 週）")
print("=" * 60)

weekly = open_train.groupby(open_train.Date.dt.to_period("W"))["Sales"].mean().tail(26)
print(weekly.round(0).to_string())
print("  [ヒント] 直近トレンドが上昇・下降している場合、古いデータの重みを下げる工夫が有効")

# ── 特徴量エンジニアリング候補のまとめ ───────────────────────
print("\n" + "=" * 60)
print("【まとめ】特徴量エンジニアリング候補")
print("=" * 60)
print("""
■ 日付系（必須）
  - Year, Month, Day, DayOfWeek, WeekOfYear
  - DayOfMonth（月初・月末は売上が違う可能性）
  - IsWeekend（DayOfWeek >= 6）

■ 店舗別統計量（強力・要 CV-safe 計算）
  - 店舗別の過去平均 Sales（例: 6ヶ月平均）
  - 店舗 × 曜日別平均 Sales
  - 店舗 × 月別平均 Sales
  - 店舗別の Promo 効果の大きさ

■ プロモーション関連
  - Promo2 参加中かどうか（PromoInterval × 現在月で判定）
  - 競合店のオープンからの経過月数（CompetitionOpenSinceYear/Month → 経過期間）

■ 競合店距離
  - CompetitionDistance の log 変換（外れ値対策）
  - 欠損 → 大きな値（例: 999999 or 中央値）で補完

■ ラグ特徴量（時系列）
  - 同じ店舗の 1 年前同日 Sales（季節性のキャプチャ）
  - 同じ店舗の直近 7 日間の平均 Sales
  ※ リーク注意: 予測対象日より未来のデータを使わないこと

■ ターゲットエンコーディング
  - 店舗 ID を直接使う（LightGBM / CatBoost は可）
  - または Store × StoreType などのグループ統計量

■ log 変換（重要）
  - RMSPE で評価するため log(Sales+1) を目的変数にして学習
  - 予測後に exp(pred) - 1 で元のスケールに戻す
""")
