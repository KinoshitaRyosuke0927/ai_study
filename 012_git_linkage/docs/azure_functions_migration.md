# 012_git_linkage の Azure Functions 移行方針

## 背景・目的

現在 `012_git_linkage` はVSCode上でFastAPIサーバーを手動起動し、ngrok経由でGitHub Webhookを受信する構成になっている。
これをAzure上に配置し、常時サーバーを起動せず「マージ発生時のみ処理が動き、終わったら自動的に停止する」構成に移行する。

## 結論: Azure Functions（消費プラン）を採用

| 選択肢 | 起動特性 | 料金 | 判定 |
|---|---|---|---|
| Azure Functions（消費プラン） | リクエスト受信時のみ起動、完了後は自動でスケールイン | 実行回数・実行時間に応じた従量課金（待機中は無料） | ○ 採用 |
| Azure Container Apps（スケールtoゼロ） | リクエスト受信時のみ起動 | 従量課金だがコールドスタートがFunctionsよりやや重い | △ 次点 |
| Azure Batch | ジョブ投入後、プール起動まで数十秒〜分単位 | ジョブ実行時間に応じた課金 | × Webhookの即時応答に不向き |
| App Service（常時起動） | 常時起動 | 起動している間ずっと課金 | × 今回の要件に合わない |

GitHub Webhookは数秒でタイムアウトするため、素早く起動できる「消費プランのAzure Functions」が最適。

## アーキテクチャ

```
GitHub (ai_studyリポジトリ, mainブランチへのPRマージ)
        │ Webhook (HTTPS POST)
        ▼
Azure Functions (HTTPトリガー, 消費プラン)
        │
        ├─ 1. 署名検証 (X-Hub-Signature-256)
        ├─ 2. マージ対象判定 (対象リポジトリ/対象ブランチか)
        ├─ 3. GitHub API から diff・変更ファイル取得
        ├─ 4. Azure OpenAI で差分要約を生成
        └─ 5. Mattermost へ要約メッセージを投稿
        │
        ▼
   処理完了後、自動的にスケールイン(待機状態へ)
```

## コード構成の変更点

既存の `app/github_service.py` / `app/azure_ai_service.py` / `app/mattermost_service.py` のロジックはほぼそのまま流用可能。
変更が必要なのはエントリポイントのみ。

### 現状（FastAPI）

```
012_git_linkage/
├── .env
├── requirements.txt
└── app/
    ├── main.py              # FastAPIエントリポイント (uvicornで起動)
    ├── github_service.py
    ├── azure_ai_service.py
    └── mattermost_service.py
```

### 移行後（Azure Functions, Python v2 プログラミングモデル）

```
012_git_linkage/
├── function_app.py          # Functionsエントリポイント (HTTPトリガー定義)
├── host.json                 # Functionsランタイム設定
├── local.settings.json       # ローカル動作確認用の環境変数(.envの代替、Git管理外)
├── requirements.txt          # azure-functions を追加
└── app/
    ├── github_service.py     # 変更なし
    ├── azure_ai_service.py   # 変更なし
    └── mattermost_service.py # 変更なし
```

`function_app.py` は以下のようなイメージになる（実装時の参考）。

```python
import azure.functions as func
from app import github_service as gh
from app import mattermost_service as mm
from app.azure_ai_service import call_summarize_diff

app = func.FunctionApp()

@app.route(route="webhook/github", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def github_webhook(req: func.HttpRequest) -> func.HttpResponse:
    body = req.get_body()
    signature = req.headers.get("X-Hub-Signature-256")
    event = req.headers.get("X-GitHub-Event")

    if not gh.verify_signature(body, signature):
        return func.HttpResponse(status_code=401)

    if event != "pull_request":
        return func.HttpResponse(status_code=200)

    payload = req.get_json()
    if not gh.is_target_merge_event(payload):
        return func.HttpResponse(status_code=200)

    # 以降、現行main.pyと同じ処理（diff取得 → AI要約 → Mattermost投稿）
    ...
    return func.HttpResponse(status_code=200)
```

`main.py` の `/api/health` エンドポイントはFunctionsには不要（Azure側で稼働状況を監視できるため）。

## 環境変数の扱い

現状の `.env` はAzure上では使わず、**Function Appの「アプリケーション設定」** に同名のキーで登録する。

| キー | 移行方法 |
|---|---|
| `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_KEY` | アプリケーション設定へ登録 |
| `MATTERMOST_URL` / `MATTERMOST_TOKEN` / `MATTERMOST_TARGET_USERNAME` | アプリケーション設定へ登録 |
| `GITHUB_TOKEN` / `GITHUB_WEBHOOK_SECRET` / `GITHUB_OWNER` / `GITHUB_REPO` / `TARGET_BRANCH` | アプリケーション設定へ登録 |

`github_service.py` 等の `os.environ[...]` はそのまま動作する（`load_dotenv` の読み込みはローカル動作確認時のみ機能し、Azure上ではアプリケーション設定が環境変数として自動的に注入されるため無害）。

秘密情報のため、アプリケーション設定への登録はAzure Portal操作かAzure CLIで行い、リポジトリにはコミットしない。

## デプロイ方法

1. Azure上にリソースを作成
   - リソースグループ
   - ストレージアカウント（Functionsの実行に必須）
   - Function App（プラン: 消費(Consumption)、ランタイム: Python）
2. ローカルから `func azure functionapp publish <FunctionApp名>` でデプロイ
   （Azure Functions Core Toolsのインストールが別途必要）
3. デプロイ後、Function Appの「アプリケーション設定」に上記の環境変数を登録
4. Function Appの発行されたURL（`https://<functionapp名>.azurewebsites.net/api/webhook/github`）を控える

## GitHub側Webhook設定の変更

現在ngrokの一時URLを設定しているWebhookのPayload URLを、Function AppのURLに変更する。

- Payload URL: `https://<functionapp名>.azurewebsites.net/api/webhook/github`
- Secret: 現行と同じ（`X9zw0QF12Kc`、または再発行する場合はアプリケーション設定側も同時に更新）

これでngrokは不要になり、ローカルでのサーバー起動作業も不要になる。

## 動作確認の流れ

1. Functionsをローカルで起動できるか確認（`func start`、`local.settings.json` を用いて`.env`相当の値を設定）
2. Azureへデプロイ
3. GitHub側のWebhook設定を新URLに変更
4. `ai_study` リポジトリでテスト用PRを作成し `main` へマージ
5. Mattermostへ要約メッセージが届くことを確認
6. Azure Portalの「監視 > ログ」または Application Insights で実行ログ・エラーの有無を確認

## 想定コスト

消費プランは以下の無料枠が毎月付与されるため、PRマージのたびに数回実行する程度の利用であれば実質無料〜数十円程度に収まる見込み。

- 実行回数: 月100万回まで無料
- 実行時間: 月40万GB秒まで無料

## 未決定・要確認事項

- Function Appの命名規則、配置するAzureリージョン、リソースグループ名
- Application Insightsを有効化してログ・エラー監視をするかどうか
- `GITHUB_WEBHOOK_SECRET` をこのタイミングで再発行するかどうか
- デプロイ手順を手動実行にするか、GitHub Actionsで自動デプロイ化するか（将来的な拡張）
