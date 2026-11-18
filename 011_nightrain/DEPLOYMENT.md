# Azure Functions デプロイ手順(011_nightrain)

チャット内容自動リマインドサービスを、Azure Functions(Consumptionプラン、Linux、Python 3.11)にデプロイする手順。
デプロイ方式(依存パッケージを同梱したzipをBlobに置き、`WEBSITE_RUN_FROM_PACKAGE` で参照する)は、
分割元の `011_chat_linkage_light/functions/DEPLOYMENT.md` と同じ。

## 前提条件

- Azure CLI(`az`)がインストール済みで、対象サブスクリプションにログイン済みであること
- Windows PowerShell 5.1 が使えること(コマンド例・`build_package.ps1` はWindows PowerShell前提)
- `app/model/reminder_classifier.joblib` があること(無い場合は `011_agenda_tool` で `python -m app.model.export_model` を実行する)
- Azure(Function App)から、Mattermost(`chat.jbdcl.com`)とGROUPSESSION(`gs.jbdcl.com`)にアクセスできること
  (Mattermostは分割元のFunction Appで接続実績あり。GROUPSESSIONは初回デプロイ後の動作確認で必ず確認する)

## 全体の流れ

1. (初回のみ)Azureリソースを作成する
2. (初回のみ)Key Vaultにパスワード・トークンを登録する
3. (初回のみ)アプリケーション設定を登録する
4. `build_package.ps1` でデプロイパッケージ(zip)をビルドする
5. zipをBlob Storageにアップロードし、`WEBSITE_RUN_FROM_PACKAGE` に設定して反映する
6. 動作確認する(最初は `REMIND_DM_USERNAME` でDMに投稿させて確認し、問題なければ本番チャンネルに切り替える)

---

## 1. 初回セットアップ: Azureリソースの作成

以下のリソース名は、2026-11-16 の初回デプロイで実際に作成したもの(サブスクリプション「CRS-PJ」)。
ストレージアカウント名・Function App名・Key Vault名はグローバルで一意である必要がある。

```powershell
$RG = "rg-nightrain"
$LOCATION = "japaneast"
$STORAGE = "stnightrain"
$FUNCAPP = "nightrain-reminder"
$KV = "kv-nightrain"

az group create --name $RG --location $LOCATION

az storage account create `
  --name $STORAGE --resource-group $RG --location $LOCATION `
  --sku Standard_LRS --kind StorageV2

az functionapp create `
  --name $FUNCAPP --resource-group $RG --storage-account $STORAGE `
  --consumption-plan-location $LOCATION `
  --runtime python --runtime-version 3.11 --functions-version 4 --os-type Linux

# デプロイパッケージ置き場のBlobコンテナ
az storage container create --account-name $STORAGE --name deploy --auth-mode key
```

- Consumption(従量課金)プランのため、タイマートリガーの実行時間分のみ課金される
- `az functionapp create` は同名のApplication Insightsも作成する(実行ログ・エラー監視用)
- 監視状態は、同じストレージアカウント(`AzureWebJobsStorage`)のコンテナ `nightrain-state` に保存される(初回実行時に自動作成)


## 2. 初回セットアップ: Key Vaultへのシークレット登録

パスワード・トークンは、アプリケーション設定に平文で書かず、Key Vaultに登録して参照する。

作業するアカウントにロール割り当て(`Microsoft.Authorization/roleAssignments/write`)の権限が無いため、
Key Vaultは **アクセスポリシー方式**(`--enable-rbac-authorization false`)で作成する
(RBAC方式で作成すると、Function App・作業者への権限付与ができない。作成後に方式を切り替えることもできない)。

```powershell
# Key Vault(アクセスポリシー方式)を作成する
az keyvault create --name $KV --resource-group $RG --location $LOCATION --enable-rbac-authorization false

# Function AppにマネージドID(システム割り当て)を付け、Key Vaultのシークレットを読めるようにする
$Principal = az functionapp identity assign --name $FUNCAPP --resource-group $RG --query principalId -o tsv
az keyvault set-policy --name $KV --resource-group $RG --object-id $Principal --secret-permissions get list

