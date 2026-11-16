# 011_agenda_tool(アジェンダ作成ツール)

Mattermost・GROUPSESSIONの投稿・記事から、部署定例会(AIM)のアジェンダ「全体共有事項」をAIで作成し、社内wiki(GROWI)へ公開するツール。

[011_chat_linkage_light](../011_chat_linkage_light/) のアジェンダ作成機能(アジェンダタブ)だけを切り出したもの。機能は分割元のアジェンダタブと同じ。分割元にあったMattermostタブ・GROUPSESSIONタブ(個別投稿のリマインド作成・投稿)と、`/nightrain agenda`・`/nightrain remind` の自動応答(Azure Functions)は含まない。投稿の自動リマインドは [011_nightrain](../011_nightrain/)(チャット内容自動リマインドサービス)が担当する。

- **配布形態**: exe(PyInstaller)での配布のみ。Azure上には展開しない。利用者が各自 `settings.ini`・`.env` を編集して使う
- **Azureの利用**: アジェンダ本文(全体共有事項)の生成のみ、Azure OpenAI(`gpt-5.4-mini`)を使う
- **投稿の絞り込みモデル**: ローカルで動く学習済みモデル(TF-IDF + ロジスティック回帰)。**モデルの学習・検証はこのフォルダで行い**、学習したモデルを `011_nightrain` にも反映する(「フィルタモデル」章を参照)

## 機能

- GROUPSESSIONは画面上のログインフォーム(モーダル)からID・パスワードを入力してログイン(サーバのメモリ上にのみ保持し、ファイルには保存しない)
- `settings.ini` の `growi.channel_list` に設定したMattermostチャンネルの投稿と、`groupsession.forum_sid` に設定したGROUPSESSIONフォーラムの記事を、指定期間でまとめて取得
- 取得した投稿・記事を学習済みモデルで0~1のスコアにし、画面上部の「フィルタ強度」スライダー(0~1、0.1刻み、初期値0.5)以上のものだけを一覧表示
- チェックした項目をもとに、AIで「全体共有事項」を生成し、`agenda_template.txt` のひな形に埋め込む
- 生成したアジェンダを、GROWIへ「公開」または「自分のみ公開」で公開(既存ページがあれば更新)

## セットアップ

```bash
pip install -r requirements.txt
```

`.env`(このディレクトリ直下)に以下を設定する。

```
MATTERMOST_URL=https://chat.jbdcl.com
MATTERMOST_TOKEN=（パーソナルアクセストークン）

GROUPSESSION_BASE_URL=https://gs.jbdcl.com/gsession

GROWI_BASE_URL=https://wiki.jbdcl.com/
GROWI_API_TOKEN=（GROWIのAPIトークン）
```

アジェンダ生成には、ワークスペースルート(`011_agenda_tool` の1つ上の階層)の `.env` に設定された Azure OpenAI の接続情報を使う(exe化時は、exeと同じフォルダの `.env` にまとめて記載する)。

```
AZURE_OPENAI_ENDPOINT=https://your-resource.services.ai.azure.com/openai/v1
AZURE_OPENAI_KEY=your-api-key
```

対象チャンネル・フォーラム・期間・公開先は `settings.ini`(このディレクトリ直下)に設定する。分割元(`011_chat_linkage_light`)の `settings.ini` もそのまま読み込める(使わない項目は無視される)。

```ini
[history]
read_date = 30

[groupsession]
forum_sid = 5, 15
read_date = 30

[growi]
channel_list = AIビジネス連絡事項, AIC 連絡事項
root_path = /100_AIM
```

- `history.read_date` — Mattermost投稿の取得期間の初期値(今日から遡る日数)
- `groupsession.forum_sid` — 新着記事を取得するGROUPSESSIONフォーラムのID(カンマ区切りで複数指定可)
- `groupsession.read_date` — GROUPSESSION記事の取得期間の初期値(今日から遡る日数)。画面の取得期間の初期値は、`history.read_date` とこの値の長い方になる
- `growi.channel_list` — 「履歴・新着記事を取得」で参照するMattermostチャンネルの表示名一覧(カンマ区切り)
- `growi.root_path` — アジェンダの公開先GROWIページの親パス(この下に「年/月」のページが作成・更新される)

