# 011_nightrain(チャット内容自動リマインドサービス)

指定したMattermostチャンネルとGROUPSESSIONフォーラムの投稿を一定間隔で監視し、リマインドが必要そうな投稿を見つけたら、AIで内容を要約し、定型の文面のリマインドを指定したMattermostチャンネルへ自動で投稿するサービス。

[011_chat_linkage_light](../011_chat_linkage_light/) のMattermostタブ・GROUPSESSIONタブの機能(投稿の絞り込み・リマインド文章の作成)を切り出し、人が画面を操作しなくても動く自動サービスにしたもの。

- **実行環境**: Azure Functions(Consumptionプラン、タイマートリガー)のみ。画面は持たず、個人のPCで常用することは想定しない(`run_local.py` は開発時の動作確認専用)
- **設定**: 監視対象・投稿先・アカウント情報などは、すべてFunction Appのアプリケーション設定(環境変数)で管理する。変更はAzure portalの「環境変数」画面などから行う(パスワード・トークンはKey Vault参照を推奨)
- **リマインド対象の判定**: [011_agenda_tool](../011_agenda_tool/)(アジェンダ作成ツール)と同じ学習済みモデル(TF-IDF + ロジスティック回帰)を使う
- **リマインドの回数**: 1つの投稿につき、見つけたときに1回だけ投稿する

デプロイ手順は [DEPLOYMENT.md](DEPLOYMENT.md) を参照。

## 処理の流れ

タイマー(平日 9:00-17:55 JST の5分ごと)で `app/watcher.py` の `poll_once()` が実行され、以下を行う。

0. 営業日・営業時間(平日 9:00-18:00 JST。土日・祝日・`COMPANY_HOLIDAYS` の休日を除く)でなければ、何もせずに終了する(`app/business_calendar.py`)

1. `WATCH_MATTERMOST_CHANNELS` のチャンネルと `WATCH_GROUPSESSION_FORUM_SIDS` のフォーラムから、前回確認した時刻以降の投稿を取得する(取りこぼし防止のため `POLL_OVERLAP_MINUTES` 分だけ重ねて取得する)
2. 学習済みモデルで各投稿に0~1のスコアを付け、`REMINDER_THRESHOLD` 以上のものをリマインド対象にする
3. リマインド対象1件ごとに、Azure OpenAIで元の投稿から「種類(依頼/お知らせ)」「表題」「依頼されている作業(お知らせの件名)」「注意点」「期日」を抜き出し、定型の文面に当てはめて `REMIND_CHANNEL` に投稿する
4. 確認した時刻と通知済みの投稿IDを、Blob Storageに保存する(同じ投稿を二度リマインドしないため)

投稿されるメッセージの例:

```
@channel
#### 年末調整実施について
年末調整の実施の依頼が来ております。
経管への提出書類がある場合は、原本の提出も含めて期限までに対応が必要になりますので注意してください。
作業完了しましたら、 :sumi: スタンプを押してください。

**期日：11/20(金)**

https://chat.jbdcl.com/...(元の投稿のURL)
```

元の投稿に「各人が提出する提出物がある」「各人が実施する作業がある」と明確に書かれていない投稿(障害・停電・工事のアナウンスなど)は、以下のお知らせ用の文面で投稿する。スタンプの依頼・注意点・期日は付けない。

```
@channel
#### Microsoft 365障害のお知らせ
Microsoft 365の障害発生のお知らせが来ております。

https://chat.jbdcl.com/...(元の投稿のURL)
```

- AIが作るのは種類(依頼/お知らせ)・表題・依頼作業(「〇〇の依頼が来ております。」の〇〇)・注意点・期日(年月日と時刻)だけで、それ以外の文面・期日の曜日・元の投稿のURLはプログラムで組み立てる(`app/watcher.py` の `render_remind_message`)
- 依頼の場合も、注意点は元の投稿に注意事項が明記されている場合だけ記載する。期日は元の投稿に明記されている場合だけ記載し、投稿日より前の日付になった場合は記載しない。期日に時刻がある場合は `11/20(金) 17:00` のように付ける
- 先頭のメンションは `REMIND_MENTION` で変更できる(既定は `@channel`。投稿先チャンネルのメンバー全員に通知が飛ぶ)
- 投稿はMattermostトークンの持ち主のアカウントで行われる。投稿には目印(`props.from_nightrain`)を付けており、投稿先チャンネルが監視対象に含まれていても、このサービス自身の投稿はリマインド対象にならない
- 営業時間外(夜間・土日・祝日・会社独自の休日)に投稿された内容は、確認位置を進めないため、次の営業日の 9:00 の実行でまとめてリマインドされる(17:55 以降 18:00 までの投稿も翌営業日 9:00 に回る)
- 初回実行時(状態が未保存の場合)は、直近 `POLL_OVERLAP_MINUTES` 分の投稿だけを対象にする(過去の投稿をまとめてリマインドしないため)
- 要約・投稿に失敗した投稿は、次回以降に再試行する。`MAX_RETRY_COUNT` 回失敗したら諦める(Application Insightsにエラーログが残る)