# 作業者(ログイン中のアカウント)にシークレットの登録・更新権限を付ける
$Me = az ad signed-in-user show --query id -o tsv
az keyvault set-policy --name $KV --resource-group $RG --object-id $Me --secret-permissions get list set delete
```

シークレットの値は、コマンド履歴に残さないよう **Azure portal の Key Vault →「シークレット」→「生成/インポート」** から登録する
(CLIで登録する場合は、値をコマンド引数に書かず、一時ファイルに書き出して
`az keyvault secret set --vault-name $KV --name <シークレット名> --file <一時ファイル> --encoding utf-8` で登録し、一時ファイルはすぐ削除する)。

| シークレット名 | 値 |
|---|---|
| `mattermost-token` | Mattermostのパーソナルアクセストークン |
| `groupsession-password` | GROUPSESSIONのパスワード |
| `azure-openai-key` | Azure OpenAIのAPIキー |

## 3. 初回セットアップ: アプリケーション設定

各設定の意味は [README.md](README.md) の「アプリケーション設定」を参照。**最初は動作確認のため `REMIND_DM_USERNAME` を設定しておき、DMに投稿させる。**

`az.cmd` は値の中の `&` などを正しく扱えないことがあるため、JSONファイル経由で設定する。

```powershell
$Settings = @{
  # UTCで指定する(JSTの平日 9:00-17:55 に5分ごと)
  POLL_SCHEDULE = "0 */5 0-8 * * 1-5"
  MATTERMOST_URL = "https://chat.jbdcl.com"
  MATTERMOST_TOKEN = "@Microsoft.KeyVault(VaultName=$KV;SecretName=mattermost-token)"
  GROUPSESSION_BASE_URL = "https://gs.jbdcl.com/gsession"
  GROUPSESSION_USERNAME = "<GROUPSESSIONのログインID>"
  GROUPSESSION_PASSWORD = "@Microsoft.KeyVault(VaultName=$KV;SecretName=groupsession-password)"
  AZURE_OPENAI_ENDPOINT = "<Azure OpenAIのエンドポイント>"
  AZURE_OPENAI_KEY = "@Microsoft.KeyVault(VaultName=$KV;SecretName=azure-openai-key)"
  AZURE_OPENAI_DEPLOYMENT = "gpt-5.4-mini"
  WATCH_MATTERMOST_CHANNELS = "JBD社員全体のお知らせ, JBD全体のお知らせ, 全員/拠点などの特定のお知らせ, 社員/拠点などの特定のお知らせ, 東京本社共有"
  WATCH_GROUPSESSION_FORUM_SIDS = "5, 15"
  REMIND_CHANNEL = "雑務連絡"
  REMIND_DM_USERNAME = "r-kinoshita"
  REMINDER_THRESHOLD = "0.7"
  COMPANY_HOLIDAYS = "12-29,12-30,12-31,01-02,01-03,01-04"   # 会社独自の休日(毎年同じ。特定年だけの休日はなし)
  # FOLLOWUP_DM_USERNAME = "r-kinoshita"   # 再リマインドをDMで確認したい場合だけ設定する(2026-11-18 からは未設定=雑務連絡のスレッドに返信)
}
$Json = Join-Path $env:TEMP "nightrain-settings.json"
# チャンネル名に日本語を含むため、BOMなしUTF-8で書き出す(Windows PowerShell 5.1の Out-File はBOM付きになる)
[System.IO.File]::WriteAllText($Json, ($Settings | ConvertTo-Json -Compress), (New-Object System.Text.UTF8Encoding $false))
az functionapp config appsettings set --name $FUNCAPP --resource-group $RG --settings "@$Json"
Remove-Item $Json
```

Key Vault参照が解決できているかは、Azure portal の Function App →「環境変数」で各設定の「ソース」欄が
緑のチェック(Key Vault 参照)になっていることで確認できる。

## 4. デプロイパッケージのビルド

`011_nightrain` ディレクトリで実行する:

```powershell
cd 011_nightrain
.\build_package.ps1
```

- `.build/` にステージングし、依存パッケージ(`requirements.txt`)を Linux 向けに
  `.python_packages/lib/site-packages/` へ事前インストール(vendoring)したうえで、`dist/functions.zip` を生成する
- パッケージに含まれるのは `function_app.py`・`host.json`・`requirements.txt`・`app/`(モデルを含む)のみ。
  `run_local.py`・`local.settings.json`・`.local_state/` は含まれない

## 5. デプロイ(Blobアップロード + WEBSITE_RUN_FROM_PACKAGE設定)

```powershell
$Zip = ".\dist\functions.zip"
# Blob名は毎回変える(同じ名前で上書きすると、変更が反映されたか切り分けにくくなるため)
$BlobName = "functions-$(Get-Date -Format 'yyyyMMddHHmmss').zip"

az storage blob upload `
  --account-name $STORAGE --container-name deploy `
  --name $BlobName --file $Zip --auth-mode key

$Sas = az storage blob generate-sas `
  --account-name $STORAGE --container-name deploy --name $BlobName `
  --permissions r --expiry (Get-Date).AddYears(1).ToString("yyyy-MM-ddTHH:mmZ") `
  --auth-mode key -o tsv
$Url = "https://$STORAGE.blob.core.windows.net/deploy/$BlobName`?$Sas"

# SAS URLには "&" が含まれるため、JSONファイル経由で設定する(--settings KEY="値" だと値が途中で切れる)
$Json = Join-Path $env:TEMP "runfrompkg.json"
(@{ WEBSITE_RUN_FROM_PACKAGE = $Url } | ConvertTo-Json -Compress) | Set-Content -Encoding ascii $Json
az functionapp config appsettings set --name $FUNCAPP --resource-group $RG --settings "@$Json"
Remove-Item $Json

# 設定値が切れずに保存されたかを読み戻して確認する(True になること)
$Saved = az functionapp config appsettings list --name $FUNCAPP --resource-group $RG `
  --query "[?name=='WEBSITE_RUN_FROM_PACKAGE'].value" -o tsv
$Saved -eq $Url

az functionapp restart --name $FUNCAPP --resource-group $RG

# WEBSITE_RUN_FROM_PACKAGE を手動設定した場合はトリガー情報が自動同期されないため、明示的に同期する
$Sub = az account show --query id -o tsv
az rest --method post `
  --uri "/subscriptions/$Sub/resourceGroups/$RG/providers/Microsoft.Web/sites/$FUNCAPP/syncfunctiontriggers?api-version=2022-03-01"
