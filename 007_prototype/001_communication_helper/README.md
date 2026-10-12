# コミュニケーション練習ツール PoC

AI（新入社員役）と音声でリアルタイムに会話し、コミュニケーションを練習するプロトタイプ。

- 設定: ユーザ（先輩）と AI（新人の鈴木さん）は、どちらも IT 企業で勤怠管理システム「KinTai Cloud」を開発するエンジニア。
  業務シナリオ・雑談の話題もエンジニアの日常に沿って設定している（[backend/personas.py](backend/personas.py)）
- AI の声は性別ごとに固定（女性: `marin` / 男性: `cedar`）。変更する場合は `personas.GENDERS` の `default_voice` を編集する
- 会話相手の表情: `image/{man|woman}_{表情}.png` を、Web 会議の相手映像風のタイルに表示する。
  感情推定のたびに次の優先順で表情を切り替える（[frontend/app.js](frontend/app.js) の `expressionFor`）。相手が話している間はタイルの枠が緑に光る

  | 表情 | 条件 |
  |---|---|
  | angry（不満） | 安心感 ≤ 25 かつ 信頼感 ≤ 25 |
  | surprise（動揺・焦り） | 1 回の発言で緊張が +15 以上、または 緊張 ≥ 80 |
  | think（困惑・緊張・落ち込み） | 緊張 ≥ 60、意欲 ≤ 35、安心感 ≤ 35 のいずれか |
  | laugh（安心して前向き） | 安心感 ≥ 70 かつ 意欲 ≥ 65 かつ 緊張 ≤ 35 |
  | smile（穏やか） | 上記以外 |
- 割り込みは計測して感情推定・レポートに使うが、ユーザが萎縮しないよう会話ログには表示しない
  - AI の話し終わりと同時に話し始めると、Azure 側の音声の切り詰めが失敗して
    `Audio content of XXms is already shorter than YYms` というエラーが返る。
    これは無害なので画面には出さず、実際は割り込みではないため直前の割り込みを取り消す（間は 0 秒として扱う）

## 開発ステップ

| ステップ | 内容 | 状態 |
|---|---|---|
| 1 | Realtime API（gpt-realtime-mini）+ 新入社員ペルソナ（性別選択・業務/雑談シナリオ）で音声会話 | ✅ |
| 2 | 文字起こし → LLM による受け手の感情推定 → グラフ表示 | ✅ |
| 3 | 声の特徴量（割り込み・間・話速・声量など）を感情推定に追加 | ✅ |
| 4 | 感情状態を AI の態度に反映、振り返りレポート | ✅ |

## 構成

```
ブラウザ ── WebRTC（音声・イベント）──▶ Azure OpenAI Realtime API
   │
   ├─ SDPオファー ──▶ バックエンド(FastAPI) ── エフェメラルキー発行 + SDP中継 ──▶ Azure
   └─ ユーザ発話の確定ごと ──▶ /api/emotion/evaluate ── gpt-5.4-mini（Structured Outputs）
```

- 音声はブラウザと Azure の間で直接やり取りするため、遅延が小さい
- API キー・システム指示文（ペルソナ設定）はバックエンドだけが持ち、ブラウザには渡さない
- ユーザ発話の文字起こしは `gpt-transcribe` デプロイを使用（話している途中から逐次表示）
- 感情推定: ユーザ発話の文字起こしが確定するたびに、直前までの会話履歴・現在の感情値・割り込み有無を
  評価用 LLM に渡し、更新後の感情（安心感 / 緊張 / 意欲 / 信頼感、0〜100）・心の声・理由・良かった点/改善点を受け取る
  （心の声・理由は画面には出さず、態度への反映とグラフのツールチップ・レポートに使う）
  - 推定は発話順に直列実行し、前回の結果を次の入力にする（感情が積み重なる）
  - 1 発話あたりの変化は ±30 までに制限（グラフの乱高下防止）
  - 推定には 1 発話あたり 3 秒前後かかる
