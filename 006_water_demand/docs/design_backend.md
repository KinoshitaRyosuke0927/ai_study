# バックエンド処理 詳細設計書

## 概要

本設計書は `app.py` に実装されているバックエンド処理のうち、  
**気象情報取得処理**（`design_weather_service.md` 参照）と  
**予測モデル処理**（`design_model.md` 参照）を除いたAPIエンドポイントについて記述する。

- **フレームワーク：** FastAPI
- **テンプレートエンジン：** Jinja2
- **データ永続化：** CSVファイル（インメモリDB等は未使用）

---

## システム構成

```
クライアント（ブラウザ）
    │
    │ HTTP
    ▼
FastAPI アプリケーション (app.py)
    │
    ├── Jinja2テンプレート（templates/）
    │       ├── menu.html
    │       ├── water_demand.html
    │       ├── work_day.html
    │       └── predict.html
    │
    └── CSVデータストア（train_data/）
            ├── water_demand.csv      ← 注文量実績
            ├── work_day.csv          ← 出社カレンダー
            ├── jbd_calendar.csv      ← 営業日カレンダー
            └── weather_data.csv      ← 気象データ
```

---

## 定数定義

| 定数名 | 値（相対パス） | 説明 |
|--------|--------------|------|
| `BASE_DIR` | `app.py` のあるディレクトリ | ベースディレクトリ |
| `DATA_PATH` | `train_data/water_demand.csv` | 注文量実績CSVパス |
| `WORK_DAY_PATH` | `train_data/work_day.csv` | 出社カレンダーCSVパス |
| `JBD_CALENDAR_PATH` | `train_data/jbd_calendar.csv` | 営業日カレンダーCSVパス |
| `WEATHER_DATA_PATH` | `train_data/weather_data.csv` | 気象データCSVパス |

---

## エンドポイント一覧

| メソッド | パス | 概要 | レスポンス形式 |
|----------|------|------|----------------|
| GET | `/` | メニュー画面を返却 | HTML |
| GET | `/water_demand` | 注文量実績一覧画面を返却 | HTML |
| POST | `/water_demand/save` | 注文量実績をCSVに保存 | JSON |
| GET | `/work_day` | 出社状況登録画面を返却 | HTML |
| GET | `/work_day/data` | 指定社員の出社データを返却 | JSON |
| POST | `/work_day/save` | 出社データをCSVに保存 | JSON |
| GET | `/predict` | 注文量予測画面を返却 | HTML |
| GET | `/predict/data-info` | 使用データの参照期間・更新日時を返却 | JSON |
| POST | `/predict/run` | 注文量予測を実行して結果を返却 | JSON |
| POST | `/predict/update-weather` | 気象データを最新化 | JSON |
| POST | `/predict/register` | 予測結果を注文量実績として登録 | JSON |

---

## エンドポイント詳細

---

### GET `/`

#### 概要

メニュー画面（`menu.html`）を返却する。

#### 処理フロー

```
1. Jinja2テンプレート `menu.html` をレンダリング
2. HTMLレスポンスを返却
```

#### リクエスト

なし

#### レスポンス

`menu.html` のHTMLレスポンス

---

### GET `/water_demand`

#### 概要

`water_demand.csv` を読み込み、注文量実績一覧画面（`water_demand.html`）を返却する。

#### 処理フロー

```
1. water_demand.csv を読み込む
2. 各行のデータを整形
   - remaining_quantity が欠損（NaN）の場合は空文字 "" に変換
3. date_ym の降順にソート
4. Jinja2テンプレート water_demand.html にデータを渡してレンダリング
5. HTMLレスポンスを返却
```

#### テンプレートに渡す変数

| 変数名 | 型 | 内容 |
|--------|----|------|
| `rows` | list[dict] | 注文量実績の行データリスト（降順） |

`rows` の各要素：

| キー | 型 | 内容 |
|------|----|------|
| `date_ym` | string | 年月（CSV の生値：`YYYY/MM/DD`） |
| `order_quantity` | float | 注文量（L） |
| `remaining_quantity` | float or string | 残量（L）、欠損の場合は `""` |

---

### POST `/water_demand/save`

#### 概要

画面で編集した注文量実績の全行を受け取り、`water_demand.csv` を上書き保存する。

#### リクエストボディ（JSON）

```json
{
  "rows": [
    {
      "date_ym": "2025/04/01",
      "order_quantity": 60.0,
      "remaining_quantity": ""
    },
    ...
  ]
}
```

