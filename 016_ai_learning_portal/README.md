# AI学習ポータル

部署メンバーがデータサイエンスを学ぶための、部署内の学習サービスです。
講座は単元ごとに「概念の説明」と「ブラウザ内で Python を実行するハンズオン(Colab 風のセル)」で構成され、
演習は自動で採点されます。

- 仕様・決定事項・開発フェーズ:[docs/spec.md](docs/spec.md)
- 講座ノートブックの書き方:[docs/notebook-format.md](docs/notebook-format.md)

現在は **フェーズ4(AI による講座作成・.ipynb の画面取り込み)** まで実装済みです。
Azure へのデプロイ手順は [docs/azure_deploy.md](docs/azure_deploy.md) にまとめています(デプロイは未実施)。

| 画面 | 内容 |
|---|---|
| ホーム / 講座カタログ / マイ学習 | 続きから学習・学習ロードマップ・新着講座 / レベル・状態・タグで絞り込み / 自分の進捗・受験履歴 |
| 講座詳細 / 単元 / 小テスト | 単元一覧と進捗 / ノートブック型の単元(Colab 風のセルで実行・採点)/ 全単元の完了後に受験、満点で修了 |
| 管理(管理者のみ) | 講座管理・講座の作成(AI で作成 / .ipynb の取り込み / 白紙から)・単元エディタ・小テストの編集・作成者による検証・公開前チェック・メンバーの受講状況・メンバー管理 |

## 構成

```
016_ai_learning_portal/
  backend/            FastAPI(Python 3.12)
    app/              アプリ本体(models / services / routers / cli)
    alembic/          DB マイグレーション
    tests/            pytest
  frontend/           React + TypeScript(Vite)
    src/python/       ブラウザ内 Python(Pyodide を動かす Web Worker)
  backend/app/ai/     AI(Azure OpenAI)による講座下書き生成(接続・入出力の型・プロンプト)
  infra/              Azure の ARM テンプレート(Container Apps・DB 自動停止ジョブ)
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
cd ../backend && uvicorn app.main:app --port 8000
```

ブラウザで http://localhost:8000 を開いてログインします。

### 画面を修正しながら開発する場合

バックエンド(`uvicorn app.main:app --reload --port 8000`)に加えて、`frontend/` で `npm run dev` を実行し、
http://localhost:5173 を開きます(`/api` はバックエンドへ転送されます)。

## 管理用コマンド(`backend/` で実行)

| コマンド | 内容 |
|---|---|
| `python -m app.cli create-user --login <名前> --name <表示名> [--admin]` | ユーザ作成(パスワードは対話入力) |
| `python -m app.cli set-password --login <名前>` | パスワード変更 |
| `python -m app.cli delete-user --login <名前>` | ユーザ削除(受講記録も削除) |

ユーザの追加・パスワードの再設定・削除は、管理者でログインして「管理 › メンバー管理」からも行えます(Azure 上ではこちらを使います)。
| `python -m app.cli import-course <講座フォルダ> [--author <名前>] [--replace]` | 講座の取り込み。`--replace` は既存講座を置き換える(**受講記録も削除される**) |
| `python -m app.cli db-state` / `db-start` / `db-stop` | Azure の MySQL サーバーの状態確認・起動・停止 |
| `python -m app.cli db-idle-stop [--idle-minutes 60]` | 一定時間アクセスが無ければ DB を停止(Azure ではスケジュールジョブで実行) |

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

## AI による講座作成

管理 › 講座を作成 › 「題材から AI で作成」で、題材 → 構成案(画面で編集)→ 下書き(単元の説明・例題・演習、小テスト)を作ります。

- AI は `010_ai_reviewer` と同じ Azure OpenAI を使います(接続情報はリポジトリ直下の `.env` の `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_KEY`)。
- 構成案は `gpt-5.4-mini`、下書きは `gpt-5.4`(`AI_MODEL_OUTLINE` / `AI_MODEL_DRAFT` で変更可)。
- AI が作った演習・小テストはすべて「未検証」です。作成者が解答を書いて検証する(選択式・数値は内容を確認する)まで公開できません。
- プロンプトは `backend/app/ai/prompts.py`、出力の型は `backend/app/ai/schemas.py` にまとめています。
  呼び出しの記録(プロンプト・応答・所要時間・版番号)は `ai_generations` テーブルに残ります。

## Azure へのデプロイ

詳しい手順は [docs/azure_deploy.md](docs/azure_deploy.md) を参照してください(010_ai_reviewer と同じリソースグループ・IP 制限)。

| 項目 | 構成 |
|---|---|
| アプリ | Azure Container Apps(従量課金、0〜1台)`ca-ai-learning-portal`。イメージは ACR `acrailearningportal` で `az acr build` |
| DB | Azure Database for MySQL フレキシブルサーバー `mysql-ai-learning-portal`(Burstable B1ms) |
| DB の起動・停止 | 普段は停止。停止中のアクセスでアプリが起動し、60 分使われなければ Container Apps ジョブが停止する |
| AI | 010 と同じ Azure OpenAI |
| IP 制限 | 010 と同じ社内ネットワーク(オフィス・VPN) |

コンテナは起動時に `alembic upgrade head` を実行してからアプリを起動します(DB が停止中ならマイグレーションをスキップして起動)。
