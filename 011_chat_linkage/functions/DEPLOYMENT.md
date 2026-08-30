# Azure Functions デプロイ手順

`011_chat_linkage` アプリのうち、Mattermostの `/nightrain agenda`・`/nightrain remind` 投稿を
ポーリング検知して自動応答する部分(`app/slash_command_watcher.py` 以下)を、
Azure Functions(Consumptionプラン)にデプロイする手順をまとめる。

**画面UI(`app/main.py`・`app/static/`)はセキュリティ上の理由からAzureには一切配置しない。**
exe配布(PyInstaller)専用。デプロイパッケージにも含めない(`build_package.ps1` が除外する)。

## 前提条件

- Azure CLI(`az`)がインストール済みで、対象サブスクリプションにログイン済みであること
- Windows PowerShell 5.1 が使えること(`build_package.ps1` はWindows PowerShell前提)
- ローカルの `011_chat_linkage/app/model/reminder_classifier/` に学習済みモデル一式が存在すること
  (`config.json`, `model.safetensors`, `tokenizer_config.json`, `training_args.bin`, `vocab.txt`)
- `011_chat_linkage/.env` に接続情報(`MATTERMOST_URL`, `MATTERMOST_TOKEN`, `AZURE_OPENAI_ENDPOINT`,
  `AZURE_OPENAI_KEY`, `GROWI_BASE_URL`, `GROWI_API_TOKEN`)が揃っていること

## 全体の流れ

1. (初回のみ)Azureリソースを作成する
2. (初回のみ)Application Settings・モデルファイルをセットアップする
3. `functions/build_package.ps1` でデプロイパッケージ(zip)をビルドする
4. zipをBlob Storageにアップロードし、`WEBSITE_RUN_FROM_PACKAGE` に設定して反映する
5. 動作確認する

---

## 1. 初回セットアップ: Azureリソースの作成

例(実際に使用したリソース名。名前は適宜変更する。ストレージアカウント名・Function App名は
グローバルで一意である必要がある):

```powershell
$RG = "rg-chat-linkage-nightrain"
$LOCATION = "japaneast"
$STORAGE = "stchatlinkagenr"
$FUNCAPP = "chat-linkage-nightrain"

az group create --name $RG --location $LOCATION

az storage account create `
  --name $STORAGE --resource-group $RG --location $LOCATION `
  --sku Standard_LRS --kind StorageV2

az functionapp create `
  --name $FUNCAPP --resource-group $RG --storage-account $STORAGE `
  --consumption-plan-location $LOCATION `
  --runtime python --runtime-version 3.11 --functions-version 4 --os-type Linux
```

Consumption(従量課金)プランを使うことで、タイマートリガーが実行された時間分のみ課金され、
待機中のコストはほぼ発生しない。`az functionapp create` は同名のApplication Insightsリソースも
自動作成する(実行ログ・エラー監視用、無料枠内でほぼ費用は発生しない想定)。

同じストレージアカウント内に、デプロイパッケージ用・モデルファイル用のBlobコンテナを作成する:

```powershell
az storage container create --account-name $STORAGE --name deploy --auth-mode key
az storage container create --account-name $STORAGE --name models --auth-mode key
```

## 2. 初回セットアップ: Application Settings・モデルファイル

### 2-1. 接続情報(Application Settings)

`011_chat_linkage/.env` の値をそのままApplication Settingsに登録する(平文。より安全にしたい場合は
Azure Key Vault参照に置き換える):

```powershell
az functionapp config appsettings set --name $FUNCAPP --resource-group $RG --settings `
  MATTERMOST_URL="<値>" `
  MATTERMOST_TOKEN="<値>" `
  AZURE_OPENAI_ENDPOINT="<値>" `
  AZURE_OPENAI_KEY="<値>" `
  GROWI_BASE_URL="<値>" `
  GROWI_API_TOKEN="<値>"
