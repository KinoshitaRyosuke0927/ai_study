# プロジェクト支援ツール「Frontier」実装プロンプト(Claude Code用)

## あなたへの指示

あなたは経験豊富なPython/Webフルスタックエンジニアです。このドキュメントは、ソフトウェア開発プロジェクトを支援するツール「Frontier」の**プロトタイプ実装仕様**です。以下の指示に従って、ローカル環境で動作するアプリケーションを実装してください。

重要な作業原則:

- 仕様書の末尾「実装ステップ」の順に**段階的に実装し、各ステップ完了時に起動・動作確認を行ってから次へ進む**こと
- 判断に迷う箇所は、この仕様書の「確定事項」を優先し、記載がない場合は最もシンプルな実装を選ぶこと(推測で複雑化しないこと)
- 外部サービス(Mattermost / GitHub / GROWI / Trello / Azure OpenAI)への実際の接続情報はユーザーが別途用意する。あなたは `.env.example` に環境変数を定義し、**コード中に接続情報をハードコードしないこと**
- 接続情報がなくても動作確認できるよう、「サンプルデータコレクタ」を必ず実装する(後述)

---

## 1. 目的と概要

開発プロジェクトの活動履歴を週次で自動収集し、AIが分析して振り返り(KPT / Fun-Done-Learn)や潜在問題の洗い出しを行うローカルアプリケーション。

- **収集対象**: Mattermost(特定チャンネル)、Trello(特定ボード)、GROWI(特定パス配下のページ)、GitHub(特定リポジトリ)
- **記憶**: 週ごとの断面(スナップショット)をMySQLに蓄積し、前週との差分を計算する
- **AI分析**(Azure OpenAI を使用):
  1. 週次レポート生成(KPT / Fun-Done-Learn 形式、 evidence 付き)
  2. プロジェクト総覧による潜在問題スキャン(滞留・負荷の偏り・品質リスクなど)
  3. 暗黙知の抽出(決定事項とその理由の検出)と自然文検索(RAG)
- **UI**: ブラウザで操作する単一ページのダッシュボード
- **実行**: 週次の自動実行(APScheduler)と手動実行(ボタン/API)
- **将来**: Azureへのデプロイを予定(本プロトタイプでは準備まで、§10参照)

## 2. 技術スタック(確定事項)

| 項目 | 採用技術 | 備考 |
|---|---|---|
| 言語 | Python 3.11+ | 型ヒントを必須とする |
| Webフレームワーク | FastAPI + uvicorn | |
| DB | **MySQL 8.x** | ユーザー指定。ドライバは PyMySQL |
| DBアクセス | SQLAlchemy 2.x (同期) | 接続文字列は `mysql+pymysql://...?charset=utf8mb4` |
| スキーマ管理 | 起動時に `schema.sql` を適用(`CREATE TABLE IF NOT EXISTS`) | Alembicは使わない(プロトタイプのため) |
| スケジューラ | APScheduler | CronTrigger、タイムゾーン Asia/Tokyo |
| AI | `openai` SDK の `AzureOpenAI` クライアント | Chat + Embeddings |
| HTTP | requests | セッション使い回し、タイムアウト・リトライ必須 |
| 設定 | pydantic-settings + python-dotenv | 全設定を環境変数から読む |
| フロントエンド | 単一 `static/index.html`(vanilla JS + Chart.js をCDNから) | ビルドツール不要 |
| テスト | pytest + responses(HTTPモック) | コレクタの正規化ロジックを対象 |

依存パッケージは `requirements.txt` にまとめる。**MySQL 8 のデフォルト認証(`caching_sha2_password`)に対応するため `cryptography` も必ず含めること。**

## 3. データベース設計(MySQL)

### 3.1 MySQL採用に関する設計判断

- 文字コード: データベース全体を `utf8mb4` とする(Mattermost投稿には絵文字が含まれるため必須)
- 日時: すべてUTCで保存(`DATETIME`)。表示時にAsia/Tokyoへ変換
- 週の定義: ISO週(月曜開始)。`week` カラムは `YYYY-Www` 形式の文字列(例: `2026-W36`)
- **ベクトル検索について**: MySQLには pgvector 相当の拡張がないため、埋め込みベクトルは `BLOB`(float32配列をバイト化)で保存し、**類似検索はアプリケーション側でコサイン類似度を計算**する。プロトタイプのデータ規模(週次で数百〜数千チャンク)では実用上問題ない。将来データ量が問題になった時点で PostgreSQL + pgvector への移行、またはAzure AI Search併用を検討する(本プロトタイプでは対応不要)

