# Frontier — Azure デプロイ手順(準備)

本プロトタイプでは **実装・準備のみ** を行う。実際のデプロイ実行は利用者が行う。

## 1. 全体構成

| コンポーネント | Azure サービス | 補足 |
|---|---|---|
| アプリ | **Azure Container Apps** | `Dockerfile` でコンテナ化し `uvicorn` で起動 |
| DB | **Azure Database for MySQL Flexible Server** | プライベートアクセス / `utf8mb4`。ローカル MySQL からは `mysqldump` で移行 |
| AI | 既存の **Azure OpenAI** リソース | 接続先は `.env` → App Settings / Key Vault 参照へ |
| スケジューラ | Container Apps 内の **APScheduler** | 単一インスタンス縛り(`min/max replicas = 1`)。将来スケールする場合は Azure Functions Timer Trigger へ分離 |
| シークレット | **Key Vault + Managed Identity** | `AZURE_OPENAI_API_KEY` などを Key Vault 参照へ切替可能 |
| 認証 | **Entra ID(簡易認証 / Easy Auth)** | Container Apps の認証機能で社内ユーザーのみに制限 |
| ネットワーク | **VNet 統合** | Mattermost / GROWI が社内網にある場合に到達性を確保 |

```
[利用者] --(Entra ID)--> [Container Apps: Frontier + APScheduler]
                                   |-- VNet 統合 --> 社内: Mattermost / GROWI
                                   |-- Private Endpoint --> Azure Database for MySQL
                                   |-- HTTPS --> Azure OpenAI / GitHub API / Trello API
                                   |-- Key Vault 参照 --> シークレット
```

## 2. 事前準備

```bash
# 変数(例)
RG=rg-frontier
LOC=japaneast
ACR=acrfrontier$RANDOM
ENVNAME=cae-frontier
APP=frontier
MYSQL=mysql-frontier
KV=kv-frontier

az group create -n $RG -l $LOC
```

## 3. MySQL Flexible Server

```bash
az mysql flexible-server create \
  -g $RG -n $MYSQL -l $LOC \
  --admin-user frontieradmin --admin-password '<STRONG_PASSWORD>' \
  --version 8.0 --tier Burstable --sku-name Standard_B1ms \
  --storage-size 32 --public-access None

# データベース作成(utf8mb4)
az mysql flexible-server db create -g $RG -s $MYSQL -d frontier \
  --charset utf8mb4 --collation utf8mb4_0900_ai_ci
```

### ローカルからのデータ移行

```bash
# ローカル(Windows は MySQL Server 8.0\bin\mysqldump.exe)
mysqldump --single-transaction --default-character-set=utf8mb4 \
  -u frontier -p frontier > frontier_dump.sql

# 移行先へ流し込み(踏み台 or Private Endpoint 経由)
mysql -h $MYSQL.mysql.database.azure.com -u frontieradmin -p \
  --ssl-mode=REQUIRED frontier < frontier_dump.sql
```

## 4. イメージのビルドと push

```bash
az acr create -g $RG -n $ACR --sku Basic
az acr build -r $ACR -t frontier:latest .
```

## 5. Container Apps

```bash
az containerapp env create -g $RG -n $ENVNAME -l $LOC   # 必要に応じ --infrastructure-subnet-resource-id で VNet 統合

az containerapp create -g $RG -n $APP \
  --environment $ENVNAME \
  --image $ACR.azurecr.io/frontier:latest \
  --registry-server $ACR.azurecr.io \
  --target-port 8000 --ingress external \
  --min-replicas 1 --max-replicas 1 \
  --system-assigned \
  --env-vars \
     APP_TZ=Asia/Tokyo APP_RUN_MODE=real \
     APP_SCHEDULE_ENABLED=true "APP_SCHEDULE_CRON=0 9 * * 1" \
     MYSQL_HOST=$MYSQL.mysql.database.azure.com MYSQL_PORT=3306 \
     MYSQL_USER=frontieradmin MYSQL_DATABASE=frontier
```

> `--min-replicas 1 --max-replicas 1` は APScheduler の多重起動を防ぐための単一インスタンス縛り。

### シークレット(Key Vault 参照)

