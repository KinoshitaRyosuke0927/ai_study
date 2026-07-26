# 012_git_linkage デプロイ・動作確認手順書

GitHub上で指定ブランチへのPRマージを検知し、差分をAIで要約してMattermostへ通知するアプリケーションの、
ローカル動作確認手順とAzureへのデプロイ手順をまとめる。

## 全体構成

```
012_git_linkage/
├── .env                    # ローカル(FastAPI)動作確認用の環境変数
├── .env.example             # .envのひな形
├── .funcignore               # Azure Functionsデプロイ時に除外するファイル
├── local.settings.json       # ローカル(Azure Functions)動作確認用の環境変数
├── host.json                  # Azure Functionsランタイム設定
├── function_app.py            # Azure Functionsのエントリポイント(本番用)
├── requirements.txt
├── docs/
│   ├── azure_functions_migration.md   # 移行方針の検討資料
│   └── deployment_guide.md            # 本手順書
└── app/
    ├── main.py                # FastAPIのエントリポイント(ローカル動作確認用)
    ├── webhook_handler.py     # Webhook受信後の共通処理(main.py/function_app.py 両方から呼ばれる)
    ├── github_service.py      # GitHub署名検証・diff取得
    ├── azure_ai_service.py    # Azure OpenAIによるdiff要約
    └── mattermost_service.py  # Mattermost投稿(DM/チャンネル)
```

`webhook_handler.py` にロジックを共通化しているため、ローカル確認(FastAPI)と本番(Azure Functions)で処理内容の差異は発生しない。

---

## 1. 前提条件・必要なツール

| ツール | 用途 | 確認コマンド |
|---|---|---|
| Python 3.11系 | アプリ実行 | `python --version` |
| Azure CLI | Azureリソース操作 | `az --version` |
| Azure Functions Core Tools v4 | ローカルFunctions実行・デプロイ | `func --version` |
| Node.js / npm | Core Toolsのインストールに使用 | `node --version` / `npm --version` |
| ngrok | ローカルサーバーの外部公開(ローカル確認時のみ) | `ngrok version` |

Azure Functions Core Toolsが未導入の場合は以下でインストールする。

```
npm install -g azure-functions-core-tools@4 --unsafe-perm true
```

Azure CLIでは事前に対象サブスクリプションにログインしておく。

```
az login
az account show   # 対象サブスクリプションになっているか確認
```

---

## 2. ローカル環境での動作確認 (FastAPI + ngrok)

コード修正時の簡易確認に使う方法。GitHubの実Webhookを使わず、ローカルPC上で完結させたい場合に利用する。

### 2.1 依存パッケージのインストール

```
pip install -r 012_git_linkage/requirements.txt
```

### 2.2 `.env` の準備

`012_git_linkage/.env.example` を参考に `012_git_linkage/.env` を作成し、以下を設定する。

```
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_KEY=
MATTERMOST_URL=
MATTERMOST_TOKEN=
DEBUG_FLAG=TRUE
MATTERMOST_TARGET_USERNAME=
MATTERMOST_TARGET_CHANNEL=
GITHUB_TOKEN=
GITHUB_WEBHOOK_SECRET=
GITHUB_OWNER=
GITHUB_REPO=
TARGET_BRANCH=
```

`DEBUG_FLAG=TRUE` にしておくと、通知はMattermostのDM(`MATTERMOST_TARGET_USERNAME`宛)に送られる。

### 2.3 FastAPIサーバーの起動

```
python -m uvicorn app.main:app --reload --port 8001 --app-dir 012_git_linkage
```

`http://127.0.0.1:8001/api/health` にアクセスし `{"status":"ok"}` が返ればサーバー起動は成功。

### 2.4 ngrokで外部公開

別ターミナルで以下を実行し、ローカルサーバーをインターネットからアクセス可能にする。

```
ngrok http 8001
```

`Forwarding` 欄に表示されるHTTPS URL（例: `https://xxxx.ngrok-free.app`）を控える。

> ngrokの無料プランはURLが起動のたびに変わるため、再起動した場合はGitHub側Webhookの設定も都度更新する必要がある。

### 2.5 GitHub側Webhookの一時設定

対象リポジトリ（`KinoshitaRyosuke0927/ai_study`）の `Settings > Webhooks` で、確認したいタイミングだけ以下に設定する。

- Payload URL: `https://xxxx.ngrok-free.app/webhook/github`
- Content type: `application/json`
- Secret: `.env` の `GITHUB_WEBHOOK_SECRET` と同じ値
- イベント: `Pull requests` のみ

### 2.6 動作確認

1. 対象ブランチへ向けたテスト用PRを作成し、マージする
2. FastAPIのログにリクエスト受信・処理内容が出力されることを確認
3. Mattermostへ要約メッセージが届くことを確認
4. 確認が終わったらngrok・FastAPIサーバーを停止する（`Ctrl+C`）。ngrokを起動したままにしない

---

## 3. Azureリソースの準備 (初回のみ)

既にAzure上にリソースが存在する場合はこの章は不要。新しい環境に一式作り直す場合の手順。

### 3.1 リソースグループの確認・作成

```
az group show --name <リソースグループ名>
# 存在しない場合
az group create --name <リソースグループ名> --location japaneast
```

### 3.2 ストレージアカウントの作成

Azure Functionsの実行に必須。

```
az storage account create \
  --name <ストレージアカウント名> \
  --resource-group <リソースグループ名> \
  --location japaneast \
  --sku Standard_LRS \
  --kind StorageV2
```

### 3.3 Application Insightsの作成

ログ・エラー監視用。事前に `microsoft.operationalinsights` プロバイダーの登録が必要な場合がある。