### 3.2 テーブル定義(`schema.sql`)

```sql
CREATE TABLE IF NOT EXISTS events (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  week VARCHAR(10) NOT NULL,              -- ISO週 "2026-W36"
  source VARCHAR(20) NOT NULL,            -- mattermost / trello / growi / github / sample
  type VARCHAR(40) NOT NULL,              -- post / card_moved / pr_merged / page_updated / ...
  actor VARCHAR(255) NOT NULL,
  ts DATETIME NOT NULL,                   -- UTC
  ref VARCHAR(255) NOT NULL,              -- ソース内一意キー(投稿ID / カードID / SHA / ページID)
  payload JSON NOT NULL,
  event_uid VARCHAR(300) GENERATED ALWAYS AS (concat(source, ':', ref, ':', type)) STORED,
  UNIQUE KEY uq_event (event_uid),        -- 再実行時の二重取り込み防止
  INDEX idx_week_source (week, source)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS items (
  item_key VARCHAR(255) PRIMARY KEY,      -- 例: "trello:card:abc123", "github:pr:42"
  source VARCHAR(20) NOT NULL,
  type VARCHAR(40) NOT NULL,              -- card / issue / pr / page / thread
  title VARCHAR(1024) NOT NULL,
  status VARCHAR(40) NOT NULL,            -- open / done / merged / archived / ...
  assignee VARCHAR(255) NULL,
  first_week VARCHAR(10) NOT NULL,        -- 初検出週
  last_week VARCHAR(10) NOT NULL,         -- 最終確認週
  payload JSON NOT NULL
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- 週次断面(差分計算の本体)
CREATE TABLE IF NOT EXISTS week_items (
  week VARCHAR(10) NOT NULL,
  item_key VARCHAR(255) NOT NULL,
  status VARCHAR(40) NOT NULL,
  title VARCHAR(1024) NOT NULL,
  PRIMARY KEY (week, item_key)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS metrics (
  week VARCHAR(10) NOT NULL,
  name VARCHAR(60) NOT NULL,              -- mattermost_posts, github_prs_merged など
  value DOUBLE NOT NULL,
  PRIMARY KEY (week, name)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS reports (
  week VARCHAR(10) PRIMARY KEY,
  kpt JSON NOT NULL,                      -- keep / problem / try / done / learned
  risks JSON NOT NULL,                    -- 潜在問題リスト
  summary_md MEDIUMTEXT NOT NULL,         -- Markdown形式の週次サマリ
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS decisions (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  week VARCHAR(10) NOT NULL,
  summary TEXT NOT NULL,                  -- 決定事項
  rationale TEXT NULL,                    -- 理由・背景(暗黙知)
  participants JSON NULL,
  source_refs JSON NOT NULL               -- event_id や URL の配列
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS embeddings (
  chunk_id VARCHAR(300) PRIMARY KEY,      -- "{source}:{ref}:{chunk_no}"
  week VARCHAR(10) NOT NULL,
  source VARCHAR(20) NOT NULL,
  ref VARCHAR(255) NOT NULL,
  text MEDIUMTEXT NOT NULL,
  vec BLOB NOT NULL,                      -- float32配列
  model VARCHAR(100) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_week (week)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS runs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  started_at DATETIME NOT NULL,
  finished_at DATETIME NULL,
  status VARCHAR(20) NOT NULL,            -- running / success / error
  mode VARCHAR(10) NOT NULL,              -- manual / scheduled
  detail TEXT NULL                        -- エラー内容など
) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
```

## 4. 設定(`.env.example` を生成する)

ユーザーが既存の接続情報を流用するため、**すべての値はプレースホルダのまま `.env.example` に定義し、`.env` はコミット対象外**とする。`.env` が無い場合はサンプルデータモードで起動できること。

