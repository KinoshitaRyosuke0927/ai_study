# Azure へのデプロイ手順

AI学習ポータル(`016_ai_learning_portal`)を Azure Container Apps(従量課金・0台まで縮小)と
Azure Database for MySQL(フレキシブルサーバー)にデプロイする手順です。構成・命名・IP 制限は
`010_ai_reviewer`(`010_ai_reviewer/docs/azure_deploy.md`)に合わせています。

> 2026-10-20 にこの手順でデプロイしました。実施時の状況は末尾の「デプロイの記録」を参照してください。
> デプロイしたアカウントには**ロールの割り当て権限が無かった**ため、DB の自動起動・停止は無効のまま運用しています
> (DB は手動で起動・停止。「自動起動・停止を有効にする」の手順で後から有効にできます)。

## 構成

| リソース | 名前 | 備考 |
|---|---|---|
| リソースグループ | `test20251008`(既存) | 010 と共用。**リソースグループ自体は削除しない** |
| リージョン | `japaneast` | |
| Azure Container Registry | `acrailearningportal` | イメージ `ai-learning-portal:<タグ>` |
| Log Analytics ワークスペース | `log-ai-learning-portal` | |
| Container Apps 環境 | `cae-ai-learning-portal` | |
| Container App | `ca-ai-learning-portal` | `minReplicas=0` / `maxReplicas=1`。Ingress に IP 制限 |
| Container Apps ジョブ | `caj-ai-learning-portal-db-stop` | 15 分ごとに「一定時間使われていなければ DB を停止」 |
| Azure Database for MySQL | `mysql-ai-learning-portal` | フレキシブルサーバー / Burstable B1ms / MySQL 8.0 |
| Azure OpenAI | 既存(010 と同じリソース) | `gpt-6-luna`(構成案・下書きとも) |

IP 制限(010 と同じ社内ネットワーク):オフィス `221.117.124.90` / VPN `122.220.62.58`

### DB の起動・停止の考え方(開発中)

- DB は普段は**停止**しておく。停止中にアクセスがあると、アプリがマネージド ID で DB を起動し、
  画面に「データベースを起動しています」を表示する(起動まで数分。起動後に自動で再読み込み)。
- ジョブ `caj-ai-learning-portal-db-stop` が 15 分ごとに最終アクセス日時を確認し、
  **60 分**(`DB_IDLE_STOP_MINUTES`)使われていなければ DB を停止する。
- フレキシブルサーバーは、停止してから **30 日たつと自動で起動**する(Azure の仕様)。その場合もジョブが止める。
- 将来 9:00〜18:00 の時間指定に切り替える手順は「時間指定の起動・停止への切り替え」を参照。

### 費用の目安

- Container App / ジョブ:動いている時間だけ課金(サブスクリプションごとの月の無料枠あり)。
- MySQL:**起動している時間のコンピューティング料金 + ストレージ料金(停止中も発生)**。
- ACR(Basic)・Log Analytics:少額の固定費。
- 正確な金額は Azure の料金計算ツールで確認すること。

## 前提条件

- Azure CLI がインストール・ログイン済み(`az account show` で確認)
- 対象サブスクリプションで共同作成者(Contributor)相当の権限
- 手順 7(マネージド ID への権限付与)には、**ロールの割り当てができる権限**(所有者、またはユーザー アクセス管理者)が必要
- ローカルに MySQL クライアント(`mysql` コマンド。データの登録に使う)
- Docker Desktop は不要(`az acr build` でクラウドビルドする)

> Windows の Azure CLI では `containerapp` 拡張機能のインストールに失敗することがあるため(010 で確認済み)、
> Container Apps の作成は `az deployment group create`(ARM テンプレート `infra/containerapp.json`)で行います。

以下のコマンドは Git Bash を想定しています。変数を先に設定しておきます。

```bash
RG=test20251008
LOC=japaneast
ACR=acrailearningportal
MYSQL=mysql-ai-learning-portal
```

## 初回デプロイ手順

### 1. Azure Container Registry の作成

