# 011_chat_linkage

Mattermost 連携アプリ。パーソナルアクセストークンを使い、以下をGUIで操作できる。

- `settings.ini` に設定したチャンネル・期間で、画面を開くと自動的に過去チャット履歴を取得(チャンネル選択プルダウン・カレンダーからの手動変更・再取得も可能)
- 取得した投稿一覧から任意の投稿を選択し、投稿内容とリアクション(誰がどのスタンプを押したか)を表示
- 選択した投稿内容をもとに、Azure OpenAI(`gpt-5.4-mini`)でリマインド文章を生成
- DM送信先(`MATTERMOST_TARGET_USERNAME`)へのメッセージ投稿

## セットアップ

```bash
pip install -r requirements.txt
```

`.env` に以下を設定する。

```
MATTERMOST_URL=https://chat.jbdcl.com
MATTERMOST_TOKEN=（パーソナルアクセストークン）
MATTERMOST_TARGET_USERNAME=（DM送信先のユーザー名）
```

リマインド文章生成には、ワークスペースルート（`011_chat_linkage` の2つ上の階層）の `.env` に設定された Azure OpenAI の接続情報を使用する。

```
AZURE_OPENAI_ENDPOINT=https://your-resource.services.ai.azure.com/openai/v1
AZURE_OPENAI_KEY=your-api-key
```

履歴取得の対象チャンネル・期間は `settings.ini` に設定する（`011_chat_linkage` ディレクトリ直下）。

```ini
[history]
channel = AIビジネス連絡事項
read_date = 30
```

- `channel` — 履歴を取得するチャンネルの表示名（`/api/channels` で取得できる名前と一致させる）
- `read_date` — 今日から遡って取得する日数

`channel_users` セクションは将来利用予定のため、現時点のアプリ動作には使用されない。

## 実行

`011_chat_linkage` ディレクトリ直下（`app/` の一つ上の階層）で以下を実行する。

```bash
uvicorn app.main:app --reload --port 8000
```

ブラウザで `http://127.0.0.1:8000` を開いてください。

## 画面構成

- 左上: チャンネル選択プルダウン、取得開始日・取得終了日のカレンダー、「履歴を取得」ボタン
- 左下: 取得した投稿一覧。クリックで選択
- 右上: 選択した投稿の内容・リアクション一覧・「リマインドを作成」ボタン(クリックすると生成結果が右下のDM入力欄に反映される)
- 右下: `MATTERMOST_TARGET_USERNAME` 宛のDM投稿フォーム

## API エンドポイント

| メソッド | パス | 説明 |
|----------|------|------|
| GET | `/` | フロントエンド（index.html） |
| GET | `/api/health` | ヘルスチェック |
| GET | `/api/target-username` | DM送信先ユーザー名を返す |
| GET | `/api/settings` | `settings.ini` の履歴取得設定(チャンネル名・期間)を返す |
| GET | `/api/channels` | 参加チャンネル一覧（チーム横断、公開・非公開のみ） |
| GET | `/api/channels/{channel_id}/posts?start=YYYY-MM-DD&end=YYYY-MM-DD` | 指定期間の投稿一覧 |
| GET | `/api/posts/{post_id}/reactions` | 指定投稿のリアクション一覧 |
| POST | `/api/reminder` | 投稿内容からAIがリマインド文章を生成 |
| POST | `/api/dm` | DM送信先へメッセージを投稿 |

## ファイル構成

- `app/main.py` — FastAPI エントリポイント
- `app/mattermost_service.py` — Mattermost API v4 の呼び出し（チャンネル一覧・投稿履歴・リアクション・DM投稿）
- `app/azure_ai_service.py` — Azure OpenAI 呼び出し（リマインド文章生成: `gpt-5.4-mini`）
- `app/static/` — フロントエンド（HTML / CSS / JS）

## 補足

- 履歴取得は Mattermost API のページング(`/api/v4/channels/{id}/posts`)を新しい投稿から遡る形で行うため、対象期間が古い・投稿数が多いチャンネルほど取得に時間がかかる。