```ini
# --- アプリ ---
APP_TZ=Asia/Tokyo
APP_RUN_MODE=sample            # sample=サンプルデータ生成 / real=実APIへ接続
APP_SCHEDULE_ENABLED=true      # APScheduler有効化(ローカル試行時はfalseでも可)
APP_SCHEDULE_CRON=0 9 * * 1    # 毎週月曜 09:00

# --- MySQL(既存の接続情報を流用) ---
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=project_pulse
MYSQL_PASSWORD=changeme
MYSQL_DATABASE=project_pulse

# --- Mattermost(既存の接続情報を流用) ---
MATTERMOST_URL=https://mattermost.example.com
MATTERMOST_TOKEN=changeme      # Personal Access Token
MATTERMOST_CHANNEL_ID=changeme

# --- GitHub(既存の接続情報を流用) ---
GITHUB_TOKEN=changeme          # fine-grained PAT
GITHUB_REPOS=owner/repo1,owner/repo2   # カンマ区切り・複数可

# --- GROWI(既存の接続情報を流用) ---
GROWI_URL=https://growi.example.com
GROWI_API_TOKEN=changeme
GROWI_TARGET_PATHS=/projects/foo       # カンマ区切り。この配下のページを対象

# --- Trello(既存の接続情報を流用) ---
TRELLO_API_KEY=changeme
TRELLO_TOKEN=changeme
TRELLO_BOARD_ID=changeme

# --- Azure OpenAI(既存リソースを流用) ---
AZURE_OPENAI_ENDPOINT=https://xxx.openai.azure.com/
AZURE_OPENAI_API_KEY=changeme
AZURE_OPENAI_API_VERSION=2024-12-01-preview   # 必要に応じ最新へ
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o            # 既存デプロイ名に合わせる
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small
```

設定は `pydantic-settings` の `Settings` クラスに一元化し、コード中で直接 `os.getenv` を書かないこと。

## 5. 実装要件

### 5.1 共通Eventモデル(`collectors/base.py`)

すべてのコレクタは、活動をこの正規化イベントに変換して返す:

```python
@dataclass
class Event:
    source: str      # mattermost / trello / growi / github / sample
    type: str        # post / card_moved / pr_merged / page_updated / ...
    actor: str
    ts: datetime     # UTC
    ref: str         # ソース内一意キー
    payload: dict

class Collector(Protocol):
    source: str
    def fetch_since(self, since: datetime) -> list[Event]: ...
```

共通要件:

- `fetch_since(since)` は `since` 以降のイベントのみ返す(差分取得)
- HTTP はタイムアウト30秒、429/5xx時は指数バックオフで最大3回リトライ
- ページングを実装すること(Mattermost: `page`/`per_page`、GitHub: `Link` ヘッダ、GROWI: `offset`/`limit`、Trello: `before`/`limit`)
- 失敗時は当該ソースをスキップしてログに残し、パイプライン全体は停止させない

### 5.2 各コレクタ

| コレクタ | API | 差分取得の要 | 取得内容と正規化 |
|---|---|---|---|
| Mattermost | `GET {url}/api/v4/channels/{channel_id}/posts?since=<エポックms>` 認証: `Authorization: Bearer <token>` | `since`(ミリ秒) | 投稿1件=イベント `post`。payload: `{text, thread_root, channel_id}`。返却は `posts` マップ + `order` を見て時系列化 |
| GitHub | `GET /repos/{owner}/{repo}/commits?since=<ISO8601>`、`/pulls?state=all&sort=updated&direction=desc`、`/issues?state=all&sort=updated&direction=desc`(認証: `Authorization: Bearer <token>`) | `since` / updated降順でupdatedAt以降のみ | `commit` / `pr_opened` / `pr_merged`(merged_at有無で判定)/ `issue_opened` / `issue_closed` / `issue_reopened`。payload: `{title, url, labels, assignee}` |
| GROWI | `GET {url}/_api/v3/pages/list?access_token=<token>&limit=100&offset=N` で一覧、必要に応じ `/_api/v3/pages/get` | 一覧の `updatedAt` を前回取得時刻と比較 | ページ作成= `page_created`、更新= `page_updated`。payload: `{path, revision_id, updatedAt}`。コメント取得がAPIで容易な範囲であれば含める(困難なら対応しなくてよい) |
| Trello | `GET https://api.trello.com/1/boards/{board_id}/actions?since=<YYYY-MM-DD>&limit=1000&key=<key>&token=<token>` | `since`(日付)。1,000件上限あり → `before` パラメータでページング | アクションtypeをイベントへ対応: `createCard`→`card_created`、`updateCard`(listAfterあり)→`card_moved`(移動先リスト名をpayloadへ)、`updateCard:closed`→`card_archived` など。カード現在状態は `GET /1/boards/{id}/cards` で取得し items に反映 |

