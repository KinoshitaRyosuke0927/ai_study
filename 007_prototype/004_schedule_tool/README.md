# スケジュール確認ツール(004_schedule_tool)

GROUPSESSION にログインし、マイグループのメンバーの予定を指定期間分まとめて取得して、
**全員(または指定人数以上)が空いている時間帯**を一覧・タイムラインで確認できるローカルの Web アプリです。
exe(PyInstaller)にして配布する想定です。利用者向けの手順は [manual.md](manual.md) を参照してください。

## 方針(必ず守ること)

- **参照専用**: GROUPSESSION の予定・在席状況は変更しない。送信するのはログインと、スケジュール画面の「表示の切り替え」だけ
  (`groupsession_client.py` の `_post_view` で、`CMD` が空文字以外・予定IDを含む送信を止めている)。
- **予定の内容は保存しない**: 取得した予定はサーバから画面へ返すだけで、ファイル・ログに書かない。API の応答には `Cache-Control: no-store` を付けている。
- **ダウンロード**: 空き時間の候補などのファイル出力は行わない(ステップ3で出す業務状況のCSVも、予定のタイトル・内容は含めない)。
- **保存するもの**:
  - `config.json` の、前回選んだマイグループとメンバーのID(`last_group` / `last_member_ids`)
  - 業務状況のラベル(`data/labels.json`): 1人×1日ごとの枠ラベル(メンバーID・氏名・マイグループ・日付・枠の値)だけ。**予定名などの予定の内容は保存しない**
    (学習するときに、ラベルのある日の予定を GROUPSESSION から読み込み直してメモリ上で使う。以前の版で保存していた予定は起動時に取り除く)
  - 学習したモデル(`data/office_model.joblib`): 予定名は文字の並びをハッシュ化した特徴量にするため、単語の一覧は残らない
- **学習・推定はこのPCの中だけで行う**: 外部と通信するのは GROUPSESSION の読み込みだけ。画面のサーバは `127.0.0.1` で待ち受ける。
- ID・パスワードとログイン中のセッションは、サーバのメモリ上にのみ保持する。

## 構成

```
004_schedule_tool/
├── run_app.py                ... 起動スクリプト(exe の入口。ブラウザを開いて uvicorn を起動)
├── schedule_tool.spec        ... PyInstaller の設定
├── requirements.txt
├── tools/
│   └── help_screenshots.py   ... 使い方ページの画面写真を架空のデータで撮り直す(exe には含めない)
├── config.json               ... 設定(初回起動時に自動作成。Git 管理外の想定)
├── data/                     ... 業務状況のラベルとモデル(自動作成。Git 管理外の想定)
└── app/
    ├── config.py             ... config.json の読み込み・前回の選択の保存
    ├── groupsession_client.py ... ログイン、マイグループ・メンバー・予定の取得(表示の切り替えのみ送信)
    ├── schedule_parser.py    ... sch010.do(週間表示)の HTML の読み取り
    ├── status_model.py       ... 業務状況のルール判定・学習・推定・出社割合
    ├── status_store.py       ... 業務状況のラベルの保存・読み込み
    ├── main.py               ... FastAPI(API と画面の配信)
    └── static/
        ├── index.html / style.css / app.js
        ├── free_time.js      ... 空き時間の計算(ブラウザ・node の両方で動く)
        ├── status.js         ... 業務状況(出社割合)の画面
        ├── help.html         ... 利用者向けの使い方ページ(画面右上の「使い方」から開く)
        └── help/             ... 使い方ページの画面写真(架空のメンバー・予定で撮影したもの)
```

利用者向けの手順は `manual.md`(と同じ内容の `app/static/help.html`)、管理者向けの手順はこの README の「管理者向けの運用手順」にまとめている。

## GROUPSESSION の画面と取得方法(GROUPSESSION 5.1.3 で確認)

