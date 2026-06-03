# ウォーターサーバー注文量予測アプリケーション

AICで毎月購入しているウォーターサーバーの水の注文量を予測するWebアプリケーションです。

## 前提条件

- Python 3.10 以上
- 気象データ取得用の RapidAPI キー（Meteostat API）

## セットアップ

### 1. 仮想環境の作成・有効化(任意)

```bash
cd water_demand
python -m venv .venv

# Windows
.venv\Scripts\activate
```

### 2. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 3. 環境変数の設定

気象データの取得に RapidAPI キーが必要です。`.env` ファイルをwater_demandと同じ階層に作成して以下の内容を記載してください。

```
RAPIDAPI_KEY=01f09bdb75msh84d979f8fb9caa1p1b192djsn48334b98456f
```

## アプリケーションの起動

```bash
uvicorn app:app --reload
```

起動後、ブラウザで http://127.0.0.1:8000 にアクセスするとメニュー画面が表示されます。

## 主な機能

| パス | 機能 |
| --- | --- |
| `/` | メニュー画面 |
| `/water_demand` | 水の注文量実績の登録・閲覧 |
| `/work_day` | 社員の出社状況の登録 |
| `/predict` | 注文量の予測 |

## ディレクトリ構成

```
water_demand/
├── app.py                  # FastAPI アプリケーション本体
├── water_demand_model.py   # 予測モデル
├── weather_data_service.py # 気象データ取得サービス
├── requirements.txt        # 依存パッケージ一覧
├── templates/              # HTMLテンプレート
│   ├── menu.html
│   ├── predict.html
│   ├── water_demand.html
│   └── work_day.html
└── train_data/             # 学習・実績データ
    ├── water_demand.csv
    ├── work_day.csv
    ├── jbd_calendar.csv
    └── weather_data.csv
.env                        # 環境変数
```