## アプリケーション設定

| 設定名 | 必須 | 説明 | 例・既定値 |
|---|---|---|---|
| `POLL_SCHEDULE` | ○ | 監視の実行間隔(NCRONTAB形式: 秒 分 時 日 月 曜日。**UTCで指定する**) | `0 */5 0-8 * * 1-5`(JSTの平日 9:00-17:55 に5分ごと) |
| `MATTERMOST_URL` | ○ | MattermostのURL | `https://chat.jbdcl.com` |
| `MATTERMOST_TOKEN` | ○ | Mattermostのパーソナルアクセストークン(Key Vault参照を推奨) | |
| `GROUPSESSION_BASE_URL` | △ | GROUPSESSIONのURL(フォーラムを監視する場合は必須) | `https://gs.jbdcl.com/gsession` |
| `GROUPSESSION_USERNAME` | △ | GROUPSESSIONのログインID(同上) | |
| `GROUPSESSION_PASSWORD` | △ | GROUPSESSIONのパスワード(同上。Key Vault参照を推奨) | |
| `AZURE_OPENAI_ENDPOINT` | ○ | Azure OpenAIのエンドポイント(v1 API) | `https://xxx.services.ai.azure.com/openai/v1` |
| `AZURE_OPENAI_KEY` | ○ | Azure OpenAIのAPIキー(Key Vault参照を推奨) | |
| `AZURE_OPENAI_DEPLOYMENT` | | 投稿内容の要約に使うデプロイ名 | `gpt-5.4-mini` |
| `WATCH_MATTERMOST_CHANNELS` | | 監視するMattermostチャンネルの表示名(カンマ区切り) | `JBD社員全体のお知らせ, JBD全体のお知らせ, 全員/拠点などの特定のお知らせ, 社員/拠点などの特定のお知らせ, 東京本社共有` |
| `WATCH_GROUPSESSION_FORUM_SIDS` | | 監視するGROUPSESSIONフォーラムのID(カンマ区切り) | `5, 15` |
| `REMIND_CHANNEL` | ○ | リマインドを投稿するMattermostチャンネルの表示名(試運用中は `雑務連絡`、本運用で `AIビジネス連絡事項` に変更予定) | `雑務連絡` |
| `REMIND_DM_USERNAME` | | **動作確認用**。設定すると、投稿先を `REMIND_CHANNEL` ではなくこのユーザーとのDMに差し替える。本番運用時は空にする | `r-kinoshita` |
| `REMIND_MENTION` | | リマインド投稿の先頭に付けるメンション(未設定なら `@channel`。`none` を指定すると付けない) | `@channel` |
| `REMINDER_THRESHOLD` | | リマインド対象とみなすスコアのしきい値(0~1) | `0.7` |
| `POLL_OVERLAP_MINUTES` | | 取りこぼし防止のため、前回確認時刻からさかのぼって取得する時間(分) | `2` |
| `NOTIFIED_RETENTION_DAYS` | | 通知済みの記録を残す日数 | `30` |
| `MAX_RETRY_COUNT` | | リマインドの作成・投稿に失敗した場合に試行する回数 | `3` |
| `BUSINESS_START_HOUR` | | 営業開始の時(JST) | `9` |
| `BUSINESS_END_HOUR` | | 営業終了の時(JST。この時刻以降は営業時間外) | `18` |
| `COMPANY_HOLIDAYS` | | 会社独自の休日(カンマ区切り)。`MM-DD` は毎年、`YYYY-MM-DD` はその日だけ休日として扱う。土日・祝日は設定しなくても休日として扱う | `12-29, 12-30, 12-31, 01-02, 01-03` |

