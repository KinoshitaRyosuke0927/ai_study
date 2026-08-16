# 011_chat_linkage

Mattermost・GROUPSESSION 連携アプリ。パーソナルアクセストークン・GROUPSESSIONアカウントを使い、以下をGUIで操作できる。

- GROUPSESSIONは画面上のログインフォーム(モーダル)からID・パスワードを入力してログイン(サーバのメモリ上にのみ保持し、ファイルには保存しない)
- Mattermostの指定チャンネルから、指定期間の投稿履歴を取得
- GROUPSESSION(社内掲示板)の指定フォーラム(複数指定可)から、指定期間の新着記事(本文・添付ファイル含む)を取得
- 取得した投稿・記事を、Azure OpenAI(`gpt-5.4-mini`)で「期日のある提出物・申請、回答が必要なもの、避難訓練・工事等の要注意アナウンス」のみに自動で絞り込んで一覧表示
- 選択した投稿・記事の内容をもとに、AIでリマインド文章を生成(提出物・申請の締め切り案内と、避難訓練等のアナウンス案内とでそれぞれ文面パターンを切り替え)
  - Mattermost投稿の場合: `settings.ini` の `channel_users.members` のうち、元投稿に `:sumi:` のリアクションをしていないメンバーを `@メンション`
  - GROUPSESSION記事の場合: メンバー全員を `@メンション`し、本文には元記事のURLを付与
- 生成したリマインド文章を、DM送信先(`settings.ini` の `mattermost.target_username`)、またはMattermostチャンネル(Mattermostタブ: リマインド作成元の投稿への返信 / GROUPSESSIONタブ: `settings.ini` の `groupsession.remind_channel` に設定したチャンネルへの通常投稿)へ投稿
- Mattermost・GROUPSESSION双方から取得した投稿・記事のうち、チェックした項目をもとに、AIで部署定例会の「アジェンダ(全体共有事項)」を`agenda_template.txt`のひな形に埋め込んで生成
- 生成したアジェンダを、GROWI(社内wiki)へ「公開」または「自分のみ公開」で公開(既存ページがあれば更新)

## セットアップ

```bash
pip install -r requirements.txt
```

`.env` に以下を設定する。

```
MATTERMOST_URL=https://chat.jbdcl.com
MATTERMOST_TOKEN=（パーソナルアクセストークン）

GROUPSESSION_BASE_URL=https://gs.jbdcl.com/gsession
```

GROUPSESSIONのログインID・パスワードは、セキュリティ上 `.env` には保存せず、GROUPSESSIONタブの画面から入力する(サーバのメモリ上にのみ保持され、アプリ終了時に破棄される)。

リマインド文章・アジェンダ生成には、ワークスペースルート（`011_chat_linkage` の2つ上の階層）の `.env` に設定された Azure OpenAI の接続情報を使用する。

```
AZURE_OPENAI_ENDPOINT=https://your-resource.services.ai.azure.com/openai/v1
AZURE_OPENAI_KEY=your-api-key
```

対象チャンネル・フォーラム・期間・メンバーは `settings.ini` に設定する（`011_chat_linkage` ディレクトリ直下）。

```ini
[mattermost]
target_username = r-kinoshita

[history]
channel = AIビジネス連絡事項
read_date = 30

[channel_users]
members = yano, endo, n-ishii, r-isahai, m-unno, r-asanoma, r-kinoshita, r-yurino

[groupsession]
forum_sid = 5, 15
read_date = 30
remind_channel = AIビジネス連絡事項, AIC 連絡事項

[growi]
channel_list = AIビジネス連絡事項, AIC 連絡事項
root_path = /100_AIM
```

- `mattermost.target_username` — DM投稿フォームの送信先ユーザー名
- `history.channel` — Mattermostの履歴を取得するチャンネルの表示名(`/api/channels` で取得できる名前と一致させる)
- `history.read_date` — 今日から遡って取得する日数
- `channel_users.members` — リマインド作成時に `@メンション` する対象のユーザー名一覧(カンマ区切り)。Mattermost投稿の場合は、このうち元投稿に `:sumi:` のリアクションをしていない人のみがメンションされる
- `groupsession.forum_sid` — 新着記事を取得するGROUPSESSIONフォーラムのID(カンマ区切りで複数指定可)
- `groupsession.read_date` — 今日から遡って取得する日数(画面表示時の初期値としてのみ使用。実際の取得期間は画面の日付指定に従う)
- `groupsession.remind_channel` — GROUPSESSIONタブの投稿先プルダウンに追加される、Mattermostチャンネルの表示名一覧(カンマ区切り)
- `growi.channel_list` — アジェンダタブの「履歴・新着記事を取得」で参照するMattermostチャンネルの表示名一覧(カンマ区切り)
- `growi.root_path` — アジェンダの公開先GROWIページの親パス(この下に「年/月」のページが作成・更新される)