| 目的 | 方法 |
|------|------|
| ログイン | `common/cmn001.do` に CSRF トークン付きで POST(011_agenda_tool と同じ) |
| マイグループ一覧 | `schedule/sch010.do` を GET し、`<select name="sch010DspGpSid">` のうち値が `M` で始まる選択肢 |
| メンバー | 上のフォームの入力値に `sch010DspGpSid=<マイグループ>`・`CMD=""` を入れて POST(グループ切り替えと同じ)し、`td.cal_colHeader-sonota` の `openUserInfoWindow(ユーザーID)` と氏名を読む |
| 指定週の予定 | さらに `sch010DspDate=YYYYMMDD`・`iniDsp=0`・`changeDateFlg=1` を付けて POST すると、その日から7日分が表示される(`iniDsp=1` のままだと日付指定が無視されて今週になる) |

週間表示の HTML の読み方:

- 日付: 1行目の `moveDailySchedule('day', YYYYMMDD, …)`。土日は `bgC_calSaturday` / `bgC_calSunday`。日本の祝日(振替休日・国民の休日を含む)は GROUPSESSION の見出しでは区別できないため、`jpholiday`(PC内で計算するライブラリ。通信しない)で判定する(`schedule_parser.is_holiday`)
- 時刻のある予定: メンバーの行の日ごとのセル(`addSchedule('add', YYYYMMDD, uid, 0)` でセルの日付がわかる)に
  `<a onclick="editSchedule('edit', YMD, 予定ID, uid, 0)">` → `span.cal_time`(`09:00-10:00`)・`div.cal_content`(タイトル)・`span.tooltips`(詳細)
- 時刻のない予定・期間予定: メンバーの行の下の行(氏名欄の `rowspan` の分)に `td.cal_periodCell`(`colspan` = 日数)と
  `td.cal_periodCell-less`(予定なしの1日)が並ぶ。列の位置から日付を求める(`editSchedule` の日付は開始日ではないので使わない)
- タイトル色: `cl_fontSchTitle○○` クラス(Green / Marine / Blue / Red / Wine / Cien / Gray など)
- HTML は閉じタグが崩れている箇所があるため、`html.parser` ではなく `lxml` で読む

予定を取得すると、期間の開始日から7日ずつ表示を切り替えて取得し、週をまたぐ期間予定は予定IDごとに日付の範囲をつなげる。
1回の取得は `config.json` の `max_weeks`(空き時間の画面。既定8週間)/ `max_weeks_status`(業務状況の画面。既定26週間)まで。

## 空き時間の判定(free_time.js)

- 業務時間(既定 9:00〜18:00)を刻み(既定30分)で区切った枠ごとに、各メンバーの予定と少しでも重なれば「空いていない」とする。
- 昼休み(既定 12:00〜13:00)にかかる枠は候補にしない(候補は昼休みで区切られる)。
- 連続する枠を、**同じ顔ぶれで必要人数以上が通して空いている**限りつなげ、必要な長さ(既定60分)以上のものを候補にする。
- 時刻のない予定(締め切りのメモにも使われるため)は、既定では空き時間に影響させない。タイムラインの「終日」欄のチップをクリックすると
  「埋まっている扱い」になり、その日は終日埋まっているとして計算する(この切り替えは保存しない)。

## 開発時の起動

```
cd c:\azure_ai\education\007_prototype\004_schedule_tool
pip install -r requirements.txt
python run_app.py          # http://localhost:8000 が開く(--port で変更、--no-browser でブラウザを開かない)
```

既定のポートは他のツールと同じ **8000**(同時に使う想定はないため)。

空き時間の計算は node で単体確認できる:

```
node -e "const F=require('./app/static/free_time.js'); console.log(F.buildSlots({businessStart:'09:00',businessEnd:'18:00',slotMinutes:30,lunchStart:'12:00',lunchEnd:'13:00'}).length)"
```

## exe 化