```bash
az acr create --resource-group $RG --name $ACR --sku Basic --location $LOC
az acr update -n $ACR --admin-enabled true
az acr credential show -n $ACR        # username / password をパラメータファイルに使う
```

### 2. イメージのビルド(クラウドビルド)

`016_ai_learning_portal/` で実行します(フロントエンドのビルドも Dockerfile の中で行われます)。

```bash
cd 016_ai_learning_portal
TAG=$(date +%Y%m%d%H%M%S)
az acr build --registry $ACR --image ai-learning-portal:$TAG .
echo $TAG                             # パラメータファイルの imageName に使う
```

### 3. MySQL フレキシブルサーバーの作成

```bash
az mysql flexible-server create \
  --resource-group $RG --name $MYSQL --location $LOC \
  --tier Burstable --sku-name Standard_B1ms --storage-size 20 --version 8.0.21 \
  --admin-user alpadmin --admin-password '<管理者パスワード>' \
  --public-access 0.0.0.0
```

- `--public-access 0.0.0.0` は「Azure のサービスからの接続を許可」する設定です。Container Apps(従量課金)の
  送信元 IP は固定されないため、この設定で接続させます(接続は TLS 必須・パスワード認証)。
- 初期データの登録のため、社内ネットワークからの接続も許可します(登録後は削除して構いません)。

```bash
az mysql flexible-server firewall-rule create -g $RG -n $MYSQL --rule-name office \
  --start-ip-address 221.117.124.90 --end-ip-address 221.117.124.90
az mysql flexible-server firewall-rule create -g $RG -n $MYSQL --rule-name vpn \
  --start-ip-address 122.220.62.58 --end-ip-address 122.220.62.58
```

### 4. データベース・アプリ用ユーザの作成とデータの登録

管理者ユーザで接続し、データベースとアプリ用ユーザを作ります(Azure では接続元が localhost ではないため、ユーザは `'%'` で作ります)。

```bash
mysql -h $MYSQL.mysql.database.azure.com -u alpadmin -p --ssl-mode=REQUIRED
```

```sql
CREATE DATABASE ai_learning_portal CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER 'ai_learning_portal'@'%' IDENTIFIED BY '<アプリ用パスワード>';
GRANT ALL PRIVILEGES ON ai_learning_portal.* TO 'ai_learning_portal'@'%';
FLUSH PRIVILEGES;
```

現在のデータ(テーブル定義・サンプル講座・サンプルユーザ)を登録します(`db/README.md` のダンプを使います)。

```bash
mysql -h $MYSQL.mysql.database.azure.com -u alpadmin -p --ssl-mode=REQUIRED \
  --default-character-set=utf8mb4 ai_learning_portal < db/02_schema_and_data.sql
```

> ダンプには Alembic の版数も含まれるため、コンテナ起動時の `alembic upgrade head` は必要な分だけを適用します。
> サンプルユーザ(`admin` / `learner01`)のパスワードは `db/README.md` に記載しています。**公開前に必ず変更**してください
> (デプロイ後に管理者でログインし、「管理 › メンバー管理」から変更できます)。

### 5. パラメータファイルの作成

> 秘密情報(MySQL の管理者・アプリ用パスワード、`APP_SECRET_KEY`)は `infra/.env.azure`(`.gitignore` 済み)に控えておきます。

`infra/containerapp.parameters.json.example` をコピーして `infra/containerapp.parameters.json` を作り、値を埋めます
(このファイルは `.gitignore` 済み。**Git にコミットしない**)。

| パラメータ | 値 |
|---|---|
| `acrUsername` / `acrPassword` | 手順 1 の `az acr credential show` の値 |
| `imageName` | `acrailearningportal.azurecr.io/ai-learning-portal:<手順 2 のタグ>` |
| `appSecretKey` | `python -c "import secrets; print(secrets.token_urlsafe(48))"` の出力 |
| `mysqlPassword` | 手順 4 のアプリ用パスワード |
| `azureOpenAiEndpoint` / `azureOpenAiKey` | リポジトリ直下の `.env` の値(010 と同じ) |