アジェンダのひな形は `settings.ini` と同じく `011_chat_linkage` ディレクトリ直下の `agenda_template.txt` で管理する。`{{YEAR}}` / `{{MONTH}}` / `{{AGENDA_BODY}}` のプレースホルダー以外は自由に編集でき、リクエストの都度読み込むためアプリの再起動は不要。

## 実行

`011_chat_linkage` ディレクトリ直下（`app/` の一つ上の階層）で以下を実行する。

```bash
uvicorn app.main:app --reload --port 8000
```

ブラウザで `http://127.0.0.1:8000` を開いてください。

## 画面構成

画面左上の「AIリマインダー」ラベルの右に「GROUPSESSIONログイン」ボタンがある。クリックするとログインモーダルが開き、GROUPSESSIONのID・パスワードを入力してログインできる(ログイン情報はサーバのメモリ上にのみ保持)。ログインするとボタンの文字が緑色の「GROUPSESSIONログイン済」に変わり、GROUPSESSIONタブ・アジェンダタブの新着記事取得ボタンが活性化する(未ログインの間は非活性)。

画面上部のタブで「Mattermost」「GROUPSESSION」「アジェンダ」を切り替える。

### Mattermostタブ
- 左上: チャンネル選択プルダウン、取得開始日・取得終了日のカレンダー、「履歴を取得」ボタン
- 左下: 取得した投稿一覧（AIにより「期日のある提出物・申請、回答が必要なもの、避難訓練・工事等の要注意アナウンス」のみに絞り込み済み）。クリックで選択
- 右上: 選択した投稿の内容・リアクション一覧・「リマインドを作成」ボタン
- 右下: Mattermostへの投稿フォーム。投稿先プルダウンで「DM(`settings.ini` の `mattermost.target_username` 宛)」または「リマインド作成元の投稿があるチャンネルへの返信」を選択できる

右上・右下エリアの境界はドラッグして高さを変更できる(GROUPSESSIONタブ・アジェンダタブも同様)。

### GROUPSESSIONタブ
- 左上: 取得開始日・取得終了日のカレンダー、「新着記事を取得」ボタン(GROUPSESSION未ログイン時は非活性)
- 左下: 取得した記事一覧（AIによる絞り込み済み）。クリックで選択
- 右上: 選択した記事の内容（本文HTML・添付ファイル一覧）・「リマインドを作成」ボタン
- 右下: Mattermostへの投稿フォーム。投稿先プルダウンで「DM」または `settings.ini` の `groupsession.remind_channel` に設定したチャンネルへの投稿を選択できる

添付ファイルのダウンロードリンクは、閲覧しているブラウザでGROUPSESSIONに別途ログイン済みである必要がある（アプリのバックエンドとブラウザのセッションは別物のため）。

### アジェンダタブ
- 左上: 取得開始日・取得終了日のカレンダー、「履歴・新着記事を取得」ボタン（クリックでMattermost履歴・GROUPSESSION新着記事の両方を取得。Mattermostのチャンネルは `settings.ini` の `growi.channel_list` に設定された全チャンネルを対象とする。GROUPSESSION未ログイン時は非活性）
- 左下: Mattermost投稿・GROUPSESSION記事を合わせた一覧（取得元がわかるバッジ付き）。各行にチェックボックスがあり、詳細表示はクリック、アジェンダへの採否はチェックボックスで操作する。見出し右の「日時順」「投稿者順」「取得元順」ボタンで並び替え可能
- 右上: 選択した項目の詳細内容・「アジェンダを作成」ボタン（1件以上チェックすると活性化し、チェック済み項目をもとにAIが「全体共有事項」を生成。`agenda_template.txt` のひな形に埋め込まれる）
- 右下: 生成された部署定例会アジェンダ（Markdown）を表示するテキストエリア。「公開先: 年」「公開先: 月」と「公開範囲」(公開 / 自分のみ公開)を指定し「wikiへ公開」でGROWIへ公開する