| フィールド | 型 | 内容 |
|------------|----|------|
| `rows` | array | 全行のデータ |
| `rows[].date_ym` | string | 年月（`YYYY/MM/DD`） |
| `rows[].order_quantity` | number | 注文量（L） |
| `rows[].remaining_quantity` | number or string | 残量（L）、空欄の場合は `""` |

#### 処理フロー

```
1. リクエストボディをJSONとして取得
2. rows の各要素を整形
   - remaining_quantity が "" の場合は None に変換
3. DataFrame に変換
4. water_demand.csv に上書き保存（index=False）
5. {"status": "ok"} を返却
```

#### レスポンス（JSON）

```json
{"status": "ok"}
```

---

### GET `/work_day`

#### 概要

出社状況登録画面（`work_day.html`）を返却する。

#### 処理フロー

```
1. work_day.csv を読み込む
2. date 列を datetime 型に変換
3. 登録期間（min_date, max_date）を "YYYY年MM月DD日" 形式で取得
4. emp_ で始まる列名（社員列）を抽出
5. Jinja2テンプレート work_day.html にデータを渡してレンダリング
6. HTMLレスポンスを返却
```

#### テンプレートに渡す変数

| 変数名 | 型 | 内容 |
|--------|----|------|
| `min_date` | string | カレンダーの最小日付（"YYYY年MM月DD日"） |
| `max_date` | string | カレンダーの最大日付（"YYYY年MM月DD日"） |
| `employees` | list[string] | 社員列名のリスト（例：`["emp_01", "emp_02", ...]`） |

---

### GET `/work_day/data`

#### 概要

指定された社員の日次出社データを辞書形式で返却する。

#### クエリパラメータ

| パラメータ名 | 型 | 必須 | 説明 |
|-------------|-----|------|------|
| `emp` | string | 必須 | 社員列名（例：`emp_01`） |

#### 処理フロー

```
1. work_day.csv を読み込む
2. date 列を datetime 型に変換
3. 指定された emp 列が存在しない場合 → 400エラーを返却
4. 全行について {日付文字列(YYYY-MM-DD): 出社フラグ(int)} の辞書を構築
5. JSONレスポンスとして返却
```

#### レスポンス（JSON）

```json
{
  "2024-10-01": 1,
  "2024-10-02": 0,
  ...
}
```

#### エラーレスポンス

| 条件 | ステータス | レスポンス |
|------|-----------|-----------|
| `emp` 列が存在しない | 400 | `{"error": "invalid employee"}` |

---

### POST `/work_day/save`

#### 概要

指定社員の出社データ変更内容を受け取り、`work_day.csv` を更新する。

#### リクエストボディ（JSON）

```json
{
  "emp": "emp_01",
  "data": {
    "2024-10-01": 1,
    "2024-10-02": 0,
    ...
  }
}
```

| フィールド | 型 | 内容 |
|------------|----|------|
| `emp` | string | 社員列名（例：`emp_01`） |
| `data` | object | 変更する日付と出社フラグの辞書 |

#### 処理フロー

```
1. リクエストボディをJSONとして取得
2. work_day.csv を読み込む
3. emp 列が存在しない場合 → 400エラーを返却
4. date 列を一時的に _parsed 列（datetime型）として作成
5. data の各エントリについて：
   - _parsed 列で日付を検索
   - 一致する行の emp 列を指定されたフラグ値（int）で更新
6. _parsed 列を削除
7. work_day.csv に上書き保存（index=False）
8. {"status": "ok"} を返却
```

#### レスポンス（JSON）

```json
{"status": "ok"}
```

#### エラーレスポンス

| 条件 | ステータス | レスポンス |
|------|-----------|-----------|
| `emp` 列が存在しない | 400 | `{"error": "invalid employee"}` |

---

### GET `/predict`

#### 概要

注文量予測画面（`predict.html`）を返却する。画面表示時に使用データ情報を取得してテンプレートに渡す。

#### 処理フロー

```
1. _data_source_info() を呼び出して使用データ情報を取得
2. Jinja2テンプレート predict.html にデータを渡してレンダリング
3. HTMLレスポンスを返却
```

#### テンプレートに渡す変数

| 変数名 | 型 | 内容 |
|--------|----|------|
| `info` | list[dict] | 使用データ情報のリスト |