- 声の特徴: ブラウザ（Web Audio API）でマイク音声を 40ms ごとに分析し、発話区間ごとに集計して感情推定に渡す
  （音声データ自体はサーバに送らない）

  | 項目 | 計測方法 | 判定の例 |
  |---|---|---|
  | 間 | AI が話し終えてからユーザが話し始めるまでの時間 | 3秒以上「長め」、6秒以上「かなり長い沈黙」 |
  | 割り込み | AI の発話中にユーザが話し始めた | 「相手の発話に割り込み」 |
  | 話速 | 文字起こしのモーラ数（概算）÷ 発話区間の長さ | 8.5 以上「速い」、10 以上「かなり速い」 |
  | 声量 | 有声部分の平均音量を、それまでの発話の中央値と比較 | +3dB「大きめ」、+6dB「かなり大きい」 |
  | 声の高さ | 自己相関で求めた基本周波数を、それまでの発話と比較 | +2.5 半音「高め（感情的）」 |
  | 抑揚 | 発話内の声の高さのばらつき（半音の標準偏差） | 1.5 未満「平坦」 |

  - 閾値は [backend/voice.py](backend/voice.py) で調整できる
  - 声量・声の高さは「その人のそれまでの発話」との比較なので、1 発話目は判定しない
  - 2 秒未満の短い発話は話速・抑揚を判定しない（区間前後の余白の影響が大きいため）
  - 声量を正しく測るため、マイクの自動音量調整（autoGainControl）は無効にしている
- 会話の文脈の維持（AI が自分の立場・会話の目的を見失わないための仕組み）
  - 指示文に、シナリオごとの「この会話でのあなたの目的と流れ」（例: 相談 → 状況説明 → 助言を受ける → お礼を言って締める）を含める
    （`personas.SCENARIOS` の `goal_flow`）。お礼・謝罪の礼儀と、相手を助ける側の言い方の禁止も共通ルールに入れている
  - 感情推定で、感情と同時に会話の進行段階（導入 / 本題 / まとめ / 終了）と「後輩が次にすべきこと」も判定し、態度の指示に含める
  - 会話に差し込むシステムメッセージは増やさない: 態度の指示は最新の 1 件だけ残し（前回分を削除）、
    相づち・話しかけなどの 1 回きりの指示は応答が終わったら削除する
- 態度への反映: 感情推定のたびに、感情値からルールベースで「次の発話での振る舞い」の指示を作り、
  Realtime API の会話にシステムメッセージとして差し込む（例: 緊張 80 以上 →「返事はごく短く、言葉に詰まる」）
  - ルールは [backend/emotion.py](backend/emotion.py) の `build_behavior_directive` で調整できる
  - 相談シナリオのように AI 側が用件を持ちかける場合（`ai_has_agenda`）は、緊張していても用件そのものは話させる
  - 推定に約 3 秒かかるため、反映されるのは「その発言への返事」ではなく「次の返事」から
    （直後の返事は、Realtime モデル自身が発言内容と声の調子から反応する）
  - ペルソナの指示文全体はブラウザに渡さず、感情に応じた指示だけを差し込む
- 振り返りレポート: 会話終了時に、評価付きの会話ログ全体を評価用 LLM に渡して生成（5 秒前後）
  - 総評 / 気持ちの変化（開始→終了）/ 相手から見た印象 / 良かった発言 / 改善したい発言と言い換え例 / 次回意識すること
  - 終了後は「振り返りレポートを見る」ボタンで再表示できる
  - 「レポートダウンロード」で、レポートと評価付きの会話ログを Markdown（`report_YYYYMMDD_HHMM_シナリオ名.md`）で保存できる
- 話者交代: VAD の自動応答は使わず（`create_response: false`）、次のように制御する
  1. ユーザ発話が確定するたびに、Realtime モデルに会話に残らない裏側の応答（out-of-band）で
     `decide_turn` 関数を必ず呼ばせ、RESPOND（返事）/ BACKCHANNEL（相づちのみ）/ WAIT（黙る）を判定（0.4 秒前後）
  2. RESPOND → 通常の応答、BACKCHANNEL →「相づちを一言だけ」の指示を差し込んで応答、WAIT → 何もしない
  3. 誰も話さない状態が `PROACTIVE_SILENCE_SEC`（既定 8 秒）続いたら、AI から話しかける（ユーザが話すまで 1 回のみ）
     - まだ誰も話していない: 挨拶など、会話の始まりにふさわしい一言
     - 会話の途中: 感情推定が出した「次にすべきこと」を添えて、後輩の立場で話しかける
     - 段階が「まとめ」「終了」: 一度だけ短く締め（お礼・作業に戻る一言）、以降は話しかけない
  - 判定基準・相づち/話しかけの指示は [backend/turn_taking.py](backend/turn_taking.py) で調整できる
  - AI の発話中にユーザが話し始めた場合は、従来どおり AI が話すのをやめる

