### Overview
#### 目的
AICで毎月購入しているウォーターサーバーの水の注文量を予測したい

#### 情報
- 20L単位で注文する
- n-1月中にn+1月の分量を注文して, n月25日にn+1月分の水が届く
- 当月の残りは翌月に消費
- AIC所在地
    緯度(lat) : 35.698568
    経度(lon) : 139.779358

#### 精度向上に向けて
**現在のモデルが抱える不確実性の原因**
- 翌月の気温が不明
- 翌月の出勤状況が不明

**精度向上に寄与すると考えられるデータ**
- 最も効果が見込める：翌月の気温予報
    現在は「前年同月の実績」で代替しており, 年ごとの気候変動が拾えていない. 気象庁や天気予報APIから翌月の予測気温を取得できれば, 最も直接的な改善になりそう
- 効果が見込める : AICの平均湿度[%]
    現在のAPIでは湿度のデータが取得できないので予測に使用していないが, 水の消費量に影響ありそう

---

### Data Description
<span style="color: red; ">赤字部分</span>は今後取得して予測に使用したいデータ

#### water_demand.csv
各月ごとの水の注文量の実績値

| 列名 | 概要 |
| --- | --- |
| date_ym | 年月 |
| order_quantity | その月に注文した水の量[L] |
| <span style="color: red; ">rest_quantity</span> | <span style="color: red; ">その月に残った水の量[L]</span> |

#### jbd_calendar.csv
JBDの営業日カレンダー

| 列名 | 概要 |
| --- | --- |
| date | 年月日 |
| business_day_flag | 会社が営業している場合は1, 休業日は0 |

#### work_day.csv
社員ごとのウォーターサーバーが置いてある事務所(AIC)での業務カレンダー

| 列名 | 概要 |
| --- | --- |
| date | 年月日 |
| emp_nn | その社員がAICで業務している場合は1, 休暇や在宅勤務, 出張などでAICに不在の場合は0 |

#### weather_data.csv
[お天気API](https://dev.meteostat.net/api/point/daily)より取得した事務所(AIC)の気候データ

| 列名 | 概要 |
| --- | --- |
| date | 年月日 |
| tavg | 平均気温[℃] |
| tmin | 最低気温[℃] |
| tmax | 最高気温[℃] |
| <span style="color: red; ">havg</span> | <span style="color: red; ">平均湿度[%]</span> |