`info` の各要素：

| キー | 型 | 内容 |
|------|----|------|
| `name` | string | データソース名 |
| `period` | string | 参照期間（例：「2024/10 〜 2025/06」） |
| `mtime` | string | ファイルの最終更新日時（例：「2025/06/01 12:00:00」） |

---

### GET `/predict/data-info`

#### 概要

予測に使用する4つのデータソースの参照期間とファイル更新日時を返却する。

#### 処理フロー（`_data_source_info()` 関数）

```
各CSVファイルについて以下を処理：

1. water_demand.csv
   - date_ym 列を datetime 型に変換
   - 最小・最大年月を "YYYY/MM" 形式で結合（例：「2025/04 〜 2025/10」）
   - ファイルの最終更新日時を取得

2. jbd_calendar.csv
   - date 列を datetime 型に変換
   - 最小・最大日付を "YYYY/MM/DD" 形式で結合
   - ファイルの最終更新日時を取得

3. work_day.csv
   - date 列を datetime 型に変換
   - 最小・最大日付を "YYYY/MM/DD" 形式で結合
   - ファイルの最終更新日時を取得

4. weather_data.csv
   - date 列を datetime 型に変換
   - 欠損行（dropna）を除外した上で最小・最大日付を "YYYY/MM/DD" 形式で結合
   - ファイルの最終更新日時を取得

返却値：上記4件を含むリスト（順序：水の注文量実績, JBD営業日カレンダー,
                              AIC出社カレンダー, 気候情報）
```

#### レスポンス（JSON）

```json
[
  {
    "name": "水の注文量実績",
    "period": "2025/04 〜 2025/10",
    "mtime": "2025/06/01 12:00:00"
  },
  {
    "name": "JBD営業日カレンダー",
    "period": "2024/10/01 〜 2025/10/31",
    "mtime": "2025/05/01 09:00:00"
  },
  {
    "name": "AIC出社カレンダー",
    "period": "2024/10/01 〜 2025/10/31",
    "mtime": "2025/06/01 10:00:00"
  },
  {
    "name": "気候情報",
    "period": "2024/10/01 〜 2025/06/17",
    "mtime": "2025/06/18 08:30:00"
  }
]
```

---

### POST `/predict/run`

#### 概要

翌月の注文量をRidge回帰で予測し、結果を返却する。  
詳細は `design_model.md` を参照。

---

### POST `/predict/update-weather`

#### 概要

Meteostat APIから気象データを取得し `weather_data.csv` に上書き保存する。  
詳細は `design_weather_service.md` を参照。

---

### POST `/predict/register`

#### 概要

予測画面で算出した推奨注文量を `water_demand.csv` に新規行として追加登録する。

#### リクエストボディ（JSON）

```json
{
  "date_ym": "2025/11/01",
  "order_quantity": 80
}
```

| フィールド | 型 | 内容 |
|------------|----|------|
| `date_ym` | string | 年月（`YYYY/MM/DD`形式） |
| `order_quantity` | number | 推奨注文量（L） |

#### 処理フロー

```
1. リクエストボディをJSONとして取得
2. water_demand.csv を読み込む
3. 新規行を作成
   - date_ym: リクエストの date_ym
   - order_quantity: リクエストの order_quantity
   - remaining_quantity: None（空欄）
4. 既存DataFrameに新規行を concat
5. water_demand.csv に上書き保存（index=False）
6. {"status": "ok"} を返却
```

#### レスポンス（JSON）

```json
{"status": "ok"}
```

---

## データ管理方針

| 項目 | 内容 |
|------|------|
| データストア | CSVファイル（DBは未使用） |
| 書き込み方式 | 全件上書き（インクリメンタル更新なし） |
| 並行制御 | なし（シングルユーザー利用を前提） |
| バックアップ | なし（必要に応じて手動バックアップ） |

## 依存パッケージ

| パッケージ | 用途 |
|------------|------|
| `fastapi` | Webフレームワーク |
| `uvicorn` | ASGIサーバー |
| `jinja2` | HTMLテンプレートエンジン |
| `pandas` | CSVの読み書き・データ加工 |
| `numpy` | 20L単位切り上げ計算（`np.ceil`） |
| `scikit-learn` | Ridge回帰・LOO-CV |
| `python-dotenv` | `.env`ファイルから環境変数を読み込む |
| `requests` | 気象データAPIのHTTPリクエスト |