IP 制限・DB 自動停止までの時間(`dbIdleStopMinutes`)・ジョブの実行間隔(`idleStopCron`)・モデル名は、
テンプレートの既定値を変える場合だけ指定します。

手順 7(ロールの割り当て)ができない場合は、次の 2 つを `false` にします(自動起動・停止を使わない構成)。

| パラメータ | 内容 |
|---|---|
| `dbAutostartEnabled` | 停止中の DB をアプリが起動するか(`false` なら停止中は「データベースに接続できません」と表示) |
| `deployIdleStopJob` | 使われていない DB を停止するジョブを作るか |

### 6. Container Apps 環境・Container App・DB 自動停止ジョブのデプロイ

```bash
az deployment group create \
  --resource-group $RG \
  --template-file infra/containerapp.json \
  --parameters @infra/containerapp.parameters.json \
  --name ai-learning-portal-deploy \
  --query "properties.outputs"
```

出力の `fqdn` がアプリの URL、`appPrincipalId` が手順 7 で使うアプリのマネージド ID です。
ジョブのマネージド ID は次で取得します(`deployIdleStopJob` が `true` の場合のみ)。

```bash
az resource show -g $RG -n caj-ai-learning-portal-db-stop --resource-type Microsoft.App/jobs --query identity.principalId -o tsv
```

### 7. マネージド ID に DB を操作する権限を付ける

アプリ(停止中の DB を起動する)とジョブ(使われていない DB を停止する)が、MySQL サーバーを操作できるようにします。
**ロールの割り当てができる権限が必要**です(無い場合は、権限を持つ人に依頼してください)。

```bash
MYSQL_ID=$(az mysql flexible-server show -g $RG -n $MYSQL --query id -o tsv)
az role assignment create --assignee-object-id <appPrincipalId> --assignee-principal-type ServicePrincipal \
  --role "Contributor" --scope $MYSQL_ID
az role assignment create --assignee-object-id <jobPrincipalId> --assignee-principal-type ServicePrincipal \
  --role "Contributor" --scope $MYSQL_ID
```

> 権限の範囲は、この MySQL サーバー1台だけです。より絞りたい場合は、`Microsoft.DBforMySQL/flexibleServers/read` /
> `start/action` / `stop/action` だけを持つカスタムロールを作って割り当ててください。

### 8. 動作確認

1. 許可された IP からアプリの URL を開き、サンプルユーザでログインできる。
2. 講座の受講(例題の実行・演習の採点・小テスト)ができる。
3. 管理 › 講座を作成 › 「題材から AI で作成」で構成案が作れる(Azure OpenAI への接続確認)。
4. 許可外の IP からは `403` になる。
5. DB を止めてからアクセスし、「データベースを起動しています」が表示され、数分後に使えるようになる。

```bash
az mysql flexible-server stop -g $RG -n $MYSQL      # 停止してから 5 を確認する
```

6. DB 自動停止ジョブを手動で実行し、ログで判定結果を確認する(直前に使っていれば「停止しません」と出る)。

```bash
az containerapp job start -g $RG -n caj-ai-learning-portal-db-stop    # 拡張機能が使えない場合はポータルから「今すぐ実行」
```

> Windows の Azure CLI は、`az acr build` のログ表示で文字コードのエラー(cp932)になることがあります。
> その場合も Azure 側のビルドは続いているため、`az acr task list-runs -r $ACR --top 1 -o table` で結果を確認します。
> 事前に `export PYTHONIOENCODING=utf-8` を設定すると避けられます。

7. 確認が終わったら DB を停止しておく(開発中は停止が基本)。

## 更新デプロイ

同じタグで再 push すると新しいリビジョンが作られないことがあるため、**更新のたびにタグを変えます**(010 と同じ)。

```bash
cd 016_ai_learning_portal
TAG=$(date +%Y%m%d%H%M%S)
az acr build --registry $ACR --image ai-learning-portal:$TAG .
```

