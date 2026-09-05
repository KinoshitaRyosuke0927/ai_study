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

以下のコマンドはすべて **このディレクトリ(`015_frontier/`)をカレントにして** 実行してください。
`uvicorn app:app` は `app.py` のあるディレクトリで実行する必要があります
(リポジトリのルートで実行すると `Could not import module "app"` になります)。

```bash
# 0. このディレクトリへ移動
cd 015_frontier

# 1. MySQL にデータベースを用意(MySQL 8.x)
#    CREATE DATABASE frontier CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
#    (テストを実行する場合は frontier_test も作成)

# 2. 依存インストール
python -m venv .venv
source .venv/bin/activate        # Windows(PowerShell): .venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3. 設定
cp .env.example .env             # ← 既存の接続情報を記入(未記入なら sample モードで動作)

# 4. 起動(必ず 015_frontier/ で実行する)
uvicorn app:app --reload --port 8000
#   別ディレクトリから起動する場合: uvicorn app:app --app-dir 015_frontier --port 8000

# 5. ブラウザで http://localhost:8000 を開き、「定期実行」タブの「今すぐ実行」
```

## 設定(`.env`)

すべて `.env` / 環境変数から読み込みます(`settings.Settings` に一元化)。
主要な項目:

| 変数 | 説明 |
|---|---|
| `APP_RUN_MODE` | `sample`(ダミーデータ)/ `real`(実 API へ接続) |
| `APP_SCHEDULE_ENABLED` | APScheduler の有効化。毎日 0:00 に定期実行の要否を判定する |
| `MYSQL_*` | MySQL 接続情報 |
| `MATTERMOST_*` / `GITHUB_*` / `GROWI_*` / `TRELLO_*` | 各ソースの接続情報 |
| `AZURE_OPENAI_*` | Azure OpenAI のエンドポイント / キー / デプロイ名 |

`.env` は `.gitignore` 済みです。接続情報をコードにハードコードしないでください。

### データ取得に関する実行時設定(`acquisition_settings.json`)

画面の「設定」タブで以下を編集し `acquisition_settings.json` に保存します
(`.gitignore` 済み。無い場合はデフォルト値で動作)。この設定は**使用する処理の実行時**に
読み込まれるため、アプリの再起動は不要です。サンプルは `acquisition_settings.json.example`。

- データ取得開始日(この日の 0:00 以降のみ取得)
- 定期実行間隔(日次 N 日ごと / 週次 曜日、いずれも 0:00)
- Mattermost 取得チャンネル / Trello 取得ボード(`.env` トークンで一覧取得しチェック選択。0 件ならそのソースは取得しない)
- GitHub リポジトリ名称(`owner/repo` またはリポジトリ名)
- 参照する Wiki のページ(GROWI パス)

GitHub リポジトリ名称と Wiki のページは、**保存時に `.env` の Git アカウント情報 / GROWI
トークンで実際にアクセスできるか確認**します。取得できない場合は画面にエラーを表示し、
保存は行いません。

## 使い方

1. **ダッシュボード**: 主要指標のカードと Chart.js の推移グラフ。
2. **週次レポート**: 週を選択して KPT(Keep/Problem/Try)+ Fun-Done-Learn(Done/Learned)
   + リスク一覧(重要度バッジ)+ Markdown サマリ。各指摘に evidence 付き。
3. **差分**: 週ごとの added / changed / removed をソース別に表示。
4. **暗黙知検索**: 自然文クエリ → RAG 検索の回答 + 出典チャンク。
5. **Mattermost情報取得**: 設定チャンネルの投稿を期間指定で取得し、チャンネル別・
   時系列(昇順)・スレッド構造で表示。「現在情報取得」(データ取得開始日〜最新日)と
   「指定期間情報取得」(開始日〜終了日)の 2 方式。表示項目は投稿者・日時・本文・リアクション。
6. **Trello情報取得**: プルダウンでボードを 1 つ選び、現在の状況を取得。リスト → カード →
   詳細(カード名・メンバー・期限・ラベル・カバー・説明・チェックリスト・コメントとアクティビティ)。
   アーカイブ済み / テンプレートカード・添付ファイルは対象外。
7. **wiki情報取得**: 「ページ一覧取得」で設定パス配下のページ一覧を取得 → プルダウンで選択 →
   「取得」で記事内容・更新履歴(誰がいつ。過去断面は取得しない)・コメントを表示。添付は対象外。
8. **GitHub情報取得**: 「取得」で設定リポジトリのブランチ一覧(各ブランチはコミット履歴で活動を表す)
   と PR 一覧(open/closed・作成者・マージ実行者・コメント/レビュー)を表示。PR 詳細は直近30件のみ。
9. **設計書情報取得**: 「取得」で設定「設計書パス」フォルダ配下の全ファイルを既定ブランチから取得し、
   ファイルごとにアコーディオン表示(テキストは内容、バイナリは省略)。
10. **定期実行**: 手動実行(進捗はポーリング表示)、実行履歴、現在のモード。
11. **設定**: データ取得開始日 / 定期実行間隔 / GitHub(リポジトリ名称・設計書パス)/ Wiki パス /
    取得対象(Mattermost チャンネル・Trello ボード)。`acquisition_settings.json` に保存。

5〜9 の取得結果はタブを切り替えても保持(アプリ停止で消える)。DB へは保存しない。

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
| GET / POST | `/api/settings` | データ取得の実行時設定の取得 / 保存 |
| POST | `/api/mattermost/fetch` | body: `{"mode":"current","latest_date":"..."}` または `{"mode":"range","start_date":"...","end_date":"..."}` → チャンネル別・スレッド構造の投稿一覧 |
| GET | `/api/trello/boards` | 取得対象ボード設定のプルダウン用(設定済みボードを名前付きで返す) |
| POST | `/api/trello/fetch` | body: `{"board_id":"..."}` → リスト / カード / カード詳細 / コメント・アクティビティ |
| GET | `/api/growi/pages` | 設定パス配下のページ一覧(プルダウン用) |
| POST | `/api/growi/fetch` | body: `{"page_id":"..."}` → 記事内容 / 更新履歴 / コメント |
| POST | `/api/github/fetch` | 設定リポジトリのブランチ活動 + PR(作成者/マージ実行者/コメント) |
| POST | `/api/design/fetch` | 設定「設計書パス」配下の全ファイル内容 |

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
runtime_config.py データ取得の実行時設定(acquisition_settings.json の読み書き)
provider_options.py 設定画面のアクセス確認 / 選択肢取得(Mattermost/Trello/GitHub/GROWI)
mattermost_view.py 「Mattermost情報取得」画面用の投稿取得(チャンネル別・スレッド構造)
trello_view.py    「Trello情報取得」画面用のボード取得(リスト/カード/詳細/活動)
growi_view.py     「wiki情報取得」画面用のページ取得(記事内容/更新履歴/コメント)
github_view.py    「GitHub情報取得」画面用のブランチ活動 + PR 取得
design_view.py    「設計書情報取得」画面用のフォルダ配下ファイル取得
collectors/       base / sample / mattermost / github / growi / trello
static/index.html 単一ファイルのダッシュボード
docs/deploy-azure.md  Azure デプロイ手順
```

## Azure へのデプロイ

`docs/deploy-azure.md` を参照(本リポジトリでは準備のみ。デプロイ実行は利用者が行う)。
