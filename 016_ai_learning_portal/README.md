# AI学習ポータル

部署メンバーがデータサイエンスを学ぶための、部署内の学習サービスです。
講座は単元ごとに「概念の説明」と「ブラウザ内で Python を実行するハンズオン(Colab 風のセル)」で構成され、
演習は自動で採点されます。

- 仕様・決定事項・開発フェーズ:[docs/spec.md](docs/spec.md)
- 講座ノートブックの書き方:[docs/notebook-format.md](docs/notebook-format.md)

現在は **フェーズ1(受講の土台)** まで実装済みです。

## 構成

```
016_ai_learning_portal/
  backend/            FastAPI(Python 3.12)
    app/              アプリ本体(models / services / routers / cli)
    alembic/          DB マイグレーション
    tests/            pytest
  frontend/           React + TypeScript(Vite)
    src/python/       ブラウザ内 Python(Pyodide を動かす Web Worker)
  content/            講座データ(course.json + .ipynb)
  db/                 デモ環境への DB 移行用(DB 作成 SQL・データ入りダンプ・セットアップスクリプト)
  docs/               仕様書など
  Dockerfile          Azure 向けコンテナイメージ
```

## ローカルでの起動

必要なもの:Python 3.12、Node.js 22、MySQL 8。

> 別の環境で、現在のデータ入りの DB を用意してデモする場合は [db/README.md](db/README.md) を参照してください
> (以下の手順 1 と、手順 2 の `alembic upgrade head`・ユーザ作成・講座取り込みが不要になります)。

### 1. データベース(初回のみ)

```sql
CREATE DATABASE ai_learning_portal CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER 'ai_learning_portal'@'localhost' IDENTIFIED BY '<パスワード>';
GRANT ALL PRIVILEGES ON ai_learning_portal.* TO 'ai_learning_portal'@'localhost';
```

### 2. バックエンド(`backend/` で実行)

```bash
python -m venv .venv
.venv\Scripts\activate                 # Git Bash なら source .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env                   # MYSQL_PASSWORD と APP_SECRET_KEY を設定する
alembic upgrade head                   # テーブル作成

# ユーザ作成と講座の取り込み
python -m app.cli create-user --login admin --name "管理者" --admin
python -m app.cli import-course ../content/statistics-basics --author admin
```

### 3. フロントエンドをビルドして起動

```bash
cd ../frontend && npm install && npm run build   # frontend/dist ができる
cd ../backend && uvicorn app.main:app --port 8016
```

ブラウザで http://localhost:8016 を開いてログインします。

### 画面を修正しながら開発する場合

バックエンド(`uvicorn app.main:app --reload --port 8016`)に加えて、`frontend/` で `npm run dev` を実行し、
http://localhost:5173 を開きます(`/api` はバックエンドへ転送されます)。

## 管理用コマンド(`backend/` で実行)

| コマンド | 内容 |
|---|---|
| `python -m app.cli create-user --login <名前> --name <表示名> [--admin]` | ユーザ作成(パスワードは対話入力) |
| `python -m app.cli set-password --login <名前>` | パスワード変更 |
| `python -m app.cli delete-user --login <名前>` | ユーザ削除(受講記録も削除) |
| `python -m app.cli import-course <講座フォルダ> [--author <名前>] [--replace]` | 講座の取り込み。`--replace` は既存講座を置き換える(**受講記録も削除される**) |

## テスト

```bash
cd backend && python -m pytest
```

テストは SQLite のインメモリ DB で動くため、MySQL は不要です。

## ブラウザ内 Python(Pyodide)について

- 既定では Pyodide を jsDelivr の CDN から読み込みます。ローカルでの確認も、インターネットに接続できれば問題なく動きます。
- 初回の実行時に Pyodide 本体と pandas などをダウンロードするため、10 秒前後かかります。2回目以降はブラウザのキャッシュが効きます。
- インターネットに出られない環境や、外部 CDN に依存したくない場合は、Pyodide 一式(`pyodide-314.0.7.tar.bz2`)を
  社内から配信できる場所に置き、`.env` の `PYODIDE_BASE_URL` をその URL に変更してください(ビルドのやり直しは不要)。
- Pyodide 314 系はクラシック Web Worker に対応していないため、モジュール Worker で `pyodide.mjs` を読み込んでいます。

## Azure へのデプロイ(想定)

1. Azure Database for MySQL(フレキシブル サーバー)に DB とユーザを作成する。
2. `docker build -t ai-learning-portal .` でイメージを作り、Azure Container Registry に登録する。
3. App Service(コンテナ)または Container Apps で起動し、アプリ設定に次を登録する。
   - `APP_ENV=azure`、`APP_SECRET_KEY`(長いランダム文字列)
   - `MYSQL_HOST` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE`
   - `MYSQL_SSL_CA=/etc/ssl/certs/ca-certificates.crt`(TLS 接続)
4. アクセス制限(IP 制限)で部署のネットワークからのみ接続できるようにする。

コンテナは起動時に `alembic upgrade head` を実行してから、アプリを起動します。
