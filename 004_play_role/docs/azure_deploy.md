# Azure Container Apps へのデプロイ手順

`004_play_role` を Azure Container Apps（Consumption プラン、スケールtoゼロ）にデプロイし、指定したIPアドレスからのみアクセスできるようにする手順です（[010_ai_reviewer/docs/azure_deploy.md](../../010_ai_reviewer/docs/azure_deploy.md) を参考に構成しています）。

## 構成

- リソースグループ: `test20251008`（既存、010_ai_reviewer 等と同居）
- リージョン: `japaneast`
- 作成するリソース:
  - Azure Container Registry: `acrplayrole`
  - Log Analytics ワークスペース: `log-play-role`
  - Container Apps 環境: `cae-play-role`
  - Container App: `ca-play-role`（`minReplicas=0` / `maxReplicas=1`、Ingress にIPアクセス制限）
- Azure OpenAI: 既存のリソースをそのまま利用（ホスティング方式とは独立して従量課金）

## データ永続化について（重要）

`reviewers.csv`（レビュアー一覧）・`data/reviewer_feedback.csv`・`data/reviewer_profile.csv`（フィードバック履歴・記憶）は、コンテナ内のローカルファイルに書き込む実装です。Container Apps はスケールtoゼロ後の再起動でコンテナのローカルファイルが失われるため、**しばらく操作がないと、追加したレビュアーや記憶した内容がリセットされます**。これは方針として許容しています（Blob Storage等への永続化は未対応）。将来的に永続化したい場合は別途相談してください。

## 前提条件

- Azure CLI がインストール・ログイン済みであること（`az account show` で確認）
- 対象サブスクリプションで Contributor 相当の権限があること
- **Docker Desktop は不要**：イメージのビルドは `az acr build`（ACR Tasks によるクラウドビルド）で行うため、ローカルにDockerランタイムは要りません

> 補足: Windows環境の Azure CLI で `containerapp` 拡張機能のインストールに失敗する場合は、010_ai_reviewer と同様に `az deployment group create`（ARMテンプレート）でContainer Apps環境／Container Appを作成してください。

## 初回デプロイ手順

### 1. Azure Container Registry (ACR) の作成

```bash
az acr create --resource-group test20251008 --name acrplayrole --sku Basic --location japaneast
```

### 2. Dockerイメージのビルド＆push（クラウドビルド）

`004_play_role` ディレクトリで実行します。Whisperモデル（small）をビルド時にダウンロードするため、初回ビルドは数分かかります。

```bash
cd 004_play_role
az acr build --registry acrplayrole --image play-role:latest .
```

### 3. ACR管理者ユーザーの有効化・認証情報取得

```bash
az acr update -n acrplayrole --admin-enabled true
az acr credential show -n acrplayrole
```

### 4. デプロイパラメータファイルの作成

`infra/containerapp.parameters.json.example` をコピーして `infra/containerapp.parameters.json` を作成し、以下を埋めます（このファイルは `.gitignore` で管理対象外です。Gitにコミットしないでください）。

- `acrUsername` / `acrPassword`: 手順3で取得した値
- `azureOpenAiEndpoint` / `azureOpenAiKey`: ワークスペースルートの `.env` に記載の値

### 5. Container Apps環境・Container Appのデプロイ

```bash
az deployment group create \
  --resource-group test20251008 \
  --template-file infra/containerapp.json \
  --parameters @infra/containerapp.parameters.json \
  --name play-role-deploy
```

デプロイ完了後、出力の `fqdn` がアプリのURLです。

## IPアクセス制限

`infra/containerapp.json` の `ipSecurityRestrictions` に、以下を許可しています。

| 名前 | IPアドレス | 用途 |
|---|---|---|
| `office` | `221.117.124.90/32` | オフィス（010_ai_reviewer と共通） |
| `vpn` | `122.220.62.58/32` | VPN（010_ai_reviewer と共通） |

初回デプロイ時は動作確認用に検証用PCのIP（`verify-temp` ルール）を一時的に許可していましたが、動作確認完了後（2026/09）に削除済みです。現在は `office` / `vpn` の2件のみ許可されています。

許可リストの確認:

```bash
az containerapp ingress access-restriction list \
  --name ca-play-role --resource-group test20251008
```

新たに一時許可が必要な場合は、以下のように追加・削除できます。

```bash
# 追加
az containerapp ingress access-restriction set \
  --name ca-play-role --resource-group test20251008 \
  --rule-name verify-temp --ip-address <IPアドレス>/32 --action Allow

# 削除
az containerapp ingress access-restriction remove \
  --name ca-play-role --resource-group test20251008 \
  --rule-name verify-temp
```

## 動作確認

1. 許可されたIPからブラウザでアクセスし、以下が動作することを確認
   - 「Whisper 文字起こし」タブでの録音→文字起こし
   - 「音声レビュー」タブでの音声ファイルアップロード→文字起こし
   - 「動画レビュー」タブでの動画アップロード→スライド解析
   - レビュアー追加→「コメントをもらう」でのAIレビュー生成
   - AIレビューカード右上のアイコンから操作マニュアル（別タブ）が開くこと
2. 許可外のIPからはアクセスできない（`403`）ことを確認
3. しばらく操作せずに放置した後、再度アクセスして動作すること（スケールtoゼロからの起動）を確認。初回アクセスはコンテナ起動待ちで数秒〜数十秒かかります

Container Appの状態確認:

```bash
az containerapp show --name ca-play-role --resource-group test20251008 \
  --query "{fqdn:properties.configuration.ingress.fqdn, runningStatus:properties.runningStatus}"
```

ログ確認:

```bash
az containerapp logs show --name ca-play-role --resource-group test20251008 --follow
```

## 更新デプロイ（コード変更を反映する場合）

> `:latest` のように同じタグで再pushしても、Container Apps 側は「image指定に変化がない」と判断して新しいリビジョンを作成しない（＝古いイメージのまま）ことがあります。更新のたびに **タグを変える**（日付や連番など）のが確実です。

```bash
cd 004_play_role
TAG=$(date +%Y%m%d%H%M%S)
az acr build --registry acrplayrole --image play-role:$TAG .
az containerapp update --name ca-play-role --resource-group test20251008 \
  --image acrplayrole.azurecr.io/play-role:$TAG
```

反映確認:

```bash
az containerapp revision list --name ca-play-role --resource-group test20251008 \
  --query "[].{name:name, active:properties.active, image:properties.template.containers[0].image}"
```

## 操作マニュアル（docs/manual.html）の公開

`docs/manual.html` と `docs/images/` は Dockerfile で `COPY docs/ ./docs/` によりイメージに同梱され、アプリ自身が `/docs/manual.html` で配信します（画面右パネル「AIレビュー」見出し右上のアイコンから別タブで開く）。マニュアルを更新したら、通常の更新デプロイ（`az acr build` → `az containerapp update`）でイメージに反映されます。

## リソースの削除（不要になった場合）

```bash
az containerapp delete --name ca-play-role --resource-group test20251008 --yes
az containerapp env delete --name cae-play-role --resource-group test20251008 --yes
az monitor log-analytics workspace delete --workspace-name log-play-role --resource-group test20251008 --yes
az acr delete --name acrplayrole --resource-group test20251008 --yes
```

※ `test20251008` は他プロジェクトのリソースと共有しているため、リソースグループ自体は削除しないでください。