DM投稿フォームはこのタブには存在しない。

## API エンドポイント

| メソッド | パス | 説明 |
|----------|------|------|
| GET | `/` | フロントエンド（index.html） |
| GET | `/api/health` | ヘルスチェック |
| GET | `/api/target-username` | DM送信先ユーザー名を返す |
| GET | `/api/settings` | `settings.ini` の設定(チャンネル名・期間・メンバー・GROUPSESSIONフォーラム等)を返す |
| GET | `/api/channels` | 参加チャンネル一覧（チーム横断、公開・非公開のみ） |
| GET | `/api/channels/{channel_id}/posts?start=YYYY-MM-DD&end=YYYY-MM-DD` | 指定期間の投稿一覧（AIによる絞り込み済み） |
| GET | `/api/posts/{post_id}/reactions` | 指定投稿のリアクション一覧 |
| GET | `/api/groupsession/login-status` | GROUPSESSIONのログイン状態を返す |
| POST | `/api/groupsession/login` | GROUPSESSIONへログインを試行し、成功した場合のみサーバのメモリ上にID・パスワードを保持する |
| POST | `/api/groupsession/logout` | GROUPSESSIONのログイン情報を破棄する |
| GET | `/api/webpage/announcements?start=YYYY-MM-DD&end=YYYY-MM-DD` | GROUPSESSION新着記事一覧（AIによる絞り込み済み。未ログインの場合は401） |
| POST | `/api/reminder` | 投稿・記事内容からAIがリマインド文章を生成（`source`: `mattermost` / `web`） |
| POST | `/api/agenda` | チェックした投稿・記事一覧からAIが部署定例会アジェンダを生成（`agenda_template.txt` を使用） |
| POST | `/api/agenda/publish` | 生成したアジェンダをGROWIへ公開（`grant`: `public` / `only_me`） |
| POST | `/api/dm` | Mattermostへメッセージを投稿（`target`: `dm` / `channel`。`channel`の場合 `channel_id` 必須、`post_id` を指定すると返信になる） |

## ファイル構成

- `app/main.py` — FastAPI エントリポイント
- `app/mattermost_service.py` — Mattermost API v4 の呼び出し（チャンネル一覧・投稿履歴・パーマリンク組み立て・リアクション・投稿）
- `app/groupsession_service.py` — GROUPSESSIONへのログイン・スレッド一覧/本文取得（JSON APIを直接呼び出し、HTMLサニタイズ・添付ファイルURL組み立てを行う。ID・パスワードはメモリ上にのみ保持）
- `app/growi_service.py` — GROWI(社内wiki)へのアジェンダページ作成・更新（新規作成/公開範囲が同じ場合の更新/自分のみ公開への変更時のみ削除+再作成、を使い分け）
- `app/azure_ai_service.py` — Azure OpenAI 呼び出し（投稿の絞り込み・リマインド文章生成・アジェンダ生成: `gpt-5.4-mini`）
- `app/static/` — フロントエンド（HTML / CSS / JS）
- `agenda_template.txt` — アジェンダのひな形（`{{YEAR}}` / `{{MONTH}}` / `{{AGENDA_BODY}}` 以外は自由に編集可能）

## exe化(PyInstaller)

配布用に `chat_linkage.exe` を作成する手順です。エンドユーザー向けの利用方法は [manual.md](manual.md) を参照してください。

### 1. PyInstaller のインストール
```bash
pip install pyinstaller
```

### 2. ビルド

`011_chat_linkage` ディレクトリ直下(`app/` の一つ上の階層)で以下を実行します。

```powershell
pyinstaller --name chat_linkage `
  --onedir `
  --noconfirm `
  --paths . `
  --add-data "app/static;static" `
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
  --exclude-module pandas `
  --exclude-module numpy `
  --exclude-module scipy `
  --exclude-module torch `
  --exclude-module torchvision `
  --exclude-module torchaudio `
  --exclude-module sklearn `
  --exclude-module cv2 `
  --exclude-module transformers `
  --exclude-module matplotlib `
  app/main.py
