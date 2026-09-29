# デモ環境への DB 移行

このフォルダのファイルで、別の環境に AI学習ポータルの DB を作り、作成時点のデータを登録できます。

| ファイル | 内容 |
|---|---|
| `01_create_database.sql` | データベース `ai_learning_portal` と接続ユーザ `ai_learning_portal` の作成 |
| `02_schema_and_data.sql` | 全テーブルの定義と、作成時点の全データ(既存のテーブルは作り直す) |
| `setup_db.ps1` | 上の 2 つをまとめて実行する(Windows PowerShell) |
| `setup_db.sh` | 上の 2 つをまとめて実行する(macOS / Linux / Git Bash) |

### 含まれるデータ

- ユーザ 2名(下表。デモ用のサンプルユーザ)
- 講座「統計の基礎」:5単元・演習6問・データファイル `scores.csv`
- Alembic の版数:取り込み後に `alembic upgrade head` を実行しても何も変わりません。

### デモ用のサンプルユーザ

| ログイン名 | パスワード | 表示名 | 権限 |
|---|---|---|---|
| `admin` | `WrDuo__3d_7p` | 管理者 | 管理者 |
| `learner01` | `dldtpnm7N2L4` | 受講者 01 | 受講者 |

デモ用のアカウントです。部署メンバーに公開する環境で使い続ける場合は、`backend/` で
`python -m app.cli set-password --login admin` を実行してパスワードを変更してください。

## 手順

必要なもの:MySQL 8、Python 3.12、Node.js 22(アプリのソース一式をデモ環境にコピーしておく)。

### 1. DB を作成してデータを登録する

**Windows**(`db/` フォルダで実行)

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_db.ps1
```

**macOS / Linux**(`db/` フォルダで実行)

```bash
bash setup_db.sh
```

MySQL 管理者(root)のパスワードと、新しく作る接続ユーザのパスワードを聞かれます。
接続先を変える場合は `setup_db.ps1 -MysqlHost <ホスト> -Port <ポート> -RootUser <ユーザ>`、
`setup_db.sh` は環境変数 `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_ROOT_USER` で指定します。

スクリプトを使わずに手で実行する場合:

```bash
# 01_create_database.sql の 'CHANGE_ME' を接続ユーザのパスワードに書き換えてから
mysql -u root -p < 01_create_database.sql
mysql -u root -p --default-character-set=utf8mb4 ai_learning_portal < 02_schema_and_data.sql
```

### 2. アプリを設定して起動する

```bash
cd ../backend
python -m venv .venv
.venv\Scripts\activate                 # macOS / Linux は source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                   # MYSQL_PASSWORD(手順1の接続ユーザのパスワード)と APP_SECRET_KEY を設定

cd ../frontend && npm install && npm run build
cd ../backend && uvicorn app.main:app --port 8016
```

ブラウザで http://localhost:8016 を開き、上の「デモ用のサンプルユーザ」でログインします。

## 注意

- `02_schema_and_data.sql` は **既存のテーブルを削除して作り直します**。デモ環境で受講した記録も消えるため、再実行するときは注意してください。
- 接続ユーザは `'ai_learning_portal'@'localhost'` で作成します。アプリと DB が別のサーバの場合は、`localhost` を接続元のホストに変えてください。
- ブラウザ内の Python は CDN(cdn.jsdelivr.net)から読み込むため、デモ環境のブラウザはインターネットに接続できる必要があります。

## データを最新にし直す(作成元の環境で実行)

作成元の DB の内容で `02_schema_and_data.sql` を作り直す場合:

```bash
mysqldump -u root -p --single-transaction --hex-blob --set-gtid-purged=OFF --no-tablespaces \
  --default-character-set=utf8mb4 --skip-dump-date \
  --result-file=02_schema_and_data.sql ai_learning_portal
```