アジェンダのひな形は、このディレクトリ直下の `agenda_template.txt` で管理する。`{{YEAR}}` / `{{MONTH}}` / `{{AGENDA_BODY}}` のプレースホルダー以外は自由に編集でき、リクエストの都度読み込むためアプリの再起動は不要。

## 実行

`011_agenda_tool` ディレクトリ直下(`app/` の一つ上の階層)で以下を実行する。

```bash
uvicorn app.main:app --reload --port 8000
```

ブラウザで `http://127.0.0.1:8000` を開く。

## 画面構成

画面左上の「アジェンダ作成ツール」ラベルの右に「GROUPSESSIONログイン」ボタンがある。クリックするとログインモーダルが開き、GROUPSESSIONのID・パスワードを入力してログインできる。ログインするとボタンの文字が緑色の「GROUPSESSIONログイン済」に変わり、「履歴・新着記事を取得」ボタンが活性化する(未ログインの間は非活性)。

その右に「フィルタ強度」スライダーがある(0~1、0.1刻み、初期値0.5)。横の「?」アイコンにカーソルを合わせると説明が表示される。

- 左上: 取得開始日・取得終了日のカレンダー、「履歴・新着記事を取得」ボタン(Mattermost履歴・GROUPSESSION新着記事の両方を取得)
- 左下: Mattermost投稿・GROUPSESSION記事を合わせた一覧(取得元がわかるバッジ付き)。各行にチェックボックスがあり、詳細表示はクリック、アジェンダへの採否はチェックボックスで操作する。見出し右の「日時順」「投稿者順」「取得元順」ボタンで並び替え可能
- 右上: 選択した項目の詳細内容・「アジェンダを作成」ボタン(1件以上チェックすると活性化)
- 右下: 生成された部署定例会アジェンダ(Markdown)を表示するテキストエリア。「公開先: 年」「公開先: 月」と「公開範囲」(公開 / 自分のみ公開)を指定し「wikiへ公開」でGROWIへ公開する

右上・右下エリアの境界はドラッグして高さを変更できる。

添付ファイルのダウンロードリンクは、閲覧しているブラウザでGROUPSESSIONに別途ログイン済みである必要がある(アプリのバックエンドとブラウザのセッションは別物のため)。

## API エンドポイント

| メソッド | パス | 説明 |
|----------|------|------|
| GET | `/` | フロントエンド(index.html) |
| GET | `/api/health` | ヘルスチェック |
| GET | `/api/settings` | `settings.ini` の設定(取得期間・GROUPSESSIONフォーラム・対象チャンネル・公開先)を返す |
| GET | `/api/channels` | 参加チャンネル一覧(チーム横断、公開・非公開のみ)。`settings.ini` のチャンネル名からIDを引くために使う |
| GET | `/api/channels/{channel_id}/posts?start=YYYY-MM-DD&end=YYYY-MM-DD&threshold=0.5` | 指定期間の投稿一覧(モデルのスコアが `threshold` 以上のもののみ) |
| GET | `/api/groupsession/login-status` | GROUPSESSIONのログイン状態を返す |
| POST | `/api/groupsession/login` | GROUPSESSIONへログインを試行し、成功した場合のみサーバのメモリ上にID・パスワードを保持する |
| POST | `/api/groupsession/logout` | GROUPSESSIONのログイン情報を破棄する |
| GET | `/api/webpage/announcements?start=YYYY-MM-DD&end=YYYY-MM-DD&threshold=0.5` | GROUPSESSION新着記事一覧(モデルのスコアが `threshold` 以上のもののみ。未ログインの場合は401) |
| POST | `/api/agenda` | チェックした投稿・記事一覧からAIが部署定例会アジェンダを生成(`agenda_template.txt` を使用) |
| POST | `/api/agenda/publish` | 生成したアジェンダをGROWIへ公開(`grant`: `public` / `only_me`) |

