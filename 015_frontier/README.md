# Frontier

開発プロジェクトの活動履歴(Mattermost / GitHub / GROWI / Trello)を週次で自動収集し、
Azure OpenAI が分析して週次レポート(KPT / Fun-Done-Learn)・潜在問題スキャン・
暗黙知の抽出と自然文検索(RAG)を行うローカルアプリケーションです。

## 特長

- **サンプルデータモード**: 接続情報が無くても、意図的に偏りを含んだ 5 週分の
  ダミーデータでパイプラインと AI 分析を通しで試せます(`APP_RUN_MODE=sample`)。
- **冪等**: 同じ週を再実行してもイベント・指標は重複しません(`events.event_uid` の UNIQUE)。
- **AI フォールバック**: Azure OpenAI 未設定でも、ルールベースの分析で完走します。

## 必要環境

- Python 3.11 以上
- MySQL 8.x(デフォルト認証 `caching_sha2_password` に対応。`cryptography` を同梱)

## セットアップ

```bash
# 1. MySQL にデータベースを用意(MySQL 8.x)
#    CREATE DATABASE frontier CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
#    (テストを実行する場合は frontier_test も作成)

# 2. 依存インストール
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. 設定
cp .env.example .env             # ← 既存の接続情報を記入(未記入なら sample モードで動作)

# 4. 起動
uvicorn app:app --reload --port 8000

# 5. ブラウザで http://localhost:8000 を開き、「実行・設定」タブの「今すぐ実行」
```

## 設定(`.env`)

すべて `.env` / 環境変数から読み込みます(`settings.Settings` に一元化)。
主要な項目:

| 変数 | 説明 |
|---|---|
| `APP_RUN_MODE` | `sample`(ダミーデータ)/ `real`(実 API へ接続) |
| `APP_SCHEDULE_ENABLED` / `APP_SCHEDULE_CRON` | APScheduler の有効化と cron(既定: 毎週月曜 09:00 JST) |
| `MYSQL_*` | MySQL 接続情報 |
| `MATTERMOST_*` / `GITHUB_*` / `GROWI_*` / `TRELLO_*` | 各ソースの接続情報 |
| `AZURE_OPENAI_*` | Azure OpenAI のエンドポイント / キー / デプロイ名 |

`.env` は `.gitignore` 済みです。接続情報をコードにハードコードしないでください。

## 使い方

1. **ダッシュボード**: 主要指標のカードと Chart.js の推移グラフ。
2. **週次レポート**: 週を選択して KPT(Keep/Problem/Try)+ Fun-Done-Learn(Done/Learned)
   + リスク一覧(重要度バッジ)+ Markdown サマリ。各指摘に evidence 付き。
3. **差分**: 週ごとの added / changed / removed をソース別に表示。
4. **暗黙知検索**: 自然文クエリ → RAG 検索の回答 + 出典チャンク。
5. **実行・設定**: 手動実行(進捗はポーリング表示)、実行履歴、現在のモード。

## API

| メソッド | パス | 内容 |
|---|---|---|
| GET | `/api/health` | DB 接続と実行モード |
| POST | `/api/run?analyze=true` | パイプライン手動実行(非同期。`run_id` を返す) |
| GET | `/api/runs` | 実行履歴 |
| GET | `/api/weeks` | データのある週一覧 |
| GET | `/api/metrics` | 週ごとの指標(推移グラフ用) |
| GET | `/api/report/{week}` | KPT + risks + サマリ |
| GET | `/api/diff/{week}` | added / changed / removed |
| GET | `/api/events?week=&source=&type=` | 生イベント |
| GET | `/api/decisions?week=` | 暗黙知(決定事項) |
| POST | `/api/search` | body: `{"query": "..."}` → RAG 検索 |

## テスト

```bash
pytest
```

- `test_collectors.py`: 4 コレクタの エンドポイント / 正規化 / ページング(`responses` で HTTP モック)
- `test_diff.py`: 差分計算(added/changed/removed)
- `test_metrics.py`: 指標計算
- `test_schema.py`: MySQL への冪等テスト(テスト DB は `frontier_test`)

テストは `MYSQL_DATABASE=frontier_test` を環境変数で上書きして実行されます
(`tests/conftest.py`)。AI 呼び出しはフォールバックに固定され、Azure OpenAI は呼びません。

## 構成

```
app.py            FastAPI + APScheduler + 静的配信
weekly.py         週次パイプライン(collectors → events → metrics → AI → embeddings)
settings.py       pydantic-settings による設定
db.py             SQLAlchemy エンジン / schema.sql 適用
schema.sql        テーブル定義(CREATE TABLE IF NOT EXISTS)
store.py          events/items 保存・週次断面・差分
metrics.py        指標計算(すべて Python 側)
ai.py             Azure OpenAI 分析(未設定時フォールバック)
rag.py            埋め込み生成 + コサイン類似度検索
vectors.py        float32 BLOB シリアライズ / コサイン
weeks.py          ISO 週ユーティリティ
collectors/       base / sample / mattermost / github / growi / trello
static/index.html 単一ファイルのダッシュボード
docs/deploy-azure.md  Azure デプロイ手順
```

## Azure へのデプロイ

`docs/deploy-azure.md` を参照(本リポジトリでは準備のみ。デプロイ実行は利用者が行う)。