- チャンネルは、トークンの持ち主が参加している公開・非公開チャンネルを表示名で指定する。同じ表示名のチャンネルが複数のチームにある場合は「チーム表示名/チャンネル表示名」の形式で指定する
- 見つからないチャンネルが `WATCH_MATTERMOST_CHANNELS` にあった場合は、警告ログを出してそのチャンネルだけ飛ばす。`REMIND_CHANNEL` が見つからない場合は、その回の処理全体を中止する(確認位置は進めないため、設定を直せば次回から続きを処理する)
- `POLL_SCHEDULE` を変更すると、Function Appが再起動され新しい間隔で動く(再デプロイは不要)。Linux の Consumption プランではタイムゾーンを変更できないため、時刻は UTC(JST - 9時間)で指定する
- 祝日の判定には `jpholiday` パッケージを使う(振替休日・国民の休日を含む)。営業時間の判定はコード側でも行うため、`POLL_SCHEDULE` を広めに設定しても営業時間外には投稿されない

## ファイル構成

- `function_app.py` — Azure Functions のエントリポイント(タイマートリガー)
- `host.json` — Azure Functions のホスト設定(タイムアウト5分)
- `requirements.txt` — 依存パッケージ(`scikit-learn` はモデルの学習時と同じ `1.8.0` に固定)
- `app/watcher.py` — 監視処理の本体(取得・スコアリング・リマインド投稿・状態保存)
- `app/config.py` — アプリケーション設定(環境変数)の読み込み
- `app/mattermost_service.py` — Mattermost API v4 の呼び出し(チャンネル一覧・投稿履歴・投稿)
- `app/groupsession_service.py` — GROUPSESSIONへのログイン・スレッド一覧/本文取得
- `app/azure_ai_service.py` — Azure OpenAI 呼び出し(投稿内容から表題・依頼作業・注意点・期日をJSONで抜き出す)
- `app/business_calendar.py` — 営業日・営業時間の判定(土日・祝日・会社独自の休日・営業時間外)
- `app/state_store.py` — 監視状態の保存(Blob Storage のコンテナ `nightrain-state`。ローカル確認時はフォルダ)
- `app/model/` — 投稿の絞り込みモデル(`reminder_classifier.joblib`・`predict.py`・`preprocess.py`)。**011_agenda_tool からコピーしたもの。直接編集しない**
- `build_package.ps1` — デプロイ用zipの作成
- `run_local.py` — 開発時の動作確認用(ローカルで1回だけ実行)
- `local.settings.json.sample` — ローカル確認用の設定のひな形

## フィルタモデルの更新

モデルの学習・検証は `011_agenda_tool` で行う。再学習したら、`011_agenda_tool` ディレクトリで以下を実行して `app/model/` にコピーし、再ビルド・再デプロイする。

```bash
cd ../011_agenda_tool
python -m app.model.export_model
```

詳細は [011_agenda_tool/app/model/MODEL.md](../011_agenda_tool/app/model/MODEL.md) を参照。

## 開発時の動作確認(ローカル)

`local.settings.json.sample` を `local.settings.json` にコピーして値を設定し、`011_nightrain` ディレクトリで実行する。ローカル実行では、誤って本番チャンネルに投稿しないよう、`REMIND_DM_USERNAME` を設定していないと実行できない。状態はBlobではなく `.local_state/` に保存される。

```bash
pip install -r requirements.txt

# 投稿もAI呼び出しもせず、直近7日分からリマインド対象を判定して、投稿予定のメッセージを表示する
python run_local.py --print-only --skip-ai --lookback-minutes 10080

# 直近1日分を対象に、AIで投稿内容を要約してDMへ投稿する
python run_local.py --lookback-minutes 1440
```

| オプション | 説明 |
|---|---|
| `--print-only` | Mattermostへ投稿せず、投稿予定のメッセージを表示するだけにする(状態も保存しない) |
| `--skip-ai` | Azure OpenAIを呼ばず、固定の要約で代用する |
| `--lookback-minutes N` | さかのぼって確認する時間(分)。`POLL_OVERLAP_MINUTES` を上書きする |
| `--reset-state` | `.local_state/` を削除し、初回実行の状態から始める |
| `--ignore-business-hours` | 営業日・営業時間の判定をせずに実行する(夜間・休日に動作確認する場合に使う) |