```
run.py                起動スクリプト（exe 化のエントリポイント）
communication_helper.spec  PyInstaller のビルド設定（exe 化の手順で生成・更新）
image/                会話相手の表情画像
backend/
  main.py             API エンドポイント・静的ファイル配信
  config.py           .env の読み込み、開発時 / exe 実行時のパスの切り替え
  personas.py         ペルソナ・シナリオ定義と指示文の生成
  realtime_client.py  Realtime API への接続（キー発行・SDP 交換）
  emotion.py          受け手の感情推定（評価プロンプト・JSON スキーマ）
  voice.py            声の特徴量の判定（閾値）とプロンプト用の整形
  report.py           振り返りレポートの生成
  turn_taking.py      話者交代の判定指示・相づち/話しかけの指示
frontend/
  index.html / app.js / style.css
  voice-analyzer.js   マイク音声の声量・声の高さの計測、モーラ数の概算
```

## 起動方法

```bash
cd 007_prototype/001_communication_helper
pip install -r requirements.txt
cp .env.example .env   # 接続情報を記入
python run.py          # または python -m uvicorn backend.main:app --port 8000
```

ブラウザで http://localhost:8000 を開き、マイクの使用を許可する。
イヤホンを使うと、AI の声をマイクが拾ってしまう問題を避けられる。

## 環境変数

| 変数 | 説明 | 既定値 |
|---|---|---|
| AZURE_OPENAI_ENDPOINT | `https://<resource>.services.ai.azure.com/openai/v1` | - |
| AZURE_OPENAI_KEY | API キー | - |
| AZURE_REALTIME_DEPLOYMENT | Realtime モデルのデプロイ名 | gpt-realtime-mini |
| AZURE_TRANSCRIBE_MODEL | 文字起こしモデルのデプロイ名 | gpt-transcribe |
| AZURE_EVAL_DEPLOYMENT | 感情推定に使うチャットモデルのデプロイ名 | gpt-5.4-mini |
| SESSION_MAX_MINUTES | 1 セッションの上限時間（分） | 10 |
| PROACTIVE_SILENCE_SEC | 誰も話さない状態がこの秒数続いたら AI から話しかける | 8 |

## exe化(PyInstaller)

配布用に `communication_helper.exe` を作成する手順です。構成は `011_chat_linkage` と同じく、
PyInstaller の `--onedir` 形式でビルドし、exe と同じフォルダに `.env` を置いてフォルダごと zip 化して配布します。
エンドユーザー向けの利用方法は [manual.md](manual.md) を参照してください。

### 1. PyInstaller のインストール

```bash
pip install pyinstaller
```

アプリ本体の依存ライブラリ（`requirements.txt`）も、ビルドする Python 環境にインストールしておくこと。

### 2. ビルド

`001_communication_helper` ディレクトリ直下（`run.py` と同じ階層）で以下を実行します。

```powershell
pyinstaller --name communication_helper `
  --onedir `
  --noconfirm `
  --paths . `
  --add-data "frontend;frontend" `
  --add-data "image;image" `
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
  --exclude-module numpy `
  --exclude-module PIL `
  --exclude-module cryptography `
  --exclude-module bcrypt `
  --exclude-module tkinter `
  run.py