このツールはMattermostへの投稿は行わない(Mattermost APIは読み取りのみ使用)。

## ファイル構成

- `app/main.py` — FastAPI エントリポイント
- `app/settings_loader.py` — `settings.ini` の読み込み
- `app/agenda_service.py` — モデルによる投稿の絞り込み・アジェンダの生成(ひな形への埋め込み)・GROWIへの公開
- `app/mattermost_service.py` — Mattermost API v4 の呼び出し(チャンネル一覧・投稿履歴・パーマリンク組み立て。読み取りのみ)
- `app/groupsession_service.py` — GROUPSESSIONへのログイン・スレッド一覧/本文取得(HTMLサニタイズ・添付ファイルURL組み立てを含む。ID・パスワードはメモリ上にのみ保持)
- `app/growi_service.py` — GROWI(社内wiki)へのアジェンダページ作成・更新
- `app/azure_ai_service.py` — Azure OpenAI 呼び出し(アジェンダ生成: `gpt-5.4-mini`。投稿の絞り込みには使用しない)
- `app/model/` — 投稿の絞り込みモデル(学習・推論・`011_nightrain` への反映。詳細は「フィルタモデル」章)
- `app/static/` — フロントエンド(HTML / CSS / JS)
- `agenda_template.txt` — アジェンダのひな形
- `agenda_tool.spec` — PyInstaller のビルド設定

## フィルタモデル(投稿の絞り込み)

投稿・記事の絞り込みには、Azure OpenAIではなくローカルで動作する学習済みモデル(`app/model/reminder_classifier.joblib`、約350KB)を使う。モデルは投稿テキストを文字1〜3gramのTF-IDFに変換し、ロジスティック回帰で「リマインドが必要そうか」の確率(0~1)を出力する。推論に必要なのは `scikit-learn` のみ。モデルの詳細は [app/model/MODEL.md](app/model/MODEL.md) を参照。

**このモデルは `011_nightrain`(チャット内容自動リマインドサービス)と共通。** 学習・検証はこのフォルダでのみ行い、学習したモデルは `export_model.py` で `011_nightrain` にコピーする。`011_nightrain` 側の `app/model/` は直接編集しない。

- `app/model/collect_train_data.py` — Mattermostの指定チャンネル・期間の投稿を取得し、ラベル付け用CSV(`pickup_flag,user,text`)を出力する(ファイル冒頭の `START_DATE` / `END_DATE` / `CHANNEL_DISPLAY_NAMES` を編集して実行)
- `app/model/train_data/` — ラベル付け済みCSV置き場。出力されたCSVの `pickup_flag` 列に 0(不要)/1(リマインド必要)を手動入力してからこのフォルダに置く
- `app/model/train_model.py` — `train_data/` 配下のCSVを読み込み、モデルを学習して `app/model/reminder_classifier.joblib` に保存する(正則化の強さは交差検証で自動選択)
- `app/model/preprocess.py` — 学習・推論で共通の前処理(個人宛てメンション・URLの正規化、小文字化)
- `app/model/predict.py` — 学習済みモデルを読み込み、投稿テキスト→0~1のリマインド必要度スコアを返す
- `app/model/export_model.py` — `reminder_classifier.joblib`・`predict.py`・`preprocess.py` を `../011_nightrain/app/model/` にコピーする

```bash
python -m app.model.collect_train_data   # ラベル付け対象のCSVを出力(要ラベル付け)
python -m app.model.train_model          # 学習を実行し、app/model/reminder_classifier.joblib に保存
python -m app.model.export_model         # 学習したモデルを 011_nightrain に反映
```

再学習後は、このツールのexeを再ビルドし、`011_nightrain` も再ビルド・再デプロイする(`011_nightrain/DEPLOYMENT.md` 参照)。

学習済みモデルは、学習時と同じバージョンの `scikit-learn` でなければ読み込めない場合がある。そのため、`requirements.txt`(このツール・`011_nightrain` とも)ではバージョンを固定している(`scikit-learn==1.8.0`)。`scikit-learn` のバージョンを上げる場合は、両方の `requirements.txt` を揃えてモデルを再学習すること。