```

### 2-2. モデルキャッシュ関連の設定

学習済みモデル(約425MB)はデプロイパッケージに含めない(理由は後述のトラブルシューティング参照)。
Blob Storageの `models` コンテナに配置し、`app/model/predict.py` が初回起動時のみダウンロードして
永続領域(`/home` 配下、Azure Filesでインスタンスをまたいで保持される)にキャッシュする設計になっている。

```powershell
az functionapp config appsettings set --name $FUNCAPP --resource-group $RG --settings `
  MODEL_CACHE_DIR="/home/data/model_cache/reminder_classifier" `
  MODEL_BLOB_CONTAINER="models"
```

**注意(Git Bash利用時)**: Git Bash(MSYS)で `/home/...` のようなPOSIX風パスを引数に渡すと、
自動的に `C:/Program Files/Git/home/...` のようなWindowsパスに変換されてしまうことがある
(詳細は下記トラブルシューティング参照)。Git Bashで実行する場合は `MSYS2_ARG_CONV_EXCL="*"` を
先頭に付けるか、PowerShellから実行すること。

### 2-3. モデルファイルのアップロード

```powershell
$ModelDir = "..\app\model\reminder_classifier"
foreach ($f in "config.json","model.safetensors","tokenizer_config.json","training_args.bin","vocab.txt") {
    az storage blob upload `
      --account-name $STORAGE --container-name models `
      --name "reminder_classifier/$f" `
      --file (Join-Path $ModelDir $f) `
      --auth-mode key --overwrite true
}
```

---

## 3. デプロイパッケージのビルド

`functions` ディレクトリで実行する:

```powershell
cd 011_chat_linkage\functions
.\build_package.ps1
```

- `functions/.build/` にステージングし、依存パッケージ(`requirements.txt`)を
  `.python_packages/lib/site-packages/` に事前インストール(vendoring)したうえで、
  `functions/dist/functions.zip` を生成する。
- `app/main.py`・`app/static/`・学習済みモデル・学習データは自動的に除外される。
- 生成される zip は **1GB近くになる**(torch/transformersを含むため)。

## 4. デプロイ(Blobアップロード + WEBSITE_RUN_FROM_PACKAGE設定)

```powershell
$Zip = "..\functions\dist\functions.zip"
$BlobName = "functions-$(Get-Date -Format 'yyyyMMddHHmmss').zip"

az storage blob upload `
  --account-name $STORAGE --container-name deploy `
  --name $BlobName --file $Zip --auth-mode key

$Sas = az storage blob generate-sas `
  --account-name $STORAGE --container-name deploy --name $BlobName `
  --permissions r --expiry (Get-Date).AddYears(1).ToString("yyyy-MM-ddTHH:mmZ") `
  --auth-mode key -o tsv
$Url = "https://$STORAGE.blob.core.windows.net/deploy/$BlobName`?$Sas"

az functionapp config appsettings set --name $FUNCAPP --resource-group $RG `
  --settings WEBSITE_RUN_FROM_PACKAGE="$Url"

az functionapp restart --name $FUNCAPP --resource-group $RG
```

**重要**: Blob名は毎回変える(タイムスタンプを含める)こと。同じBlob名を使い回して内容だけ
上書きすると、Azure側が変更を検知せず古い内容のまま動き続けることがある(詳細は
トラブルシューティング参照)。

再起動後、関数が正しく認識されるまで数十秒〜数分かかることがある。以下で確認する:

```powershell
az functionapp function list --resource-group $RG --name $FUNCAPP
```

`poll_slash_commands` が一覧に出れば成功。空配列 `[]` の場合は、Application Insightsで
エラーログを確認する(下記「動作確認・ログの見方」参照)。

## 5. 動作確認

Mattermostの `settings.ini` `[slash_watch]` で指定した監視対象(チャンネル・DM)に
`/nightrain agenda` または `/nightrain remind` を投稿し、5分以内(デフォルトのポーリング間隔)に
スレッド返信が来ることを確認する。

### ログの見方(Application Insights)

```powershell
az monitor app-insights query --app $FUNCAPP --resource-group $RG `
  --analytics-query "union traces, exceptions | order by timestamp desc | take 50" -o json