```

一度上記を実行すると、同じ設定が `communication_helper.spec` に保存される。2回目以降は次のコマンドでも同じビルドができる。

```powershell
pyinstaller communication_helper.spec --noconfirm
```

各オプションの意味:

- `run.py`（エントリポイント）: `backend/main.py` はパッケージ内の相対 import（`from .config import ...`）を使っており、
  PyInstaller のエントリスクリプト（トップレベルのスクリプトとして実行される）にはできないため、
  `backend` パッケージを import して uvicorn を起動する `run.py` をエントリにしている。
- `--onedir`: exe と依存ライブラリを同じフォルダに展開する形式。`--onefile` は起動のたびに一時フォルダへ全ライブラリを展開するため使用しない。
- `--paths .`: `run.py` から `backend` パッケージを import できるよう、カレントディレクトリを import 探索パスに追加する。
- `--add-data "frontend;frontend"` / `--add-data "image;image"`: 画面（HTML / JS / CSS）と表情画像を `_internal/` 配下に同梱する。
  `backend/config.py` の `RESOURCE_DIR` は、exe 実行時に `_internal/`（`sys._MEIPASS`）を指すようになっているため、同梱先はそれぞれ `frontend` / `image` にする。
- `--hidden-import uvicorn.*`: uvicorn は動的 import が多く、PyInstaller の静的解析だけでは検出できないモジュールがあるため明示指定する。
- `--exclude-module numpy` 等: アプリでは使わないが、ビルドに使う Python 環境に入っている他のパッケージの依存として
  静的解析で巻き込まれるライブラリを除外する（除外しない場合は約 90MB、除外後は約 40MB）。
  ビルド環境によって巻き込まれるライブラリは変わるため、`dist/communication_helper/_internal/` に大きな不要フォルダがあれば同様に除外を追加する。

ビルドが終わったら、配布する前に必ず `dist/communication_helper/` に `.env` を置いて exe を起動し、
画面の表示・音声会話・感情推定・振り返りレポートが動作することを確認すること。

### 3. 配布用ファイルの配置

ビルドすると `dist/communication_helper/` フォルダに `communication_helper.exe` 本体と `_internal/`（依存ライブラリ・画面・画像）が生成される。
この `dist/communication_helper/` フォルダに、exe と同じ階層で以下を追加する（PyInstaller では同梱されないため手動で配置する）。
exe 実行時は `.env` を **exe と同じフォルダ** から読み込む（開発時は `001_communication_helper` 直下を参照）。

- `.env` — Azure OpenAI の接続情報とアプリの設定（`.env.example` をコピーして編集）
  ```
  AZURE_OPENAI_ENDPOINT=https://<resource>.services.ai.azure.com/openai/v1
  AZURE_OPENAI_KEY=<your-api-key>
  AZURE_REALTIME_DEPLOYMENT=gpt-realtime-mini
  AZURE_TRANSCRIBE_MODEL=gpt-transcribe
  AZURE_EVAL_DEPLOYMENT=gpt-5.4-mini
  SESSION_MAX_MINUTES=10
  PROACTIVE_SILENCE_SEC=8
  ```
- `起動.bat`（任意）— ダブルクリックで exe の起動とブラウザを開くショートカット
  ```bat
  @echo off
  start "" http://localhost:8000
  communication_helper.exe
  ```
  サーバの起動より先にブラウザが開くため、最初に「接続できません」と表示された場合は数秒後にページを再読み込みする。

### 4. zip化するフォルダ構成

配布時は、フォルダ名を配布用の名称（例: `communication_practice`）にリネームしたうえで、以下の構成一式を zip 化する。
エンドユーザー向けの利用手順は [manual.md](manual.md) を参照（または同梱）。

```
communication_practice/          ← このフォルダごと zip 化して配布する（dist/communication_helper/ をリネーム）
├── communication_helper.exe     ... アプリ本体（PyInstaller が生成）
├── _internal/                   ... 依存ライブラリ・画面・表情画像（PyInstaller が生成。触らない）
├── .env                         ... 接続情報・設定（手動配置。3. 参照）
└── 起動.bat                      ... 起動用ショートカット（任意、手動配置）
```

manual.md 内の「1. フォルダ構成」もこの構成と対応しているため、フォルダ名を変更する場合は manual.md 側の記載も合わせて更新すること。

### 5. 利用時の注意（配布先への案内事項）

- `起動.bat`（または `communication_helper.exe`）を実行すると黒いウィンドウ（サーバ）が開く。使い終わったらこのウィンドウを閉じると終了する。
- 黒いウィンドウがすぐに閉じてしまう場合は、exe と同じフォルダに `.env` が無いか、`AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_KEY` が未設定であることが多い
  （起動時にエラーで終了する）。原因を確認したいときは、PowerShell 等で exe のフォルダに移動して `.\communication_helper.exe` を実行するとエラー内容が表示される。
- ブラウザで http://localhost:8000 を開き、マイクの使用を許可する。マイクは `localhost` でのみ使えるため、
  ほかの PC から IP アドレスでアクセスする使い方はできない。
- 8000 番ポートを使う別のアプリ（`011_chat_linkage`・`016_ai_learning_portal` など）と同時には起動できない。
- Azure OpenAI と、グラフ描画ライブラリ（Chart.js、CDN から読み込み）を使うため、インターネット接続が必要。
- `.env` には API キーが含まれるため、zip を社外に渡したり、共有フォルダに置いたりしないこと。
  配布先ごとにキーを分けたい場合は、配布前に `.env` の `AZURE_OPENAI_KEY` を差し替える。
- イヤホンの使用を推奨（AI の声をマイクが拾うのを防ぐ）。
