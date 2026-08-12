# AIリマインダー 利用手順

Mattermost・GROUPSESSIONから投稿・記事を取得し、AIでリマインド文章やAIMのアジェンダを作成できるアプリケーションです。作成したアジェンダは社内wiki(GROWI)へ公開することもできます。

## 1. フォルダ構成

配布フォルダには以下が含まれています。

```
ai_reminder/
├── chat_linkage.exe   ... アプリ本体
├── 起動.bat            ... ダブルクリックで起動＆ブラウザを開くショートカット
├── .env                ... Mattermost・GROUPSESSION・GROWI・Azure OpenAI の接続情報
├── settings.ini        ... 対象チャンネル・フォーラム・メンバー等の設定(自分で編集可能)
└── _internal/          ... アプリ動作用の内部ファイル(触らないでください)
```

## 2. 事前準備

このアプリは追加のソフトウェアインストールは不要です。ただし、利用開始前に `.env` と `settings.ini` の内容を環境に合わせて設定してください。

### 2-1. `.env` の設定

`chat_linkage.exe` と同じフォルダの `.env` に、以下の接続情報が設定されている必要があります。

```
AZURE_OPENAI_ENDPOINT=https://your-resource.services.ai.azure.com/openai/v1
AZURE_OPENAI_KEY=your-api-key

MATTERMOST_URL=https://chat.jbdcl.com
MATTERMOST_TOKEN=（パーソナルアクセストークン）

GROUPSESSION_BASE_URL=https://gs.jbdcl.com/gsession
GROUPSESSION_USERNAME=（GROUPSESSIONのログインID）
GROUPSESSION_PASSWORD=（GROUPSESSIONのログインパスワード）

GROWI_BASE_URL=https://wiki.jbdcl.com/
GROWI_API_TOKEN=（GROWIのAPIトークン）
```

- Azure OpenAIの接続情報については設定不要です。
- `MATTERMOST_TOKEN` は、Mattermostの「設定」→「セキュリティ」→「パーソナルアクセストークン」から発行します。
- `GROWI_API_TOKEN` は、GROWIの画面右上のユーザー名をクリック→設定画面→「API設定」タブ→「API Tokenを更新」ボタンから取得できます。

### 2-2. `settings.ini` の設定

対象チャンネル・フォーラム・期間・メンバー等を `settings.ini` で設定します。

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
root_path = /2000_開発者向け/2000_開発者向け/2YYY_組織/AIビジネス研究室/100_AIM
```

| 項目 | 説明 |
|------|------|
| `mattermost.target_username` | Mattermostタブ・GROUPSESSIONタブの投稿先プルダウンにある「DM」の宛先ユーザー名 |
| `history.channel` | Mattermostタブの履歴取得チャンネルの初期選択(表示名。`/api/channels` で取得できる名前と一致させる) |
| `history.read_date` | Mattermostタブの取得期間の初期値(今日から遡る日数) |
| `channel_users.members` | リマインド作成時に `@メンション` する対象のユーザー名一覧(カンマ区切り)。Mattermost投稿の場合、元投稿に `:sumi:` のリアクションをしていない人のみがメンションされる |
| `groupsession.forum_sid` | 新着記事を取得するGROUPSESSIONフォーラムのID(カンマ区切りで複数指定可) |
| `groupsession.read_date` | GROUPSESSIONタブの取得期間の初期値(今日から遡る日数) |
| `groupsession.remind_channel` | GROUPSESSIONタブの投稿先プルダウンに追加される、Mattermostチャンネルの表示名一覧(カンマ区切り) |
| `growi.channel_list` | アジェンダタブの「履歴・新着記事を取得」で参照するMattermostチャンネルの表示名一覧(カンマ区切り) |
| `growi.root_path` | アジェンダの公開先GROWIページの親パス(この下に「年/月」のページが作成・更新される) |

チャンネルの表示名を間違えると、該当機能でエラーメッセージが表示されます(3-1参照)。

## 3. アプリの起動方法

`起動.bat` をダブルクリックしてください。自動的にアプリが起動し、既定のブラウザで `http://localhost:8000` が開きます。

(`起動.bat` を使わず `chat_linkage.exe` を直接ダブルクリックした場合は、手動でブラウザから `http://localhost:8000` にアクセスしてください。)

起動時に黒いコンソール画面が表示されますが、これはアプリのログ出力用の画面です。閉じるとアプリが終了するため、利用中は閉じないでください。