```

日本語の`print()`出力が文字化けする場合、`az`コマンドの出力はUTF-8以外(cp932等)で
保存されていることがあるため、Pythonでデコード時に `errors="replace"` やcp932フォールバックを
試すこと。

### ポーリング間隔の一時変更(動作確認用)

`functions/function_app.py` の `schedule="0 */5 * * * *"` を `schedule="0 */1 * * * *"` 等に
変更し、再ビルド・再デプロイすれば1分間隔になる。確認後は必ず `0 */5 * * * *` に戻すこと。

---

## トラブルシューティング(今回のデプロイで発生した問題と対処)

デプロイ作業で実際に遭遇した問題を、時系列で原因と対処法とともに記録する。同じ問題を
繰り返さないための参考情報。

### 1. 大きなzip(425MB)の直接アップロードで接続が切断される

- **症状**: `az functionapp deploy --src-path <zip>` や `az functionapp deployment source
  config-zip` で、アップロード中に `ConnectionResetError: [WinError 10054]` が発生する。
- **原因**: モデルファイル(425MB)を含む大きなzipを、単一のHTTP POSTで直接アップロードする
  方式(Kudu ZipDeploy)が、ネットワーク環境によっては不安定で失敗する。
- **対処**: 一度Azure Blob Storageへ `az storage blob upload`(チャンク分割・自動リトライ付き)で
  アップロードし、そのBlobのSAS URLを `az functionapp deploy --src-url` に渡す方式に変更した。
  Azure内部でのファイル取得になるため、ローカルの1回の巨大アップロードより格段に安定する。

### 2. `ModuleNotFoundError: No module named 'app'`(zipのパス区切り問題)

- **症状**: デプロイ後、関数が0件のまま検出されず、ログに `No module named 'app'` と出る。
  `sys.path` を明示的に追加しても解決しない。
- **原因**: PowerShellの `Compress-Archive` が生成するzipの内部エントリ名が、Linux上での
  Run From Package展開時に正しくディレクトリとして認識されないケースがあった
  (`os.listdir()` で `app\group_session_service.py` のような、バックスラッシュを含む1つの
  フラットなファイル名として見えてしまう=パス区切りの互換性問題)。
- **対処**: `Compress-Archive` をやめ、Pythonの `zipfile` モジュールで、
  `os.path.relpath(...).replace(os.sep, "/")` により明示的にフォワードスラッシュ区切りの
  エントリ名でzipを作成するようにした(`build_package.ps1` 内の `$zipScript`)。

### 3. `WEBSITE_RUN_FROM_PACKAGE` を手動設定するとOryxビルドがスキップされる

- **症状**: 上記2を解決後、`app` は見つかるようになったが、今度は
  `ModuleNotFoundError: No module named 'dotenv'` のように、`requirements.txt` の依存パッケージが
  見つからないエラーになる。
- **原因**: `az functionapp deploy` にAzure自身が管理するBlobへパッケージをアップロードさせず、
  こちら側で用意した独自のBlob URLを `WEBSITE_RUN_FROM_PACKAGE` に直接設定すると、
  Azure側のOryxビルドパイプライン(`SCM_DO_BUILD_DURING_DEPLOYMENT=true` によるpip install)が
  実行されない。指定したzipの中身がそのまま(pip installされずに)読み取り専用でマウントされるだけになる。
- **対処**: 依存パッケージ(`requirements.txt`)をローカルで事前に `pip install --target` して
  `.python_packages/lib/site-packages/` に同梱(vendoring)し、実行時のビルドが一切不要な
  自己完結型のzipを作る方式にした(`build_package.ps1` の該当ステップ)。

### 4. `requirements.txt` の日本語コメントで `UnicodeDecodeError`

- **症状**: `pip install -r requirements.txt` の実行時に
  `UnicodeDecodeError: 'cp932' codec can't decode byte ...` が発生する。
- **原因**: `requirements.txt` に日本語コメントを書いていたが、ファイルがBOM無しUTF-8だったため、
  pipがWindowsのシステムロケール(cp932)でデコードしようとして失敗した。