## exe化(PyInstaller)

配布用に `agenda_tool.exe` を作成する手順。エンドユーザー向けの利用方法は [manual.md](manual.md) を参照。

### 1. 事前準備: 学習済みモデルの用意

ビルド前に `app/model/reminder_classifier.joblib` が存在することを確認する。無い場合は「フィルタモデル」章の手順で `python -m app.model.train_model` を実行して作成する。

### 2. PyInstaller のインストール

```bash
pip install pyinstaller
```

### 3. ビルド

`011_agenda_tool` ディレクトリ直下で以下を実行する(ビルド設定は `agenda_tool.spec` に保存済み)。

```powershell
pyinstaller --noconfirm agenda_tool.spec
```

`agenda_tool.spec` は、以下のコマンドラインオプションと同じ内容になっている。

```powershell
pyinstaller --name agenda_tool `
  --onedir `
  --noconfirm `
  --paths . `
  --add-data "app/static;static" `
  --add-data "app/model/reminder_classifier.joblib;model" `
  --hidden-import uvicorn.logging `
  --hidden-import uvicorn.loops `
  --hidden-import uvicorn.loops.auto `
  --hidden-import uvicorn.protocols `
  --hidden-import uvicorn.protocols.http `
  --hidden-import uvicorn.protocols.http.auto `
  --hidden-import uvicorn.protocols.websockets `
  --hidden-import uvicorn.protocols.websockets.auto `
  --hidden-import uvicorn.lifespan `
  --hidden-import uvicorn.lifespan.on `
  --hidden-import sklearn._cyutility `
  --exclude-module pandas `
  --exclude-module torch `
  --exclude-module torchvision `
  --exclude-module torchaudio `
  --exclude-module transformers `
  --exclude-module accelerate `
  --exclude-module catboost `
  --exclude-module lightgbm `
  --exclude-module xgboost `
  --exclude-module plotly `
  --exclude-module skimage `
  --exclude-module cv2 `
  --exclude-module matplotlib `
  app/main.py
```

- `--onedir`(デフォルト): exeと依存ライブラリを同一フォルダに展開する形式でビルドする。`--onefile` は起動のたびに一時フォルダへ全ライブラリを展開するため使用しない。
- `--paths .`: `app/main.py` が `from app import ...` のように `app` パッケージを絶対importしているため、その親ディレクトリ(カレントディレクトリ)をimport探索パスに追加する。
- `--add-data "app/static;static"`: フロントエンドの静的ファイルを同梱する。frozen実行時、エントリスクリプト(`app/main.py`)はサブフォルダの階層を保持せずトップレベルスクリプトとして組み込まれるため、`STATIC_DIR`(`app/main.py` の `BASE_DIR / "static"`)と一致させるには同梱先を `app/static` ではなく `static` にする必要がある。
- `--add-data "app/model/reminder_classifier.joblib;model"`: 学習済みモデルを `_internal/model/reminder_classifier.joblib` に配置する。`app/model/predict.py` の `MODEL_PATH` は、frozen実行時に `sys.executable`(exeの場所)を基準にこのパスを組み立てる。
- `--hidden-import uvicorn.*`: uvicornは動的importが多く、PyInstallerの静的解析だけでは検出できないモジュールがあるため明示指定する。
- `--hidden-import sklearn._cyutility`: scikit-learn 1.8で追加された内部モジュールで、PyInstaller側のフックがまだ対応していないため明示指定する(指定しないとexe起動時に `ModuleNotFoundError` で停止する)。
- `--exclude-module pandas` 等: `openai` パッケージ等を起点に不要に巻き込まれる大きなライブラリを除外する(除外しないと成果物が数百MB増える)。`scipy` は `scikit-learn` が使用するため除外しない。

配布前に `dist/agenda_tool/agenda_tool.exe` を起動し、投稿の取得(絞り込み)・アジェンダ作成が正常に動作することを必ず確認する。

### 4. 配布用ファイルの配置