```bash
az keyvault create -g $RG -n $KV
az keyvault secret set --vault-name $KV -n mysql-password    --value '<STRONG_PASSWORD>'
az keyvault secret set --vault-name $KV -n azure-openai-key  --value '<AOAI_KEY>'
az keyvault secret set --vault-name $KV -n github-token      --value '<GH_PAT>'
az keyvault secret set --vault-name $KV -n growi-token       --value '<GROWI_TOKEN>'
az keyvault secret set --vault-name $KV -n trello-token      --value '<TRELLO_TOKEN>'
az keyvault secret set --vault-name $KV -n mattermost-token  --value '<MM_PAT>'

# Container Apps のマネージド ID に Key Vault の参照権限を付与し、
# secretref 経由で環境変数へマウントする
az containerapp secret set -g $RG -n $APP --secrets \
  mysql-password=keyvaultref:https://$KV.vault.azure.net/secrets/mysql-password,identityref:system

az containerapp update -g $RG -n $APP --set-env-vars \
  MYSQL_PASSWORD=secretref:mysql-password \
  AZURE_OPENAI_API_KEY=secretref:azure-openai-key \
  GITHUB_TOKEN=secretref:github-token \
  GROWI_API_TOKEN=secretref:growi-token \
  TRELLO_TOKEN=secretref:trello-token \
  MATTERMOST_TOKEN=secretref:mattermost-token
```

## 6. 認証(Entra ID / Easy Auth)

```bash
az containerapp auth microsoft update -g $RG -n $APP \
  --client-id <APP_REG_CLIENT_ID> \
  --client-secret <APP_REG_SECRET> \
  --tenant-id <TENANT_ID> \
  --allowed-audiences api://<APP_REG_CLIENT_ID>
az containerapp auth update -g $RG -n $APP --action RedirectToLoginPage --require-authentication true
```

社内テナントのユーザーのみアクセス可能になる。エンタープライズ アプリケーションの
「割り当てが必要」設定で、さらに特定グループへ限定できる。

## 7. 環境変数 一覧と対応表(ローカル → Azure)

| `.env`(ローカル) | Azure での設定先 | 備考 |
|---|---|---|
| `APP_TZ` | Container Apps env-var | `Asia/Tokyo` |
| `APP_RUN_MODE` | Container Apps env-var | 本番は `real` |
| `APP_SCHEDULE_ENABLED` | Container Apps env-var | `true` |
| `APP_SCHEDULE_CRON` | Container Apps env-var | `0 9 * * 1` |
| `MYSQL_HOST` | Container Apps env-var | `<server>.mysql.database.azure.com` |
| `MYSQL_PORT` | Container Apps env-var | `3306` |
| `MYSQL_USER` | Container Apps env-var | Flexible Server の管理ユーザー |
| `MYSQL_PASSWORD` | **Key Vault** → `secretref:mysql-password` | |
| `MYSQL_DATABASE` | Container Apps env-var | `frontier` |
| `MATTERMOST_URL` | Container Apps env-var | 社内 URL(VNet 到達性が必要) |
| `MATTERMOST_TOKEN` | **Key Vault** → `secretref:mattermost-token` | |
| `MATTERMOST_CHANNEL_ID` | Container Apps env-var | |
| `GITHUB_TOKEN` | **Key Vault** → `secretref:github-token` | |
| `GITHUB_REPOS` | Container Apps env-var | カンマ区切り |
| `GROWI_URL` | Container Apps env-var | 社内 URL(VNet 到達性が必要) |
| `GROWI_API_TOKEN` | **Key Vault** → `secretref:growi-token` | |
| `GROWI_TARGET_PATHS` | Container Apps env-var | カンマ区切り |
| `TRELLO_API_KEY` | Container Apps env-var | |
| `TRELLO_TOKEN` | **Key Vault** → `secretref:trello-token` | |
| `TRELLO_BOARD_ID` | Container Apps env-var | |
| `AZURE_OPENAI_ENDPOINT` | Container Apps env-var | 既存リソースの URL |
| `AZURE_OPENAI_API_KEY` | **Key Vault** → `secretref:azure-openai-key` | |
| `AZURE_OPENAI_API_VERSION` | Container Apps env-var | |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | Container Apps env-var | 既存デプロイ名 |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | Container Apps env-var | 既存デプロイ名 |

## 8. 起動後の確認

1. `https://<app>.<region>.azurecontainerapps.io/api/health` が `{"status":"ok", ...}` を返す。
2. ダッシュボードの「今すぐ実行」で `real` モードのパイプラインが完走する。
3. `runs` テーブルに `status=success` が記録される。
4. スケジュール実行(月曜 09:00 JST)がログに出る。

## 9. 将来の拡張(本プロトタイプ対象外)

- ベクトル検索のスケール: PostgreSQL + pgvector への移行、または Azure AI Search 併用。
- スケジューラ分離: Azure Functions Timer Trigger 化(複数レプリカ対応)。
- レポートの Mattermost / メール通知、GROWI への下書き自動作成。
