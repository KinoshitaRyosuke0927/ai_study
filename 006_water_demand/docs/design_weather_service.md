# 気象情報取得処理 設計書

## 概要

AIC（オフィス）所在地の日次気象データを外部API（Meteostat via RapidAPI）から取得し、
`weather_data.csv` に保存する処理の設計書。

- **実装ファイル：** `weather_data_service.py`
- **呼び出し元：** `app.py` の `update_weather()` 関数（`POST /predict/update-weather` エンドポイント）

---

## 外部API仕様

### サービス概要

| 項目 | 内容 |
|------|------|
| APIサービス名 | Meteostat（RapidAPI 経由） |
| APIドキュメント | https://dev.meteostat.net/api/point/daily |
| RapidAPIホスト | `meteostat.p.rapidapi.com` |
| エンドポイント | `https://meteostat.p.rapidapi.com/point/daily` |
| HTTPメソッド | GET |
| 認証方式 | RapidAPI APIキー（リクエストヘッダー） |
| 取得上限 | 1回のリクエストで最大10年分 |
| 利用上限 | 500回/月 |

### リクエスト仕様

**クエリパラメータ**

| パラメータ名 | 型 | 必須 | 値 | 説明 |
|-------------|-----|------|----|------|
| `lat` | float | 必須 | `35.698568` | AICの緯度（固定値） |
| `lon` | float | 必須 | `139.779358` | AICの経度（固定値） |
| `start` | string | 必須 | `YYYY-MM-DD` | 取得開始日 |
| `end` | string | 必須 | `YYYY-MM-DD` | 取得終了日 |

**リクエストヘッダー**

| ヘッダー名 | 値 |
|-----------|----|
| `x-rapidapi-host` | `meteostat.p.rapidapi.com` |
| `x-rapidapi-key` | 環境変数 `RAPIDAPI_KEY` の値 |

**リクエスト例**

```
GET https://meteostat.p.rapidapi.com/point/daily
    ?lat=35.698568
    &lon=139.779358
    &start=2024-10-01
    &end=2025-06-18

x-rapidapi-host: meteostat.p.rapidapi.com
x-rapidapi-key: <RAPIDAPI_KEY>
```

### レスポンス仕様

**レスポンスボディ（JSON）**

```json
{
  "data": [
    {
      "date":  "2024-10-01",
      "tavg":  23.1,
      "tmin":  20.0,
      "tmax":  26.2,
      "prcp":  null,
      "snow":  null,
      "wdir":  null,
      "wspd":  null,
      "wpgt":  null,
      "pres":  null,
      "tsun":  null
    },
    ...
  ]
}
```

**レスポンスフィールド一覧（`data` 配列の各要素）**

| フィールド | 単位 | 内容 |
|------------|------|------|
| `date` | - | 日付（YYYY-MM-DD） |
| `tavg` | ℃ | 平均気温 |
| `tmin` | ℃ | 最低気温 |
| `tmax` | ℃ | 最高気温 |
| `prcp` | mm | 降水量 |
| `snow` | mm | 積雪深 |
| `wdir` | ° | 平均風向 |
| `wspd` | km/h | 平均風速 |
| `wpgt` | km/h | 最大瞬間風速 |
| `pres` | hPa | 海面気圧 |
| `tsun` | 分 | 日照時間 |

> 本システムでは `date`, `tavg`, `tmin`, `tmax` のみ使用する。他フィールドは取捨される。

---

## 関数仕様

### `get_daily_weather`

```python
def get_daily_weather(
    start_date: datetime.datetime,
    end_date: datetime.datetime
) -> pd.DataFrame
```

**引数**

| 引数 | 型 | 説明 |
|------|----|------|
| `start_date` | `datetime.datetime` | 取得開始日 |
| `end_date` | `datetime.datetime` | 取得終了日 |

**戻り値**

| 列名 | 型 | 内容 |
|------|----|------|
| `date` | `datetime64[ns]` | 日付 |
| `tavg` | `float` | 平均気温（℃） |
| `tmin` | `float` | 最低気温（℃） |
| `tmax` | `float` | 最高気温（℃） |

データが0件の場合は空のDataFrame（同一スキーマ）を返却する。

**例外**

| 例外 | 発生条件 |
|------|----------|
| `EnvironmentError` | 環境変数 `RAPIDAPI_KEY` が未設定 |
| `requests.HTTPError` | HTTPリクエストが4xx/5xxで失敗（`raise_for_status()`による） |

---

## 処理フロー

```
1. 環境変数 RAPIDAPI_KEY を取得
   └── 未設定の場合 → EnvironmentError を送出

2. 日付を文字列（YYYY-MM-DD）に変換

3. クエリパラメータ・リクエストヘッダーを構築

4. GET リクエスト送信（タイムアウト: 10秒）
   └── HTTPエラーの場合 → raise_for_status() でエラーを送出

5. レスポンスボディをJSONとしてパース
   `data` キーのリストを取得

6. データが0件の場合 → 空のDataFrameを返却

7. `date`, `tavg`, `tmin`, `tmax` のみ抽出

8. `date` 列を datetime64[ns] 型に変換

9. DataFrameを返却
```

---

## 呼び出し元との連携（`app.py`）

### エンドポイント

```
POST /predict/update-weather
```

### 呼び出し時の設定値

| 項目 | 値 | 説明 |
|------|----|------|
| 取得開始日 | `2024-10-01`（固定） | システム稼働開始日 |
| 取得終了日 | 実行時点の当日 (`datetime.now()`) | 常に最新日まで取得 |
| 保存先 | `train_data/weather_data.csv` | 既存ファイルを上書き |

### エラーハンドリング

| 例外 | HTTPステータス | レスポンス |
|------|----------------|-----------|
| `EnvironmentError` | 400 | `{"error": "環境変数 RAPIDAPI_KEY が設定されていません。"}` |
| その他の例外 | 500 | `{"error": "データ取得に失敗しました: {例外メッセージ}"}` |

---

## 環境変数

| 変数名 | 説明 | 設定方法 |
|--------|------|----------|
| `RAPIDAPI_KEY` | Meteostat APIのRapidAPIキー | `.env` ファイルに記載（`python-dotenv` で読み込み） |

### `.env` ファイルの設定例

```
RAPIDAPI_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

> `.env` ファイルはプロジェクトルート（`006_water_demand/` の親ディレクトリ）に配置する。

---

## 出力データ（`weather_data.csv`）

| 列名 | 型 | 内容 |
|------|----|------|
| `date` | datetime64[ns]（保存時は文字列） | 年月日（YYYY-MM-DD） |
| `tavg` | float | 平均気温（℃）|
| `tmin` | float | 最低気温（℃）|
| `tmax` | float | 最高気温（℃）|

**サンプル**

```
date,tavg,tmin,tmax
2024-10-01,23.1,20.0,26.2
2024-10-02,26.3,22.2,31.7
2024-10-03,23.2,21.8,25.1
```

---

## 注意事項・制約

| 項目 | 内容 |
|------|------|
| 利用制限 | APIリクエスト上限は **500回/月**。毎月の予測前に1回実行するユースケースであれば問題ない。 |
| データの欠損 | APIレスポンスの各フィールドは `null` になる場合がある。月次平均気温の計算時に `dropna()` で欠損行は除外される。 |
| 上書き保存 | 実行のたびに `weather_data.csv` を全件上書きする。差分更新は行わない。 |
| タイムアウト | HTTPリクエストのタイムアウトは10秒に設定。 |
