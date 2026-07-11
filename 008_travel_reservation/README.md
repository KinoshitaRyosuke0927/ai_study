# travel_reservation

旅行者および宿泊施設経営者向けの予約管理アプリケーション。
バックエンドはFastAPI(+MySQL)、フロントエンドはReact(Vite)で構成されている。

## 構成

- `backend/`: FastAPI製API(MySQLへ接続)
- `frontend/`: React(Vite)製フロントエンド

## 前提環境

- Python 3.12系
- Node.js(npmが使用できること)
- MySQL 8.0

## セットアップ手順

### 1. リポジトリのクローン

```powershell
git clone <このリポジトリのURL>
cd travel_reservation
```

### 2. バックエンドのセットアップ

#### 2-1. MySQLの準備

MySQLが未導入の場合は、以下の手順書に従ってインストールからデータ投入まで行う。

1. [backend/database/docs/01_mysql_install.md](backend/database/docs/01_mysql_install.md) — MySQL 8.0のインストール(未導入者向け)
2. [backend/database/docs/02_db_setup.md](backend/database/docs/02_db_setup.md) — `travel_reservation`データベースの作成・データ投入
3. [backend/database/docs/03_a5m2_connect.md](backend/database/docs/03_a5m2_connect.md) — A5:SQL Mk-2からのDB接続確認(任意)

MySQLが既に導入済みであれば、2番の手順書からでよい。

#### 2-2. Pythonパッケージのインストール

```powershell
cd backend
pip install -r requirements.txt
```

#### 2-3. 環境変数ファイルの作成

`backend`配下に以下の内容で`.env`ファイルを作成し、`DB_PASSWORD`に手順2-1で設定した`ais_admin`のパスワードを設定する。

```
DB_HOST=localhost
DB_PORT=3306
DB_USER=ais_admin
DB_PASSWORD=<ais_adminのパスワード>
DB_NAME=travel_reservation
```

#### 2-4. バックエンドの起動

`backend`ディレクトリで以下を実行する。

```powershell
uvicorn main:app --reload
```

ブラウザで`http://127.0.0.1:8000/health`にアクセスし、`{"status":"ok"}`が返ることを確認する。

#### 2-5. バックエンドの単体テスト実行

`backend`ディレクトリで以下を実行する。

```powershell
python -m pytest tests/
```

### 3. フロントエンドのセットアップ

#### 3-1. パッケージのインストール

```powershell
cd frontend
npm install
```

#### 3-2. フロントエンドの起動

```powershell
npm run dev
```

`http://localhost:3000`にアクセスして画面が表示されることを確認する。

## 補足

- DBまわりの詳細な資料はdocs配下の資料を参照する。