```

- `--onedir`(デフォルト): exeと依存ライブラリを同一フォルダに展開する形式でビルドします。`--onefile` は起動のたびに一時フォルダへ全ライブラリを展開するため使用しません。
- `--paths .`: `app/main.py` が `from app import ...` のように `app` パッケージを絶対importしているため、その親ディレクトリ(カレントディレクトリ)をimport探索パスに追加します。
- `--add-data "app/static;static"`: フロントエンドの静的ファイルを同梱します。frozen実行時、エントリスクリプト(`app/main.py`)はサブフォルダの階層を保持せずトップレベルスクリプトとして組み込まれるため、`STATIC_DIR`(`app/main.py` の `BASE_DIR / "static"`)と一致させるには同梱先を `app/static` ではなく `static` にする必要があります。
- `--hidden-import uvicorn.*`: uvicornは動的importが多く、PyInstallerの静的解析だけでは検出できないモジュールがあるため明示指定します。
- `--exclude-module pandas` 等: `openai` パッケージが(未使用の)CLIファイル検証機能向けに `pandas` を遅延import しており、それを起点に `torch` / `scikit-learn` / `opencv` / `transformers` などの大型ライブラリまでPyInstallerの静的解析で巻き込まれてしまう(このアプリでは実際には一切使用しない機能)。除外しないとビルド成果物が700MB超になるため、明示的に除外する。

ビルド成果物は `dist/chat_linkage/` フォルダに生成されます(`chat_linkage.exe` 本体 + `_internal/` 配下の依存ライブラリ、除外指定込みで約70MB)。

### 3. 配布用ファイルの配置

`dist/chat_linkage/` フォルダに、exeと同じ階層で以下を追加してください(PyInstallerには同梱されません)。exe化時は `settings.ini` ・`.env` ともに **exeと同じフォルダ** を参照します(開発時は `011_chat_linkage` 直下・ワークスペースルートをそれぞれ参照)。

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
- `settings.ini`(`011_chat_linkage/settings.ini` をコピーして配布環境向けに編集)
- `agenda_template.txt`(`011_chat_linkage/agenda_template.txt` をコピー)— アジェンダのひな形
- `起動.bat`(任意)— ダブルクリックでexe起動とブラウザオープンを行うショートカット
  ```bat
  @echo off
  start "" http://localhost:8000
  chat_linkage.exe
  ```

`dist/chat_linkage/` フォルダ一式をzip化して配布してください。エンドユーザー向けの利用手順は [manual.md](manual.md) を参照(または同梱)してください。

## 補足

- 履歴取得は Mattermost API のページング(`/api/v4/channels/{id}/posts`)を新しい投稿から遡る形で行うため、対象期間が古い・投稿数が多いチャンネルほど取得に時間がかかる。
- Mattermost投稿・GROUPSESSION記事の一覧取得時には、Azure OpenAIに投稿内容を渡して「期日のある提出物・申請、回答が必要なもの、避難訓練・工事等の要注意アナウンス」のみを判定させ、それ以外(雑談・情報共有・完了報告など)は一覧に表示しない。
- リマインド文章中のURL（GROUPSESSION記事へのリンク等）や、アジェンダ文章中の各項目へのリンクは、AIに直接URLを生成させると誤り・改変のリスクがあるため、プレースホルダー文字列(`{{ARTICLE_URL}}` 等)を出力させたうえで、アプリ側で実際のURLに置換している。
- アジェンダ生成で一度に多くの項目(10件超など)をチェックすると、AIが末尾の項目でリンク付与を省略することがまれにある。その場合は再実行すると改善することが多い。
- GROUPSESSIONへのログインはStruts(CSRFトークン)方式のため、ログイン画面を都度GETしてトークンを取得したうえでPOSTしている。ID・パスワードが誤っている場合もHTTPステータスは200で返り、ログイン画面がそのまま再表示されるため、`groupsession_service.py` ではレスポンス内にログインフォームが残っているかどうかで成否を判定している。
- GROWIのページ更新API(レガシー`/_api/pages.update`)は、公開範囲を「自分のみ公開」に変更する際にアクセス許可ユーザーを正しく設定できず、投稿者自身も含めて誰もアクセスできないページになってしまう不具合があるため、`growi_service.py` では「自分のみ公開」への変更時のみページを削除して新規作成し直す(この場合、ページのURLが変わる)。それ以外の変更(本文のみの更新、自分のみ公開→公開への変更等)は通常の更新APIで安全に行える。
- 右パネル上下2エリアの境界はドラッグで高さを調整できる。一度ドラッグすると、以後その2エリアはウィンドウサイズに応じて比例的に伸縮する(ドラッグ前の初期比率とは別に管理される)。