```

関数が認識されたことを確認する(`poll_and_remind` が表示されれば成功):

```powershell
az functionapp function list --resource-group $RG --name $FUNCAPP
```

ホストが起動していること(`state` が `Running`)も確認する:

```powershell
$Key = az functionapp keys list --resource-group $RG --name $FUNCAPP --query "masterKey" -o tsv
Invoke-RestMethod -Uri "https://$FUNCAPP.azurewebsites.net/admin/host/status" -Headers @{ "x-functions-key" = $Key }
```

## 6. 動作確認と本番切り替え

1. `REMIND_DM_USERNAME` を設定した状態で、監視対象チャンネル(またはGROUPSESSIONフォーラム)にリマインド対象になりそうな投稿がされるのを待つ
   (初回実行時は直近 `POLL_OVERLAP_MINUTES` 分の投稿のみが対象)
2. Application Insightsのログで、各監視対象の「取得 N 件 / 未通知 N 件」が出ていること、
   GROUPSESSIONのログイン・取得でエラーが出ていないことを確認する
3. DMにリマインドが届くことを確認する
4. 問題なければ、Azure portal の「環境変数」で `REMIND_DM_USERNAME` を削除(空に)して保存する。以後は `REMIND_CHANNEL` に投稿される
5. 期日前の再リマインドは、`FOLLOWUP_DM_USERNAME` を設定した状態で、DMに届く確認用の投稿(対象者の一覧つき)を確認する。問題なければ `FOLLOWUP_DM_USERNAME` を削除して保存する。以後は1回目のリマインド投稿へのスレッド返信として、対象者をメンションして投稿される

### ログの見方(Application Insights)

```powershell
az monitor app-insights query --app $FUNCAPP --resource-group $RG `
  --analytics-query "union traces, exceptions | order by timestamp desc | take 50" -o json
```

日本語のログが文字化けする場合は、Azure portal の Application Insights →「ログ」で同じクエリを実行する。

## 運用メモ

- **設定変更**: 監視対象・投稿先・しきい値・実行間隔は、Azure portal の Function App →「環境変数」で変更する。保存するとFunction Appが再起動され、次回の実行から反映される(再デプロイは不要)
- **パスワード・トークンの更新**: Key Vaultのシークレットに新しいバージョンを登録する。反映まで最大24時間かかることがあるため、すぐ反映したい場合はFunction Appを再起動する
- **モデルの更新**: `011_agenda_tool` で再学習 → `python -m app.model.export_model` → 「4. ビルド」→「5. デプロイ」
- **一時停止**: Azure portal で Function App を「停止」すれば監視も止まる。再開時は、停止中に確認できなかった期間を、前回確認時刻から続けて取得する
  (長期間停止した後は、その間の投稿のリマインドがまとめて投稿されることがある。避けたい場合は、再開前にBlobコンテナ `nightrain-state` の中身を削除して初回状態に戻す)
- **コスト**: 1回の実行は数秒程度(リマインド対象がある場合は、AI呼び出し分だけ長くなる)。Consumptionプランの無料枠内に収まる想定

## トラブルシューティング(分割元のデプロイで発生した問題のうち、この構成でも起こりうるもの)

| 症状 | 原因・対処 |
|---|---|
| 関数が0件のまま検出されず、`No module named 'app'` が出る | PowerShellの `Compress-Archive` で作ったzipはLinuxでパス区切りが正しく解釈されないことがある。`build_package.ps1`(Pythonの `zipfile` でzip化する)を使う |
| `No module named 'requests'` などの依存パッケージが見つからない | `WEBSITE_RUN_FROM_PACKAGE` を手動設定するとAzure側のビルド(pip install)は行われない。`-SkipVendoring` を付けずにビルドする |
| `pip install` で `UnicodeDecodeError: 'cp932'` | `requirements.txt` に日本語を書かない(コメントも英語にする) |
| `build_package.ps1` がpipの警告で異常終了する | pipの標準エラー出力をPowerShellがエラー扱いするため。スクリプト内でpip実行中のみ `$ErrorActionPreference` を緩和している(変更しない) |
| デプロイ後にタイマーが一切動かず、`/admin/host/status` が503 | `WEBSITE_RUN_FROM_PACKAGE` のSAS URLが `&` で切れている。5章の読み戻し確認で `True` になるか確認する |
| Git Bashから `az` で `/` 始まりの値を設定すると壊れる | MSYSのパス自動変換。PowerShellから実行する |
| `POLL_SCHEDULE` に関するエラーで関数が起動しない | アプリケーション設定 `POLL_SCHEDULE` が未設定。3章の設定を確認する |
| 「アプリケーション設定 XXX が設定されていません」 | 該当の設定が未登録、またはKey Vault参照が解決できていない(「環境変数」画面のソース欄を確認) |