- **対処**: `requirements.txt` はコメントも含めてASCII文字のみにした(コメントは英語で記載)。

### 5. `unidic-lite` が `--only-binary=:all:` と競合する

- **症状**: `pip install --platform ... --only-binary=:all: -r requirements.txt` で
  `Could not find a version that satisfies the requirement unidic-lite`。
- **原因**: `unidic-lite` はwheel(バイナリ配布)を提供しておらず、sdist(ソース配布)のみ。
  `--only-binary=:all:` はsdistのインストールを禁止するため失敗する。
- **対処**: 最終的には、`unidic-lite` を `requirements.txt` の残りと**同じ1回の pip install**に
  含めた上で `--only-binary=:all:` を外す形にはせず、実際には他の依存関係と一緒に
  1回のpip呼び出しでインストールする形に整理した(下記6・7とあわせて解決)。

### 6. `torch` が誤ってCUDA同梱版(PyPI版)を掴む

- **症状**: 関数の実行時に
  `ValueError: libcublas.so.*[0-9] not found in the system path` で失敗する。
- **原因**: `torch` は通常のPyPIにもCUDA同梱版が **同じバージョン番号("2.6.0"など)** で
  公開されている。`--extra-index-url https://download.pytorch.org/whl/cpu` を使って
  CPU版の取得を意図しても、pipの解決ロジックにより誤って通常のPyPI版(CUDA同梱・巨大)が
  選ばれることがあり、Azure Functions環境にはCUDAライブラリが存在しないため実行時エラーになる。
- **調査**: `curl https://download.pytorch.org/whl/cpu/torch/` で実際のwheelファイル名を確認したところ、
  CPU版は `torch-2.6.0+cpu-cp311-cp311-linux_x86_64.whl` のように、
  **バージョン名に `+cpu` サフィックスが付き、プラットフォームタグも `manylinux*` ではなく
  `linux_x86_64`** であることが判明した。
- **対処**: `torch==2.6.0+cpu` とバージョンを明示し、`--platform` に
  `manylinux2014_x86_64`(他の依存パッケージ用)と `linux_x86_64`(torch用)の**両方**を
  指定することで、確実にCPU版のみが解決されるようにした。

### 7. 依存パッケージを2回のpip呼び出しに分けると依存関係が衝突する

- **症状**: `torch` を別のpip呼び出し(2回目)で同じ `--target` ディレクトリにインストールすると、
  `Cannot install torch because these package versions have conflicting dependencies`
  (jinja2/MarkupSafe等をめぐる衝突)。
- **原因**: 同じ `--target` ディレクトリに対して複数回に分けて `pip install` すると、
  1回目のインストール結果(dist-info等)と2回目の依存関係解決が正しく整合せず、
  pipの依存解決ロジックが混乱する。
- **対処**: `requirements.txt` の内容と `torch==2.6.0+cpu` を1つのrequirementsファイルにまとめ、
  **1回のpip呼び出し**で(`--index-url` にPyTorch CPU版インデックス、
  `--extra-index-url` に通常のPyPIを指定して)まとめてインストールするようにした。
  `unidic-lite` のみ、sdist配布のみでクロスプラットフォーム指定と併用できない制約のため、
  引き続き別のpip呼び出し(プラットフォーム指定なし、Windows上でビルドしてもLinuxで
  問題なく動く純粋なデータパッケージ)で個別にインストールしている。

### 8. PowerShellの `$ErrorActionPreference = "Stop"` でpipの正常終了が異常終了扱いになる

- **症状**: pipが実際には正常終了(exit code 0)しているのに、
  PowerShellスクリプトが `NativeCommandError` で異常終了する。
- **原因**: pipは「新しいバージョンがあります」等の無害な通知メッセージを標準エラー出力に
  書き込むことがある。Windows PowerShell 5.1では、ネイティブコマンド(pip等)が標準エラー出力に
  何か書き込んだだけで、`$ErrorActionPreference = "Stop"` の下ではそれを終端エラーとして
  扱ってしまう(exit codeとは無関係)、既知の挙動がある。