## 4. 使い方

画面上部のタブで「Mattermost」「GROUPSESSION」「アジェンダ」を切り替えます。

### 4-1. Mattermostタブ

1. 左上のプルダウンからチャンネルを選び、取得開始日・取得終了日を指定して「履歴を取得」をクリックします(AIが「期日のある提出物・申請、回答が必要なもの、避難訓練・工事等の要注意アナウンス」のみに自動で絞り込んで一覧表示します)。
2. 左下の一覧から投稿をクリックすると、右上に投稿内容・リアクション一覧が表示されます。
3. 「リマインドを作成」をクリックすると、AIがリマインド文章を生成し、右下の「投稿内容」欄に反映されます。
4. 右下の「投稿先」プルダウンで、投稿先を選択します。
   - `DM: （ユーザー名）` — `settings.ini` の `mattermost.target_username` へDM送信
   - `チャンネルへ返信: （チャンネル名）` — リマインド作成元の投稿があるチャンネルへ、その投稿へのスレッド返信として投稿(投稿を選択している場合のみ選択肢に表示されます)
5. 内容を確認・編集し、「投稿」をクリックすると送信されます。送信後もメッセージ欄の内容は残ります。

### 4-2. GROUPSESSIONタブ

1. 取得開始日・取得終了日を指定して「新着記事を取得」をクリックします(AIが「期日のある提出物・申請、回答が必要なもの、避難訓練・工事等の要注意アナウンス」のみに自動で絞り込んで一覧表示します)。
2. 左下の一覧から記事をクリックすると、右上に本文(添付ファイル一覧含む)が表示されます。
3. 「リマインドを作成」をクリックすると、AIがリマインド文章を生成します(本文には元記事のURLが自動で付与されます)。
4. 右下の「投稿先」プルダウンで、`DM` または `settings.ini` の `groupsession.remind_channel` に設定したチャンネルへの投稿を選択します。
5. 「投稿」をクリックすると送信されます。

添付ファイルのダウンロードをしたい場合は、閲覧しているブラウザでGROUPSESSIONに別途ログイン済みである必要があります。

### 4-3. アジェンダタブ

1. 取得開始日・取得終了日を指定して「履歴・新着記事を取得」をクリックします。`settings.ini` の `growi.channel_list` に設定した全チャンネルのMattermost投稿と、GROUPSESSIONの新着記事をまとめて取得します。
2. 左下の一覧から項目をクリックすると詳細が表示され、チェックボックスでアジェンダに含める項目を選択します。
3. 「アジェンダを作成」をクリックすると、チェックした項目をもとにAIが部署定例会の「全体共有事項」を生成し、右下のテキストエリアに表示されます。
4. 内容を確認・編集し、「公開先: 年」「公開先: 月」を指定して「wikiへ公開」をクリックすると、`settings.ini` の `growi.root_path` 配下に「年/月」のページとして公開されます(既に同じ年月のページがある場合は上書き更新されます)。

## 5. アプリの終了方法

起動中のコンソール画面を閉じるか、`Ctrl + C` を押してください。

## 6. トラブルシューティング

| 症状 | 原因・対処 |
|------|-----------|
| 起動直後にコンソールが閉じてエラーで落ちる(`KeyError: 'GROUPSESSION_BASE_URL'` 等) | `.env` がexeと同じフォルダに無い、または内容が未設定です。2-1を確認してください。 |
| 「settings.iniのチャンネル『◯◯』が見つかりませんでした」と表示される | `settings.ini` に設定したチャンネルの表示名が、実際のMattermostチャンネル名と一致していません。2-2を確認してください。 |
| 「Mattermost APIエラー」と表示される | `MATTERMOST_TOKEN` が無効・期限切れの可能性があります。Mattermostでパーソナルアクセストークンを再発行してください。 |
| 「GROUPSESSIONへのアクセスに失敗しました」と表示される | `GROUPSESSION_USERNAME` / `GROUPSESSION_PASSWORD` が誤っている可能性があります。 |
| 「GROWIへの公開に失敗しました」と表示される | `GROWI_API_TOKEN` が無効、または `growi.root_path` の指定が誤っている可能性があります。 |
| ブラウザで画面が表示されない | コンソール画面にエラーが出ていないか確認し、`http://localhost:8000` に手動でアクセスしてください。すでに同じポートで別プロセスが起動している場合は、そちらを終了してから再度お試しください。 |