```
cd c:\azure_ai\education\007_prototype\004_schedule_tool
pyinstaller schedule_tool.spec --noconfirm
```

`dist\schedule_tool\` フォルダ(`schedule_tool.exe` と `_internal`)をまとめて配布する。`config.json` は初回起動時に exe と同じフォルダへ自動作成される。

学習済みモデルの配布:

- exe と同じフォルダに `data\office_model.joblib` を置く(開発環境の `data\office_model.joblib` をコピー)。モデルを更新したら上書きしてもらう。
- `data\labels.json` は配布しない(誰が・何日に・どの時間オフィスにいたかの情報のため)。
- `config.json` の `labeling_enabled` は既定 `false`(配布版)。ラベルの保存・削除・学習のボタンを隠し、API(`/api/status/labels`・`/labels/delete`・`/train`)も 403 で受け付けない。
  管理者(ラベル付け・学習をする人)だけ `true` にする。開発環境の `config.json` は `true` にしてあるので、配布物に混ぜないこと。

## 業務状況(出社割合)

### 出社割合の定義

- 勤務時間(`config.json` の業務時間から昼休みを除いた範囲。既定 9:00〜18:00 − 12:00〜13:00 = 8時間)を **30分ごとの16枠**に区切り、
  枠ごとに **オフィス / オフィス外 / 休み** のラベルを付ける。
- 出社割合 = オフィスの枠の数 ÷ 枠の数(勤務時間は8時間固定。半休は0.5、休暇・土日祝は0)。
- 出力するCSVは、取得した期間の **全日付 × 全メンバー**(休日も0として含む)。形式は行=日付・列=メンバーの横持ち(見出し `date,苗字…`(氏名を空白で区切った最初の部分。同じ苗字が複数いるときはその人だけ氏名)、日付は `2026/11/01`(yyyy/mm/dd)、値は `1` / `0.5` / `0.875` のように余分な0なし)で、予定名は含めない。UTF-8(BOM付き)。

### 判定の優先順(status_model.estimate)

1. 保存済みのラベル(枠の区切りが今の設定と同じもの)
2. 学習したモデル(`data/office_model.joblib` があれば)
3. キーワードによるルール(`rule_labels`。休暇・半休・在宅・出張・外出・訪問などの語。何も当てはまらなければオフィス)

休日(土日と日本の祝日。`schedule_parser.is_holiday`)は常に休み(0)。学習のときも、休日の日付のラベルは使わない。会社独自の休み(年末年始など)は休日扱いにしていない。

### ラベル付け(status.js)

- 出社割合の表(行=日付、列=メンバー)で日を選び、右の表で枠をクリック・ドラッグして塗る。行ごとに「1日オフィス / オフィス外 / 休み」のボタンもある。
- 「この日のラベルを保存」は、その日の全メンバー分(表示中のラベル)を保存する。送るのはラベルと、選んでいるマイグループだけ(予定は送らない)。
- 以前の版にあった予定名のマスキング・置き換えルールは、実際の予定にマスキングが必要なものがなかったため廃止した
  (予定名を保存しない方式に変えたので、マスキングは不要になった)。

### 学習(status_model.train)

- 学習データの作り方(`attach_events`): 保存済みのラベルをマイグループごとにまとめ、日付を「間が7日以内ならひとつの期間」に分けて、
  期間ごとに `GroupsessionClient.get_schedule` で予定を読み込み直す。その人のその日の予定をラベルとメモリ上で組み合わせて学習し、予定は保存しない。
  - ログインが必要(切れていればログイン画面を開く)。読み込みは1週間ずつなので、半年分で1分ほどかかる。
  - ラベルを付けた後に GROUPSESSION の予定が書き換えられた場合は、書き換え後の予定で学習する。
  - マイグループが記録されていないラベル(以前の版で保存したもの)は、画面で選んでいるマイグループで読み込む。グループにいない人のラベルは使わない(件数を画面に出す)。
- 1枠を1件とした分類(ロジスティック回帰)。特徴量は次の文字列を `FeatureHasher`(2^18次元)でハッシュ化したもの:
  - 枠の時刻・午前/午後・曜日・メンバー
  - その枠に重なる予定の予定名(2〜3文字の並び)・色
  - その日の時刻なし予定・その日の他の予定の予定名(2〜3文字の並び)・色
  - 人ごとの書き方の癖を学べるよう、上の文字の並びに「メンバー」を付けたもの
- 学習には10件(1人×1日)以上のラベルが必要。日付で分けた交差検証(最大5分割)で、枠の正解率と出社割合の平均誤差を求めて画面に出す。

## 管理者向けの運用手順

ラベル付け・学習は、`config.json` の `labeling_enabled` を `true` にした管理者の環境だけで行う(配布版は `false`)。

### ラベル付け

1. 「業務状況(出社割合)」で期間(最大26週間)を取得し、出社割合の表で日を選ぶ。
2. 右の表は、ラベルがない日はモデル(未学習ならルール)の推定で塗られている。違う枠だけ「塗る値」で塗り直し(行の右の「オ / 外 / 休」で1日分)、
   「この日のラベルを保存」で全メンバー分を保存する。保存済みのラベルを消すときは「この日のラベルを削除」。
3. 「◀ 前の日」「次の日 ▶」で日を移動しながら続ける。土日・祝日はラベル付けの対象外(常に0)。
4. 表の印: ✓ = 保存済みのラベル、無印 = モデル推定、斜体 = ルール判定、● = 画面で直してまだ保存していないもの。

### 学習

1. **GROUPSESSION にログインした状態で**、左の「保存したラベルでモデルを学習」を押す(ラベル10件以上で押せる)。
   ラベルのある日の予定を読み込み直すため、半年分で1分ほどかかる。
2. 終わると、日付で分けた検証の精度(枠の正解率・出社割合の平均誤差)が表示される。ラベルを追加したら学習し直す。
3. 2026-11-23 時点: 2026/4/1〜11/30 の1,134件で学習し、枠の正解率 95.2%・出社割合の平均誤差 ±0.046。

### 配布・モデルの更新

1. `pyinstaller schedule_tool.spec --noconfirm` で `dist\schedule_tool\` を作る(「exe 化」を参照)。
2. `dist\schedule_tool\data\` に、管理者の環境の `data\office_model.joblib` をコピーする。**`labels.json` と管理者の `config.json` は入れない。**
3. フォルダごと配布する。配布先の `config.json` は初回起動時に `labeling_enabled: false` で作られる。
4. モデルを更新したら、新しい `office_model.joblib` を配布先の `data` フォルダに上書きしてもらう。
5. `data` フォルダ(`labels.json` と `office_model.joblib`)は学習のやり直しに必要なので、別の場所にもバックアップしておく。

### 使い方ページの画面写真の撮り直し

画面を変えたら、`tools/help_screenshots.py` で `app/static/help/*.png` を撮り直す。

```
cd c:\azure_ai\education\007_prototype\004_schedule_tool
python tools/help_screenshots.py            # 3枚すべて(login / free / status)
python tools/help_screenshots.py status     # 指定した画面だけ
python tools/help_screenshots.py --serve    # モックサーバだけ起動(http://127.0.0.1:8765/?shot=free などで確認)
```

- 架空のメンバー・予定を返すモックサーバ(ポート 8765、127.0.0.1 のみ)を起動し、ヘッドレスの Chrome(無ければ Edge)で 1440×860 で撮影する。
- GROUPSESSION には接続せず、本物の `config.json`・`data` も使わない(一時フォルダに架空のラベル・モデルを作る)。
- 撮る画面や操作を変えるときは、スクリプト内の `AUTO_SCRIPT`(画面の自動操作)と `SHOTS` を直す。
- **実際の予定が写った画面写真は使わない**(顧客名などが写り込むため)。
