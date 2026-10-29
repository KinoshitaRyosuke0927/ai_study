# DB の環境構築・復元

このフォルダのファイルで、AI学習ポータルの DB を作り、スナップショット(ある時点の全データ)を登録します。
次の 2 つの目的で使います。

- **新しい環境を作る**:講座・ユーザ・受講記録が入った状態で始める
- **DB のデータが消えたときに復元する**:スナップショットを作った時点の状態に戻す

> スナップショットは、Azure での管理(Azure Database for MySQL のバックアップ)に移行するまでの補助手段です。
> スナップショットを作った後に変わったデータは含まれません。

| ファイル | 内容 |
|---|---|
| `01_create_database.sql` | データベース `ai_learning_portal` と接続ユーザ `ai_learning_portal` の作成 |
| `snapshot_20261030/` | 2026-10-30 時点のスナップショット。全テーブルの定義と全データ(`schema_and_data.sql`)と講座の画像(`images/`)。含まれるデータはフォルダ内の `README.md` |
| `setup_db.ps1` | DB の作成・スナップショットの登録・講座の画像のコピーをまとめて実行する(Windows PowerShell) |
| `setup_db.sh` | 同上(macOS / Linux / Git Bash) |

### スナップショットに含まれるもの

- 講座 11件(公開中 10件・下書き 1件)と単元・演習・小テスト・データファイル・画像
- ユーザ 2名(`admin` / `r-kinoshita`)。**パスワードは作成元の環境と同じ**です
- 受講記録(提出・単元の完了・小テストの受験・修了)と、AI による講座作成の記録
- Alembic の版数(登録後に `alembic upgrade head` を実行すると、それ以降のマイグレーションだけが適用されます)

講座の画像は DB ではなくファイル(既定は `backend/var/images/`)で管理しているため、SQL とは別にコピーします(スクリプトが行います)。

## 手順

必要なもの:MySQL 8、Python 3.12、Node.js 22(アプリのソース一式を用意しておく)。

### 1. DB を作成してスナップショットを登録する

**Windows**(`db/` フォルダで実行)

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_db.ps1
```

**macOS / Linux / Git Bash**(`db/` フォルダで実行)

```bash
bash setup_db.sh
```

既存のデータが消えることの確認(`y` で続行)のあと、MySQL 管理者(root)のパスワードと、接続ユーザ `ai_learning_portal` のパスワードを聞かれます。
スクリプトは次を行います。

1. データベースと接続ユーザを作成する(すでにある場合は、接続ユーザのパスワードを今入力した値に更新する)
2. スナップショットのテーブル定義とデータを登録する(**既存のテーブルは削除して作り直す**)
3. 講座の画像を `backend/var/images/` にコピーする(同じ名前のファイルは上書き)

接続先や画像の保存先を変える場合は次のように指定します。

| | PowerShell | Bash(環境変数) |
|---|---|---|
| 接続先 | `-MysqlHost <ホスト> -Port <ポート> -RootUser <ユーザ>` | `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_ROOT_USER` |
| 画像の保存先(`IMAGE_LOCAL_DIR` を変えている場合) | `-ImageDir <フォルダ>` | `IMAGE_DIR` |

スクリプトを使わずに手で実行する場合:

```bash
# 01_create_database.sql の 'CHANGE_ME' を接続ユーザのパスワードに書き換えてから
mysql -u root -p < 01_create_database.sql
mysql -u root -p --default-character-set=utf8mb4 ai_learning_portal < snapshot_20261030/schema_and_data.sql
mkdir -p ../backend/var/images && cp -R snapshot_20261030/images/. ../backend/var/images/
```

### 2. アプリを設定して起動する

```bash
cd ../backend
python -m venv .venv
.venv\Scripts\activate                 # macOS / Linux は source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                   # MYSQL_PASSWORD(手順1の接続ユーザのパスワード)と APP_SECRET_KEY を設定
alembic upgrade head                   # スナップショット以降のマイグレーションがあれば適用(無ければ何もしない)

cd ../frontend && npm install && npm run build
cd ../backend && uvicorn app.main:app --port 8000
```

講座は DB に入っているため、講座の取り込み(`import-course`)やユーザの作成(`create-user`)は不要です。
ブラウザで http://localhost:8000 を開き、スナップショットのユーザでログインします。

**復元の場合**は、`backend/.env` がそのまま使えるので、手順1で接続ユーザのパスワードに `.env` の `MYSQL_PASSWORD` と同じ値を入力し、
手順2は `alembic upgrade head` とアプリの再起動だけで済みます。

## 注意

- スナップショットの登録は **既存のテーブルを削除して作り直します**。取り込み先の DB にあったデータはすべて消えるため、実行する DB を確認してください。
- ユーザのパスワード(ハッシュ)は作成元と同じになります。別の人が使う環境では、`backend/` で
  `python -m app.cli set-password --login <ログイン名>` を実行してパスワードを変更してください。
- スナップショットには受講記録や AI に渡したプロンプトの記録など、部署内の情報が含まれます。社外に渡したり、公開リポジトリに置いたりしないでください。
- 接続ユーザは `'ai_learning_portal'@'localhost'` で作成します。アプリと DB が別のサーバの場合は、`localhost` を接続元のホストに変えてください。
- ブラウザ内の Python は CDN(cdn.jsdelivr.net)から読み込むため、ブラウザはインターネットに接続できる必要があります。

## スナップショットを作り直す(作成元の環境で実行)

新しい時点のスナップショットが必要になったら、日付のフォルダを作って DB と講座の画像を書き出します。

```bash
mkdir -p snapshot_YYYYMMDD
mysqldump -u root -p --single-transaction --hex-blob --set-gtid-purged=OFF --no-tablespaces \
  --default-character-set=utf8mb4 --skip-dump-date \
  --result-file=snapshot_YYYYMMDD/schema_and_data.sql ai_learning_portal
cp -R ../backend/var/images snapshot_YYYYMMDD/images
```

書き出したら、`setup_db.ps1` の `$snapshotName` と `setup_db.sh` の `SNAPSHOT_NAME`、このファイルの表を新しいフォルダ名に変えます。
フォルダ内の `README.md`(含まれるデータの説明)も合わせて作成してください。