**テーブル定義の変更(Alembic のマイグレーション)を含む場合は、先に DB を起動**してください。
コンテナは起動時に `alembic upgrade head` を実行しますが、DB が停止中だとスキップして起動します。

```bash
az mysql flexible-server start -g $RG -n $MYSQL     # マイグレーションを含む場合のみ(起動まで数分)
```

イメージを差し替えます。`infra/containerapp.parameters.json` の `imageName` を新しいタグにして手順 6 のコマンドを
再実行します(アプリとジョブの両方が新しいイメージになります)。`az containerapp` 拡張機能が使える環境では次でも構いません。

```bash
az containerapp update -g $RG -n ca-ai-learning-portal --image $ACR.azurecr.io/ai-learning-portal:$TAG
az containerapp job update -g $RG -n caj-ai-learning-portal-db-stop --image $ACR.azurecr.io/ai-learning-portal:$TAG
```

ログでマイグレーションが適用されたことを確認します(`[start] DB に接続できないため…` が出ていないこと)。

```bash
az containerapp logs show -g $RG -n ca-ai-learning-portal --follow
```

## 運用メモ

- **AI の下書き作成中にアプリが止まった場合**:Container App はアクセスが無くなって約 5 分たつと 0 台に縮小するため、
  下書き作成のページを閉じたまま放置すると作成が止まることがあります。止まったジョブは次の起動時に「中断」になり、
  進捗ページの「続きから再開」で残り(中身の無い単元・小テスト)だけを作れます。
- **AI 呼び出しの記録**:プロンプトと応答は `ai_generations` テーブルに残ります(プロンプトの版番号つき)。
  精度改善の検討に使います。
- **DB の手動操作**:`az mysql flexible-server start|stop|show -g $RG -n $MYSQL --query state`。
- **ユーザ管理**:管理者でログインし「管理 › メンバー管理」から行います(コンテナ内で CLI を使う必要はありません)。

## 講座の画像の保存先(次回のデプロイまでに対応)

講座の画像(講座エディタの「画像」、講座フォルダの `images/`)は、ローカルでは `backend/var/images` に保存している
(設定 `IMAGE_STORE=local`)。Container Apps のコンテナ内のファイルは再起動で消えるため、Azure では
**Azure Blob Storage** に保存する(ユーザ決定 2026-10-25)。次回のデプロイ時に次を行う。

1. ストレージアカウントとコンテナ(例:`stailearningportal` / `course-images`)を作成する。非公開(匿名アクセスなし)にする。
   画像はアプリ経由で配信し、下書き講座の画像は作成者・管理者だけが見られるようにしているため。
2. `backend/app/infra/image_store.py` に Blob Storage 版の保存先を追加し、`IMAGE_STORE=azure_blob` で切り替える
   (キーは「講座 ID/ファイル名」のまま。`delete_prefix` は講座の削除時に使う)。
3. 接続はアプリのマネージド ID(ロール「ストレージ BLOB データ共同作成者」)で行う。ロールの割り当て権限が無い場合は接続文字列をシークレットで渡す。
4. 既存の画像があれば、ローカルの `backend/var/images` の中身を同じキーでコンテナにアップロードする。

## AI が作ったコードの実行環境(次回のデプロイまでに確認)

AI による講座作成では、AI が作ったコード(例題・模範解答・正解の根拠・図)をサーバ側の Node.js + Pyodide で実行して確かめる
(`backend/runner/`、2026-10 追加)。コンテナイメージには node 本体と Pyodide が入る(Dockerfile の `runner` ステージ)。次回のデプロイ時に次を確認する。

1. **外向きの通信**:Pyodide のパッケージ(pandas・scikit-learn など)は、初回の実行時に CDN(cdn.jsdelivr.net)から取得する。
   Container App から CDN へ通信できること(受講者のブラウザと同じ取得元)。
2. **メモリ**:1回の実行で Pyodide とパッケージを読み込むため、数百 MB を使う。現在の `memory: 1Gi` では足りない可能性があるので、
   `infra/containerapp.json` の Container App を `cpu: 1.0` / `memory: 2Gi` に上げることを検討する。