```
az extension add --name application-insights --yes

# 未登録の場合のみ
az provider register --namespace microsoft.operationalinsights
az provider show --namespace microsoft.operationalinsights --query "registrationState" -o tsv   # "Registered" になるまで待つ

az monitor app-insights component create \
  --app <Application Insights名> \
  --location japaneast \
  --resource-group <リソースグループ名> \
  --application-type web
```

### 3.4 Function Appの作成

```
az functionapp create \
  --name <Function App名> \
  --resource-group <リソースグループ名> \
  --storage-account <ストレージアカウント名> \
  --consumption-plan-location japaneast \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --os-type Linux \
  --app-insights <Application Insights名>
```

作成直後は「content is published using ... Functions Core Tools」という警告が出るが、コード未デプロイのため正常。

---

## 4. アプリケーション設定 (環境変数) の登録

`.env` の内容をFunction Appの「アプリケーション設定」として登録する。値に日本語（マルチバイト文字）を含む場合の注意点は [6. トラブルシューティング](#6-トラブルシューティング) を参照。

```
az functionapp config appsettings set \
  --name <Function App名> \
  --resource-group <リソースグループ名> \
  --settings \
    "AZURE_OPENAI_ENDPOINT=<値>" \
    "AZURE_OPENAI_KEY=<値>" \
    "MATTERMOST_URL=<値>" \
    "MATTERMOST_TOKEN=<値>" \
    "DEBUG_FLAG=TRUE" \
    "MATTERMOST_TARGET_USERNAME=<値>" \
    "MATTERMOST_TARGET_CHANNEL=<値>" \
    "GITHUB_TOKEN=<値>" \
    "GITHUB_WEBHOOK_SECRET=<値>" \
    "GITHUB_OWNER=<値>" \
    "GITHUB_REPO=<値>" \
    "TARGET_BRANCH=<値>"
```

登録内容の確認（Azure Portal の Function App > 構成 > アプリケーション設定 で見るのが確実。CLI表示は文字化けする場合がある）。

```
az functionapp config appsettings list \
  --name <Function App名> \
  --resource-group <リソースグループ名> \
  -o table
```

---

## 5. コードのデプロイ

`012_git_linkage` ディレクトリで以下を実行する。現状は手動デプロイのみ（GitHub Actions等の自動デプロイは未導入）。

```
cd 012_git_linkage
func azure functionapp publish <Function App名> --python
```

成功すると、末尾に以下のようにFunctionのURLが表示される。

```
Functions in <Function App名>:
    github_webhook - [httpTrigger]
        Invoke url: https://<Function App名>.azurewebsites.net/api/webhook/github
```

### デプロイ後の簡易疎通確認

署名なしリクエストを送り、`401`（署名検証エラー）が返ればコードは正しく動作している。

```
curl -s -o /dev/null -w "status: %{http_code}\n" \
  -X POST "https://<Function App名>.azurewebsites.net/api/webhook/github" \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: ping" \
  -d '{}'
```

---

## 6. GitHub側Webhook設定の更新

対象リポジトリの `Settings > Webhooks` で、Payload URLとSecretをAzure Functions側に合わせる。

- Payload URL: `https://<Function App名>.azurewebsites.net/api/webhook/github`
- Secret: アプリケーション設定に登録した `GITHUB_WEBHOOK_SECRET` と同じ値

保存すると自動的に `ping` イベントが送信されるため、「Recent Deliveries」タブで応答が `200` になっていることを確認する。

---

## 7. エンドツーエンドの動作確認

1. 対象リポジトリで、監視対象ブランチ（例: `main`）へ向けたテスト用PRを作成する
2. PRをマージする
3. Mattermostへ要約メッセージが届くことを確認する
4. 届かない場合は Azure Portal の Function App > 監視 > ログ、または Application Insights の「トランザクション検索」でエラー内容を確認する

---

## 8. トラブルシューティング

### 8.1 アプリケーション設定に日本語を登録した際の文字化け

Windows環境のターミナルからAzure CLIで日本語を含む値を `--settings` に渡すと、コンソールの文字コードの影響で **表示上** 文字化けして見えることがある。この場合、実際に保存されている値が壊れているとは限らない。

確認方法:
- Azure Portal の Function App > 構成 > アプリケーション設定 から実際の値を目視確認する（最も確実）
- 上記で正しく表示されていれば、CLI側の表示崩れのみであり実害はない

### 8.2 デプロイ時に表示されるPythonバージョンの警告

```
Local python version '3.x.x' is different from the version expected for your deployed Function App...
```

ローカルの実行用Pythonとデプロイ先(3.11)のバージョンが異なる場合に出る警告。Azure側はリモートビルド時に3.11環境でパッケージを再インストールするため、通常は無視して問題ない。`ModuleNotFound` 系のエラーが実際に発生した場合のみ、ローカルの仮想環境をPython 3.11に揃えることを検討する。

### 8.3 GitHub Webhookの再送・失敗確認

対象リポジトリの `Settings > Webhooks > (対象Webhook) > Recent Deliveries` から、直近の送信内容とレスポンス（ステータスコード・レスポンスボディ）を確認できる。`Redeliver` ボタンで同じペイロードを再送信できるため、コード修正後の再テストにも使える。

---

## 9. 現行環境の情報 (参考)

| 項目 | 値 |
|---|---|
| リソースグループ | test20251008 |
| ストレージアカウント | howlingstorage |
| Application Insights | howling |
| Function App | howling |
| リージョン | Japan East |
| Function URL | https://howling.azurewebsites.net/api/webhook/github |
| 対象GitHubリポジトリ | KinoshitaRyosuke0927/ai_study |
| 監視対象ブランチ | main |

秘密情報（トークン・Secret等）は本ドキュメントには記載しない。実際の値はAzure Portalのアプリケーション設定、または手元の `.env` を参照すること。