ビルドすると `dist/agenda_tool/` フォルダに `agenda_tool.exe` 本体と `_internal/` が生成される。このフォルダに、exeと同じ階層で以下を追加する(PyInstallerには同梱されないため手動で配置する)。exe化時は `settings.ini`・`.env`・`agenda_template.txt` とも **exeと同じフォルダ** を参照する。

- `.env` — Mattermost・GROUPSESSION・GROWIの接続情報に加え、Azure OpenAIの接続情報(`AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_KEY`)も1つのファイルにまとめて配置する
  ```
  AZURE_OPENAI_ENDPOINT=https://your-resource.services.ai.azure.com/openai/v1
  AZURE_OPENAI_KEY=your-api-key

  MATTERMOST_URL=https://chat.jbdcl.com
  MATTERMOST_TOKEN=（パーソナルアクセストークン）

  GROUPSESSION_BASE_URL=https://gs.jbdcl.com/gsession

  GROWI_BASE_URL=https://wiki.jbdcl.com/
  GROWI_API_TOKEN=（GROWIのAPIトークン）
  ```
- `settings.ini`(`011_agenda_tool/settings.ini` をコピーして配布環境向けに編集)
- `agenda_template.txt`(`011_agenda_tool/agenda_template.txt` をコピー)
- `起動.bat`(任意)— ダブルクリックでexe起動とブラウザオープンを行うショートカット
  ```bat
  @echo off
  start "" http://localhost:8000
  agenda_tool.exe
  ```

### 5. zip化するフォルダ構成

```
agenda_tool/                  ← このフォルダごとzip化して配布する(dist/agenda_tool/)
├── agenda_tool.exe           ... アプリ本体(PyInstallerが生成)
├── _internal/                ... 依存ライブラリ・学習済みモデル等(PyInstallerが生成。触らない)
├── .env                      ... 接続情報(手動配置)
├── settings.ini              ... 対象チャンネル・フォーラム・公開先等の設定(手動配置)
├── agenda_template.txt       ... アジェンダのひな形(手動配置)
└── 起動.bat                  ... 起動用ショートカット(任意、手動配置)
```

manual.md 内の「1. フォルダ構成」もこの構成と対応しているため、フォルダ名を変更する場合は manual.md 側の記載も合わせて更新すること。

## 補足

- 履歴取得は Mattermost API のページング(`/api/v4/channels/{id}/posts`)を新しい投稿から遡る形で行うため、対象期間が古い・投稿数が多いチャンネルほど取得に時間がかかる。
- モデルの学習データが少ない・偏っているカテゴリ(例: 避難訓練・工事等のアナウンス系)では判定精度が低くなることがあるため、見逃しが疑われる場合は「フィルタ強度」を下げるか、`app/model/train_data/` にそのカテゴリの事例を追加してモデルを再学習することを検討する。
- アジェンダ文章中の各項目へのリンクは、AIに直接URLを生成させると誤り・改変のリスクがあるため、プレースホルダー文字列(`{{URL_0}}` 等)を出力させたうえで、アプリ側で実際のURLに置換している。
- アジェンダ生成で一度に多くの項目(10件超など)をチェックすると、AIが末尾の項目でリンク付与を省略することがまれにある。その場合は再実行すると改善することが多い。
- GROUPSESSIONへのログインはStruts(CSRFトークン)方式のため、ログイン画面を都度GETしてトークンを取得したうえでPOSTしている。ID・パスワードが誤っている場合もHTTPステータスは200で返り、ログイン画面がそのまま再表示されるため、`groupsession_service.py` ではレスポンス内にログインフォームが残っているかどうかで成否を判定している。
- GROWIのページ更新API(レガシー`/_api/pages.update`)は、公開範囲を「自分のみ公開」に変更する際にアクセス許可ユーザーを正しく設定できず、誰もアクセスできないページになってしまう不具合があるため、`growi_service.py` では「自分のみ公開」への変更時のみページを削除して新規作成し直す(この場合、ページのURLが変わる)。
- 右パネル上下2エリアの境界はドラッグで高さを調整できる。一度ドラッグすると、以後その2エリアはウィンドウサイズに応じて比例的に伸縮する。
