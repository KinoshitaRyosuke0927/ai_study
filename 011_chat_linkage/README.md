# 011_chat_linkage

Mattermost・GROUPSESSION 連携アプリ。パーソナルアクセストークン・GROUPSESSIONアカウントを使い、以下をGUIで操作できる。

- Mattermostの指定チャンネルから、指定期間の投稿履歴を取得
- GROUPSESSION(社内掲示板)の指定フォーラムから、指定期間の新着記事(本文・添付ファイル含む)を取得
- 取得した投稿・記事を、Azure OpenAI(`gpt-5.4-mini`)で「期日のある提出物・申請、回答が必要なもの」のみに自動で絞り込んで一覧表示
- 選択した投稿・記事の内容をもとに、AIでリマインド文章を生成
  - Mattermost投稿の場合: `settings.ini` の `channel_users.members` のうち、元投稿に `:sumi:` のリアクションをしていないメンバーを `@メンション`
  - GROUPSESSION記事の場合: メンバー全員を `@メンション`し、本文には元記事のURLを付与
- DM送信先(`MATTERMOST_TARGET_USERNAME`)へのメッセージ投稿
- Mattermost・GROUPSESSION双方から取得した投稿・記事のうち、チェックした項目をもとに、AIで部署定例会の「アジェンダ(全体共有事項)」を生成

## セットアップ

```bash
pip install -r requirements.txt
```

`.env` に以下を設定する。

```
MATTERMOST_URL=https://chat.jbdcl.com
MATTERMOST_TOKEN=（パーソナルアクセストークン）
MATTERMOST_TARGET_USERNAME=（DM送信先のユーザー名）

GROUPSESSION_BASE_URL=https://gs.jbdcl.com/gsession
GROUPSESSION_USERNAME=（GROUPSESSIONのログインID）
GROUPSESSION_PASSWORD=（GROUPSESSIONのログインパスワード）
```

リマインド文章・アジェンダ生成には、ワークスペースルート（`011_chat_linkage` の2つ上の階層）の `.env` に設定された Azure OpenAI の接続情報を使用する。

```
AZURE_OPENAI_ENDPOINT=https://your-resource.services.ai.azure.com/openai/v1
AZURE_OPENAI_KEY=your-api-key
```

対象チャンネル・フォーラム・期間・メンバーは `settings.ini` に設定する（`011_chat_linkage` ディレクトリ直下）。

```ini
[history]
channel = AIビジネス連絡事項
read_date = 30

[channel_users]
members = yano, endo, n-ishii, r-isahai, m-unno, r-asanoma, r-kinoshita, r-yurino

[groupsession]
forum_sid = 15
read_date = 30
```

- `history.channel` — Mattermostの履歴を取得するチャンネルの表示名（`/api/channels` で取得できる名前と一致させる）
- `history.read_date` — 今日から遡って取得する日数
- `channel_users.members` — リマインド作成時に `@メンション` する対象のユーザー名一覧（カンマ区切り）。Mattermost投稿の場合は、このうち元投稿に `:sumi:` のリアクションをしていない人のみがメンションされる
- `groupsession.forum_sid` — 新着記事を取得するGROUPSESSIONフォーラムのID
- `groupsession.read_date` — 今日から遡って取得する日数（画面表示時の初期値としてのみ使用。実際の取得期間は画面の日付指定に従う）

## 実行

`011_chat_linkage` ディレクトリ直下（`app/` の一つ上の階層）で以下を実行する。

```bash
uvicorn app.main:app --reload --port 8000
```

ブラウザで `http://127.0.0.1:8000` を開いてください。

## 画面構成

画面上部のタブで「Mattermost」「GROUPSESSION」「アジェンダ」を切り替える。

### Mattermostタブ
- 左上: チャンネル選択プルダウン、取得開始日・取得終了日のカレンダー、「履歴を取得」ボタン
- 左下: 取得した投稿一覧（AIにより「期日のある提出物・申請、回答が必要なもの」のみに絞り込み済み）。クリックで選択
- 右上: 選択した投稿の内容・リアクション一覧・「リマインドを作成」ボタン
- 右下: `MATTERMOST_TARGET_USERNAME` 宛のDM投稿フォーム（GROUPSESSIONタブと共通で、タブ切り替え時に実体が移動する）

