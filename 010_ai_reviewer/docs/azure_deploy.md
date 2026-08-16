# Azure Container Apps へのデプロイ手順

`010_ai_reviewer` を Azure Container Apps（Consumption プラン、スケールtoゼロ）にデプロイし、指定したIPアドレスからのみアクセスできるようにする手順です。

## 構成

- リソースグループ: `test20251008`（既存、既に他プロジェクトのリソースと同居）
- リージョン: `japaneast`
- 作成するリソース:
  - Azure Container Registry: `acraireviewer`
  - Log Analytics ワークスペース: `log-ai-reviewer`
  - Container Apps 環境: `cae-ai-reviewer`
  - Container App: `ca-ai-reviewer`（`minReplicas=0` / `maxReplicas=1`、Ingress にIPアクセス制限）
- Azure OpenAI: 既存のリソースをそのまま利用（ホスティング方式とは独立して従量課金）

現在デプロイ済みのURL: `https://ca-ai-reviewer.greentree-4bae97a2.japaneast.azurecontainerapps.io`
（許可されたIPアドレス以外からは `403` で拒否されます）

## 前提条件

- Azure CLI がインストール・ログイン済みであること（`az account show` で確認）
- 対象サブスクリプションで Contributor 相当の権限があること
- **Docker Desktop は不要**：イメージのビルドは `az acr build`（ACR Tasks によるクラウドビルド）で行うため、ローカルにDockerランタイムは要りません

> 補足: このリポジトリで検証した際、Windows環境の Azure CLI に `containerapp` 拡張機能を追加しようとすると、Python環境（Rust/`_ctypes`関連）の問題でインストールに失敗しました。そのため、Container Apps環境／Container App の作成には `az containerapp` コマンドではなく、`az deployment group create`（ARMテンプレート）を使っています。`containerapp` 拡張機能が正常にインストールできる環境であれば `az containerapp` コマンドで同等の操作が可能です。

## 初回デプロイ手順

### 1. Azure Container Registry (ACR) の作成

```bash
az acr create --resource-group test20251008 --name acraireviewer --sku Basic --location japaneast
```

### 2. Dockerイメージのビルド＆push（クラウドビルド）

`010_ai_reviewer` ディレクトリで実行します。

```bash
cd 010_ai_reviewer
az acr build --registry acraireviewer --image ai-reviewer:latest .
```

### 3. ACR管理者ユーザーの有効化・認証情報取得

Container App からイメージをpullするための認証情報です。

```bash
az acr update -n acraireviewer --admin-enabled true
az acr credential show -n acraireviewer
```

### 4. デプロイパラメータファイルの作成

`infra/containerapp.parameters.json.example` をコピーして `infra/containerapp.parameters.json` を作成し、以下を埋めます（このファイルは `.gitignore` で管理対象外です。Gitにコミットしないでください）。

- `acrUsername` / `acrPassword`: 手順3で取得した値
- `azureOpenAiEndpoint` / `azureOpenAiKey`: ワークスペースルートの `.env` に記載の値

### 5. Container Apps環境・Container Appのデプロイ

`infra/containerapp.json`（ARMテンプレート）を使ってデプロイします。Log Analyticsワークスペース・Container Apps環境・Container Appを一括で作成します。

```bash
az deployment group create \
  --resource-group test20251008 \
  --template-file infra/containerapp.json \
  --parameters @infra/containerapp.parameters.json \
  --name ai-reviewer-deploy
```

デプロイ完了後、出力の `fqdn` がアプリのURLです。

## 動作確認

1. 許可されたIP（オフィス: `221.117.124.90` / VPN: `122.220.62.58`）からブラウザでアクセスし、PPTXアップロード→レビュー→修正方針→想定質問の一連が動作することを確認
2. 日本語を含むスライドで、変換後の画像に文字化け（tofu）が出ていないことを確認
3. 許可外のIPからはアクセスできない（`403`）ことを確認
4. しばらく操作せずに放置した後、再度アクセスして動作すること（スケールtoゼロからの起動）を確認。初回アクセスはコンテナ起動待ちで数秒〜数十秒かかります