- **対処**: pip呼び出しの直前で `$ErrorActionPreference = "Continue"` に一時的に緩和し、
  成否は `$LASTEXITCODE` を明示的にチェックして判定するようにした。判定後は
  `$ErrorActionPreference = "Stop"` に戻す。

### 9. MattermostのDMチャンネルで投稿取得が404エラーになる

- **症状**: 実行は成功扱い(`Succeeded`)になるが、DM宛の投稿がいつまでも検知されない。
  ログに `404 Client Error: Not Found for url: https://.../api/v4/teams/` が出続ける。
- **原因**: Mattermostの**DM・グループDMチャンネルは `team_id` が空文字列**になる。
  `app/mattermost_service.py` の `get_channel_posts_in_range()` は、投稿のパーマリンクを
  作るために無条件で `get_team(channel["team_id"])` を呼んでいたため、DMの場合は
  空文字列を渡して404になり、投稿取得自体が例外で失敗していた
  (chat_linkage側のバグ。Azureのデプロイとは無関係な、DM監視固有の不具合)。
- **対処**: `channel["team_id"]` が空の場合は `get_team()` を呼ばず、代わりに
  `get_my_teams()` で取得できる(自分が参加している)いずれかのチーム名を
  パーマリンク生成用に代用するようにした。

### 10. Git Bashのパス自動変換でアプリ設定値が壊れる

- **症状**: `/nightrain remind` 実行時に `[Errno 13] Permission denied: 'C:'` というエラーが出る。
- **原因**: `az functionapp config appsettings set --settings MODEL_CACHE_DIR=/home/data/...`
  という**Git Bash(MSYS)経由のコマンド**を実行した際、MSYSが `/home/data/...` を
  POSIXパスと誤認識し、自動的にWindowsパス
  `C:/Program Files/Git/home/data/model_cache/reminder_classifier` に変換してしまっていた。
  結果としてFunction App(Linux)上でモデルキャッシュ先が `C:/Program Files/Git/...` という
  存在しないWindowsパスになり、その親ディレクトリ作成時に(ルート直下の `C:` を
  作ろうとして)権限エラーになっていた。
- **対処**: `MSYS2_ARG_CONV_EXCL="*"` を付けてMSYSのパス変換を無効化するか、
  Windows PowerShellから実行することで、値をそのまま(`/home/data/...`)渡すようにした。
  **教訓**: Git Bashから `az` コマンド等でPOSIX風の値(`/`で始まる文字列)を渡す場合は、
  意図しないパス変換が起きていないか、設定後に必ず値を読み戻して確認すること。

### 11. `WEBSITE_RUN_FROM_PACKAGE` の更新が反映されないように見えた(実際はビルド未実施が原因)

- **症状**: 同じBlob名を使い回して中身だけ差し替えても、デプロイ結果(関数の挙動)が
  変わらないように見えた。
- **原因**: 前述の3と関連するが、根本原因は「Oryxビルドがそもそも実行されていなかった」
  ことであり、キャッシュの問題ではなかった。ただし切り分けの過程で、念のため
  **Blob名にタイムスタンプを含めて毎回変える**運用にしておくと、こうした切り分けが
  容易になる(本手順書のデプロイ手順もこの方式を採用している)。

---

## 運用メモ

- **コスト**: Consumptionプランのため、タイマートリガーの実行時間分のみ課金される
  (1回1〜2秒程度、5分間隔)。ほぼ無視できるレベル。Application Insightsも無料枠内。
- **モデルの初回ダウンロード**: Function Appのインスタンスが新規起動(コールドスタート)した
  際、`/home/data/model_cache/reminder_classifier` にモデルファイルが無ければBlobから
  自動ダウンロードする。`/home` はAzure Filesでインスタンスをまたいで永続化されるため、
  通常は初回デプロイ後の最初の1回のみダウンロードが発生する。
- **再デプロイの簡易手順**: コード変更のみの場合は「3. ビルド」→「4. デプロイ」を
  繰り返せばよい(Azureリソース自体の再作成は不要)。