itemsテーブルへの反映ロジックはコレクタ共通の `upsert_items()` として実装する。

### 5.3 サンプルデータコレクタ(必須)

`APP_RUN_MODE=sample` のとき、4ソースの実APIの代わりに `SampleCollector` を使用する:

- 過去4〜6週分のリアルな雰囲気のサンプルデータを生成する(Mattermost投稿数が週により増減する、特定メンバーにコミットが集中する、レビュー待ちPRが滞留する、カードが完了を上回る、など**潜在問題が検出できるような偏りを意図的に含める**)
- 日本語のプロジェクトらしいテキスト(コミットメッセージ、カード名、Wikiページ名)を使用
- これにより**接続情報なしでもパイプライン全体とAI分析の縦貫通テストが可能**になる

### 5.4 差分・指標計算(`store.py` / `metrics.py`)

- `run_week()` 実行のたびに、その週の `week_items` 断面を保存
- 差分計算: 前週の `week_items` と比較し、`added / changed / removed` を item ごとに算出(`type` 別に集約)
- 指標は**必ずPythonコードで計算**(AIに数えさせない)。最低限このセット:

| 指標 | 定義 |
|---|---|
| mattermost_posts / mattermost_active_users | 週の投稿数 / 投稿したユニーク人数 |
| trello_cards_created / trello_cards_done | 作成数 / done扱いリストに移動した数 |
| trello_wip | 完了以外のリストに残るカード数(週末時点) |
| github_commits / github_prs_merged / github_prs_opened | 週の件数 |
| github_stale_prs | オープンから3日以上マージされていないPR数 |
| github_issues_reopened | 再オープンされたissue数 |
| growi_pages_created / growi_pages_updated | 週の件数 |

- 指標・イベント・レポートはすべて `week` で結合できる。ダッシュボードは過去週の `metrics` を並べて推移グラフを描く

### 5.5 Azure OpenAI 分析(`ai.py`)

`AzureOpenAI(azure_endpoint=..., api_key=..., api_version=...)` を使用し、チャットとエンベディングは `.env` のデプロイ名を使う。

**(a) 週次レポート(KPT / Fun-Done-Learn)** — structured outputs(JSON Schema、`strict: true`)で以下を出力させ `reports` に保存:

- `keep[]` / `problem[]` / `done[]` / `learned[]`: 各 `{title, detail, evidence[]}`
- `try[]`: 各 `{title, detail, followup_of}`(`followup_of` は先週のtry項目を引用できる)
- **ハルシネーション防止ルール**(システムプロンプトに明記):
  - 入力に含まれない事実を捏造しない
  - 数値は入力された指標JSONをそのまま引用する(再計算・推測しない)
  - すべての指摘に `evidence`(event_uid または指標名+週)を引用させる

入力: 今週の指標JSON、差分ダイジェスト(added/changed/removedのitem種別ごとの要約)、先週のKPT(特にtry)、直近4週の指標推移。

**(b) 潜在問題スキャン** — 同じくstructured outputsで `risks[]` を出力:

- スキーマ: `{category, severity(high|mid|low), title, detail, evidence[]}`
- システムプロンプトにチェック観点を明記: 進捗の滞留 / 品質リスク(再オープン・バグ集中)/ 負荷の偏り(特定メンバー集中・バスファクター)/ コミュニケーション低下(投稿数急減・反応遅延)/ スコープ膨張(作成ペース>完了ペース)/ ドキュメント腐敗(コード変更後に更新されないWiki)

**(c) 暗黙知の抽出** — Mattermost投稿・スレッドから「決定事項+理由+代替案・異論」を検出し `decisions` に保存。検出基準をプロンプトに明記(「〜することにした」「〜で合意」「〜は見送り」などの言語パターン)。