Container Appの状態確認:

```bash
az containerapp show --name ca-ai-reviewer --resource-group test20251008 \
  --query "{fqdn:properties.configuration.ingress.fqdn, runningStatus:properties.runningStatus}"
```

ログ確認:

```bash
az containerapp logs show --name ca-ai-reviewer --resource-group test20251008 --follow
```

## 更新デプロイ（コード変更を反映する場合）

> `:latest` のように同じタグで再pushしても、Container Apps 側は「image指定に変化がない」と判断して新しいリビジョンを作成しない（＝古いイメージのまま）ことがあります。更新のたびに **タグを変える**（日付や連番など）のが確実です。

```bash
cd 010_ai_reviewer
TAG=$(date +%Y%m%d%H%M%S)
az acr build --registry acraireviewer --image ai-reviewer:$TAG .
az containerapp update --name ca-ai-reviewer --resource-group test20251008 \
  --image acraireviewer.azurecr.io/ai-reviewer:$TAG
```

反映確認:

```bash
az containerapp revision list --name ca-ai-reviewer --resource-group test20251008 \
  --query "[].{name:name, active:properties.active, image:properties.template.containers[0].image}"
```

## レビュー観点CSV（review_point.csv / pp_check_points.csv）の内容を更新したい場合

このアプリでは `review_point.csv` / `pp_check_points.csv` を**Dockerイメージに焼き込む方式**（永続化なし）を採用しています。そのため、画面の「レビュー観点設定」でON/OFFを変更してもコンテナ再起動で元に戻ります。**観点の内容自体（項目の追加・文言変更・デフォルトのON/OFF）を恒久的に変えたい場合は、CSVファイルを編集してから再デプロイする**必要があります。

1. `010_ai_reviewer/review_point.csv`（資料内容の観点）または `010_ai_reviewer/pp_check_points.csv`（資料デザインの観点）をローカルで編集する
2. 上記「更新デプロイ（コード変更を反映する場合）」と同じ手順でイメージを再ビルド・再デプロイする（CSVはDockerfileで `COPY` されているため、イメージに新しい内容が反映されます）

```bash
cd 010_ai_reviewer
# review_point.csv / pp_check_points.csv を編集した後
TAG=$(date +%Y%m%d%H%M%S)
az acr build --registry acraireviewer --image ai-reviewer:$TAG .
az containerapp update --name ca-ai-reviewer --resource-group test20251008 \
  --image acraireviewer.azurecr.io/ai-reviewer:$TAG
```

3. デプロイ後、ブラウザで「レビュー観点設定」画面を開き、変更した内容が反映されていることを確認する

> 画面上のON/OFF変更を「保存」した状態を永続化したい（コンテナ再起動後も維持したい）場合は、今回のデプロイ方式では対応できません。その場合は Azure Files 等の永続ストレージを追加する構成変更が必要になるので、別途相談してください。

## IPアクセス制限の変更

許可するIPアドレスを追加・変更したい場合は、`infra/containerapp.json` の `ipSecurityRestrictions` を編集して手順5のデプロイコマンドを再実行するか、以下のように直接更新します。

```bash
az containerapp ingress access-restriction set \
  --name ca-ai-reviewer --resource-group test20251008 \
  --rule-name office --ip-address 221.117.124.90/32 --action Allow
```

## リソースの削除（不要になった場合）

```bash
az containerapp delete --name ca-ai-reviewer --resource-group test20251008 --yes
az containerapp env delete --name cae-ai-reviewer --resource-group test20251008 --yes
az monitor log-analytics workspace delete --workspace-name log-ai-reviewer --resource-group test20251008 --yes
az acr delete --name acraireviewer --resource-group test20251008 --yes
```

※ `test20251008` は他プロジェクトのリソースと共有しているため、リソースグループ自体は削除しないでください。

## 操作マニュアル（docs/user_manual.html）の公開

アプリ本体とは別に、操作マニュアル（`docs/user_manual.html` と `docs/images/`）を **Azure Blob Storage の静的Webサイトホスティング機能** で公開しています。マニュアルはIPアクセス制限をかけず、誰でも閲覧できるようにしています。