3. 実行環境を使わない場合は `AI_RUNNER_ENABLED=false` にする(AI が作った下書きをそのまま保存する。作成画面に「コードの実行確認:なし」と表示される)。

## 自動起動・停止を有効にする(ロールの割り当てができるようになったら)

1. 所有者(またはユーザー アクセス管理者)の権限を持つ人に、手順 7 のロールの割り当てを実行してもらう
   (アプリのマネージド ID は手順 6 の出力 `appPrincipalId`)。
2. `infra/containerapp.parameters.json` の `dbAutostartEnabled` と `deployIdleStopJob` を `true` にして、手順 6 を再実行する。
3. 作られた DB 停止ジョブのマネージド ID にも、手順 7 と同じロールを割り当ててもらう。

## 時間指定の起動・停止への切り替え(将来)

運用開始後、9:00〜18:00(平日)だけ DB を起動する場合は、次のように変更します。Container Apps ジョブの cron は
**UTC** です(日本時間 9:00 = UTC 0:00、18:00 = UTC 9:00)。

1. 起動ジョブと停止ジョブを追加する(`infra/containerapp.json` の `Microsoft.App/jobs` を複製し、
   `command` をそれぞれ `["python", "-m", "app.cli", "db-start"]` / `["python", "-m", "app.cli", "db-stop"]`、
   `cronExpression` を `0 0 * * 1-5` / `0 9 * * 1-5` にする。手順 7 と同様に権限を付ける)。
2. 自動停止ジョブ(`db-idle-stop`)は削除するか、業務時間外だけ動くように `cronExpression` を変える。
3. 業務時間外のアクセスでも起動させたい場合は `DB_AUTOSTART_ENABLED=true` のまま、起動させたくない場合は `false` にする
   (`false` の場合、停止中は「データベースに接続できません」と表示されます)。

## リソースの削除(不要になった場合)

```bash
az containerapp delete -g $RG -n ca-ai-learning-portal --yes
az containerapp job delete -g $RG -n caj-ai-learning-portal-db-stop --yes
az containerapp env delete -g $RG -n cae-ai-learning-portal --yes
az monitor log-analytics workspace delete -g $RG --workspace-name log-ai-learning-portal --yes
az mysql flexible-server delete -g $RG -n $MYSQL --yes
az acr delete -g $RG -n $ACR --yes
```

※ `test20251008` は他プロジェクトのリソースと共用しているため、リソースグループ自体は削除しないでください。

## デプロイの記録

| 項目 | 内容 |
|---|---|
| 実施日 | 2026-10-20 |
| URL | `https://ca-ai-learning-portal.icymeadow-336147b5.japaneast.azurecontainerapps.io`(オフィス・VPN からのみ) |
| イメージ | `acrailearningportal.azurecr.io/ai-learning-portal:20261020072419` |
| MySQL | `mysql-ai-learning-portal`(Burstable B1ms / MySQL 8.0 / TLS 必須)。接続許可は「Azure のサービス」のみ |
| データ | デプロイ時点のローカル DB の内容をそのまま登録(ユーザ・講座・受講記録) |
| DB の自動起動・停止 | **無効**(`dbAutostartEnabled=false` / `deployIdleStopJob=false`)。デプロイしたアカウントにロールの割り当て権限が無いため |
| 秘密情報 | `infra/.env.azure`・`infra/containerapp.parameters.json`(どちらも Git 管理対象外) |

DB の起動・停止は手動で行います(停止中にアクセスすると「データベースに接続できません」と表示されます)。

```bash
az mysql flexible-server stop  -g test20251008 -n mysql-ai-learning-portal    # 使い終わったら停止
az mysql flexible-server start -g test20251008 -n mysql-ai-learning-portal    # 使う前に起動(数分かかる)
az mysql flexible-server show  -g test20251008 -n mysql-ai-learning-portal --query state -o tsv
```