### GROUPSESSIONタブ
- 左上: 取得開始日・取得終了日のカレンダー、「新着記事を取得」ボタン
- 左下: 取得した記事一覧（AIによる絞り込み済み）。クリックで選択
- 右上: 選択した記事の内容（本文HTML・添付ファイル一覧）・「リマインドを作成」ボタン
- 右下: DM投稿フォーム（Mattermostタブと共通）

添付ファイルのダウンロードリンクは、閲覧しているブラウザでGROUPSESSIONに別途ログイン済みである必要がある（アプリのバックエンドとブラウザのセッションは別物のため）。

### アジェンダタブ
- 左上: 取得開始日・取得終了日のカレンダー、「履歴・新着記事を取得」ボタン（クリックでMattermost履歴・GROUPSESSION新着記事の両方を取得。Mattermostのチャンネルは Mattermostタブで選択中のものを使用する）
- 左下: Mattermost投稿・GROUPSESSION記事を合わせた一覧（取得元がわかるバッジ付き）。各行にチェックボックスがあり、詳細表示はクリック、アジェンダへの採否はチェックボックスで操作する
- 右上: 選択した項目の詳細内容・「アジェンダを作成」ボタン（チェック済み項目をもとにAIが「全体共有事項」を生成）
- 右下: 生成された部署定例会アジェンダ（Markdown）を表示するテキストエリア

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
| GET | `/api/webpage/announcements?start=YYYY-MM-DD&end=YYYY-MM-DD` | GROUPSESSION新着記事一覧（AIによる絞り込み済み） |
| POST | `/api/reminder` | 投稿・記事内容からAIがリマインド文章を生成（`source`: `mattermost` / `web`） |
| POST | `/api/agenda` | チェックした投稿・記事一覧からAIが部署定例会アジェンダを生成 |
| POST | `/api/dm` | DM送信先へメッセージを投稿 |

## ファイル構成

- `app/main.py` — FastAPI エントリポイント
- `app/mattermost_service.py` — Mattermost API v4 の呼び出し（チャンネル一覧・投稿履歴・パーマリンク組み立て・リアクション・DM投稿）
- `app/groupsession_service.py` — GROUPSESSIONへのログイン・スレッド一覧/本文取得（JSON APIを直接呼び出し、HTMLサニタイズ・添付ファイルURL組み立てを行う）
- `app/azure_ai_service.py` — Azure OpenAI 呼び出し（投稿の絞り込み・リマインド文章生成・アジェンダ生成: `gpt-5.4-mini`）
- `app/static/` — フロントエンド（HTML / CSS / JS）

## 補足

- 履歴取得は Mattermost API のページング(`/api/v4/channels/{id}/posts`)を新しい投稿から遡る形で行うため、対象期間が古い・投稿数が多いチャンネルほど取得に時間がかかる。
- Mattermost投稿・GROUPSESSION記事の一覧取得時には、Azure OpenAIに投稿内容を渡して「期日のある提出物・申請、回答が必要なもの」のみを判定させ、それ以外(雑談・情報共有・完了報告など)は一覧に表示しない。
- リマインド文章中のURL（GROUPSESSION記事へのリンク等）や、アジェンダ文章中の各項目へのリンクは、AIに直接URLを生成させると誤り・改変のリスクがあるため、プレースホルダー文字列(`{{ARTICLE_URL}}` 等)を出力させたうえで、アプリ側で実際のURLに置換している。
- アジェンダ生成で一度に多くの項目(10件超など)をチェックすると、AIが末尾の項目でリンク付与を省略することがまれにある。その場合は再実行すると改善することが多い。
- GROUPSESSIONへのログインはStruts(CSRFトークン)方式のため、ログイン画面を都度GETしてトークンを取得したうえでPOSTしている。