- ストレージアカウント: `staireviewerdocs`（`test20251008` / `japaneast`）
- 公開URL: `https://staireviewerdocs.z11.web.core.windows.net/`
- IPアクセス制限: ストレージアカウントのネットワークファイアウォールで、アプリ本体と同じ `221.117.124.90`（オフィス）・`122.220.62.58`（VPN）のみ許可し、それ以外は拒否する設定にしています

コンテナ（Container Apps）を使わず、Blob Storageの`$web`コンテナに直接ファイルを置く方式のため、コンピューティング費用がかからず非常に低コストです。

### 初回セットアップ

```bash
az storage account create \
  --name staireviewerdocs --resource-group test20251008 \
  --location japaneast --sku Standard_LRS --kind StorageV2 \
  --allow-blob-public-access true

az storage blob service-properties update \
  --account-name staireviewerdocs \
  --static-website --index-document user_manual.html

# IPアクセス制限（アプリ本体と同じ許可IP）
az storage account update \
  --name staireviewerdocs --resource-group test20251008 \
  --default-action Deny --bypass AzureServices
az storage account network-rule add \
  --account-name staireviewerdocs --resource-group test20251008 \
  --ip-address 221.117.124.90
az storage account network-rule add \
  --account-name staireviewerdocs --resource-group test20251008 \
  --ip-address 122.220.62.58
```

### マニュアル更新時のアップロード手順

`docs/user_manual.html` やスクリーンショット（`docs/images/`）を更新した場合、以下で再アップロードします。

```bash
cd 010_ai_reviewer/docs
az storage blob upload \
  --account-name staireviewerdocs --container-name '$web' \
  --name user_manual.html --file user_manual.html \
  --content-type "text/html; charset=utf-8" --auth-mode key --overwrite

az storage blob upload-batch \
  --account-name staireviewerdocs --destination '$web/images' \
  --source images --auth-mode key --overwrite
```

## レビュー結果の共有リンク機能用ストレージ

「共有する」ボタンで発行するレビュー結果のスナップショットは、専用のBlob Storageに保存しています。

- ストレージアカウント: `staireviewershare`（`test20251008` / `japaneast`、`--allow-blob-public-access false`）
- コンテナ: `shares`（非公開・匿名アクセス不可）
- 保存データはBlob Storageに直接アクセスできず、**Container App（アプリ本体）が接続文字列を使って読み書きする経路のみ**のため、このストレージアカウントにはIPファイアウォールを設定していません（アプリ側のIP制限が実質的なアクセス制御になっています）
- 発行から**30日経過したデータはライフサイクル管理ポリシーで自動削除**されます

### 初回セットアップ

```bash
az storage account create --name staireviewershare --resource-group test20251008 \
  --location japaneast --sku Standard_LRS --kind StorageV2 --allow-blob-public-access false

az storage container create --account-name staireviewershare --name shares --public-access off

# 30日経過後に自動削除するライフサイクルポリシー
az storage account management-policy create --account-name staireviewershare --resource-group test20251008 \
  --policy '{"rules":[{"name":"delete-old-shares","type":"Lifecycle","definition":{
    "filters":{"blobTypes":["blockBlob"],"prefixMatch":["shares/"]},
    "actions":{"baseBlob":{"delete":{"daysAfterModificationGreaterThan":30}}}}}]}'

# 接続文字列を取得し、infra/containerapp.parameters.json の shareStorageConnectionString に設定
az storage account show-connection-string --name staireviewershare --resource-group test20251008
```

接続文字列を `infra/containerapp.parameters.json` に反映したら、「Container Apps環境・Container Appのデプロイ」の手順（`az deployment group create`）を再実行してください。

### 共有データの手動削除・確認

```bash
# 保存されている共有データの一覧
az storage blob list --account-name staireviewershare --container-name shares --auth-mode key --output table

# 特定の共有を即時削除したい場合（30日を待たず削除）
az storage blob delete --account-name staireviewershare --container-name shares \
  --name "<share_id>.json" --auth-mode key
```