**(d) 埋め込みとRAG検索** — 各イベントのテキストを800文字程度のチャンクに分割し embeddings に蓄積。検索時はクエリを埋め込み化し、**Python側でコサイン類似度top-kを抽出**した上で、チャットモデルに渡して回答を生成する。

全AI呼び出しは: 失敗時リトライ1回 → エラーを記録して処理継続。トークン消費を抑えるため、summary・embeddingは週ごとに一度だけ生成し再利用。

### 5.6 週次パイプライン(`weekly.py`)

```
run(mode):
  1. runs テーブルに実行記録(running)を作成
  2. since = 前回成功実行時刻(runs から取得。初回は「4週前」)
  3. 各コレクタで fetch_since → events に保存(uq_eventで冪等)
  4. items / week_items を更新
  5. 指標計算 → metrics に保存
  6. AI分析: レポート生成 + リスクスキャン + 暗黙知抽出 → reports / decisions
  7. 埋め込み生成 → embeddings
  8. runs を success で更新(エラー時は error と detail)
```

- 再実行してもイベントが重複しない(冪等)こと
- 週の境界: 実行時点のISO週。途中の日付データは `ts` の週へ正規化して格納

### 5.7 Web UI / API(`app.py` + `static/index.html`)

FastAPIエンドポイント:

| メソッド | パス | 内容 |
|---|---|---|
| GET | `/` | `static/index.html` を配信 |
| GET | `/api/health` | DB接続・設定モード(sample/real)を返す |
| POST | `/api/run?analyze=true` | パイプラインを手動実行(非同期で開始し run_id を返す) |
| GET | `/api/runs` | 実行履歴一覧 |
| GET | `/api/weeks` | データ存在する週一覧 |
| GET | `/api/metrics` | 週ごとの指標(JSON。推移グラフ用) |
| GET | `/api/report/{week}` | KPT + risks + サマリ |
| GET | `/api/diff/{week}` | added / changed / removed 一覧 |
| GET | `/api/events?week=&source=&type=` | 生イベント閲覧 |
| GET | `/api/decisions?week=` | 暗黙知一覧 |
| POST | `/api/search` | body: `{"query": "..."}` → RAG検索結果+AI回答 |

UI(`static/index.html`、単一ファイル、Chart.js はCDN):

1. **ダッシュボードタブ**: 主要指標のカード表示 + Chart.js折れ線グラフ(指標推移)
2. **週次レポートタブ**: 週を選択 → KPT(Keep/Problem/Try/Done/Learned を色分けカード)+ リスク一覧(重要度バッジ)+ サマリMarkdown
3. **差分タブ**: 週を選択 → added/changed/removed をソース別に表示
4. **暗黙知検索タブ**: 検索フォーム → 回答+出典(chunk一覧)表示
5. **実行・設定タブ**: 「今すぐ実行」ボタン(実行中はスピナー、結果はポーリングで反映)、実行履歴、現在のモード(sample/real)表示

デザインはダーク寄りのシンプルなダッシュボード風。フレームワークは使わず素のHTML/CSS/JSで書くこと。

### 5.8 ログ・エラーハンドリング

- `logging` を使用(フォーマット: 時刻, レベル, モジュール, メッセージ)。外部API呼び出し・AI呼び出しは INFO/ERROR で必ず記録
- コレクタ1ソースの失敗でパイプライン全体を止めない(エラーを記録して続行)
- API エラーは適切なHTTPステータス + 説明的なメッセージで返す

## 6. テスト(`tests/`)

- `test_collectors.py`: `responses`(HTTPモック)を使い、**4コレクタそれぞれ**で (1) 正しいエンドポイント・パラメータで叩くこと (2) JSONレスポンスがEventへ正しく正規化されること (3) ページングが機能すること
- `test_diff.py`: week_items の差分計算(added/changed/removed)のユニットテスト
- `test_metrics.py`: 指標計算のユニットテスト
- `test_schema.py`: MySQLに対する冪等テスト(uq_event により再取り込みで重複しないこと)。テスト用DBは `project_pulse_test` を使用
- AI呼び出しはモック可能な構造にすること(テストで実際のAzure OpenAIを呼ばない)

## 7. 実行手順(README.md に記載)

```bash
# 1. MySQLにデータベースとユーザーを用意(MySQL 8.x)
#    CREATE DATABASE project_pulse CHARACTER SET utf8mb4;
# 2. 依存インストール
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# 3. 設定
cp .env.example .env   # ← ユーザーが既存の接続情報を記入
# 4. 起動(接続情報がなくても APP_RUN_MODE=sample で動作)
uvicorn app:app --reload --port 8500
# 5. ブラウザで http://localhost:8500 を開き、「今すぐ実行」
```

## 8. 実装ステップ(この順に進めること)

1. **雛形**: ディレクトリ構成、`requirements.txt`、`Settings`、`schema.sql` 適用処理、FastAPI最小構成 → 起動確認
2. **パイプライン骨格**: `SampleCollector` + イベント保存 + 差分計算 + 指標計算をAI無しで通す → `/api/metrics` が数値を返すことを確認
3. **実コレクタ4種**: Mattermost → GitHub → GROWI → Trello の順に実装し、各ステップでテストを追加・実行
4. **AI分析**: Azure OpenAI による KPT/リスク/暗黙知生成(sampleモードでも呼び出される)。AIが使えない環境ではダミー応答を返すフォールバックを用意
5. **RAG検索**: 埋め込み生成 + `/api/search`
6. **UI完成**: 5タブの実装
7. **仕上げ**: APScheduler、README、`docs/deploy-azure.md`(§10)

各ステップの完了時に `uvicorn` 起動 + `pytest` 実行を確認し、問題があれば修正してから次へ進むこと。

## 9. 受け入れ基準

- [ ] `APP_RUN_MODE=sample` の状態で起動し、「今すぐ実行」でサンプルデータ4週分が取り込まれる
- [ ] ダッシュボードに指標推移グラフが表示される
- [ ] 週次レポートに KPT / Fun-Done-Learn / リスクが evidence 付きで表示される
- [ ] 差分タブで週ごとの added / changed / removed が確認できる
- [ ] 同じ週を再実行してもイベント・指標が重複しない
- [ ] `pytest` がすべて成功する
- [ ] 実接続情報を `.env` に設定し `APP_RUN_MODE=real` にすると、4ソースの実データでパイプラインが動く(ユーザーが検証)
- [ ] 接続情報・トークンがソースコードにハードコードされていない

## 10. Azureへのデプロイ(本プロトタイプでは準備まで)

本ステップでは**実装のみ**。実際のデプロイ実行はユーザーが行う。以下を `docs/deploy-azure.md` に手順としてまとめ、必要なファイル(`Dockerfile`、設定の環境変数化)を用意すること。

- **構成**:
  - アプリ: **Azure Container Apps**(Dockerfileでコンテナ化。uvicorn で起動)
  - DB: **Azure Database for MySQL Flexible Server**(プライベートアクセス。utf8mb4。ローカルのMySQLからは `mysqldump` で移行)
  - AI: 既存の Azure OpenAI リソースをそのまま利用(接続先は `.env` → App Settings / Key Vault へ)
  - スケジューラ: Container Apps 内の APScheduler をそのまま利用(単一インスタンス縛り)。将来スケールする場合は Azure Functions Timer Trigger へ分離
- **シークレット管理**: Key Vault + Managed Identity。アプリは `AZURE_OPENAI_API_KEY` を Key Vault 参照に切替可能な構造にしておく
- **認証**: Entra ID(簡易認証)をフロントに設定し、社内ユーザーのみアクセス可能に
- **ネットワーク**: Mattermost / GROWI が社内ネットワークにある場合は VNet 統合で到達性を確保(手順書に記載)
- この文書はプロトタイプの接続情報構成をそのまま移行できるよう、**環境変数の一覧と対応表**を必ず含めること

## 11. スコープ外(実装しないこと)

- 多プロジェクト対応(単一プロジェクトの設定のみ)
- ユーザー認証・権限管理(ローカル動作のため。Azure移行時にEntra IDで対応)
- レポートのメール/チャット通知(Mattermostへの投稿は将来拡張)
- GROWIページの自動下書き作成(将来拡張)
- PostgreSQL / pgvector 対応
