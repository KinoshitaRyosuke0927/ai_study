メモ：電話応対AI
PBX / クラウドPBXで着信ルーティングする
PBXとは、会社の内線や着信振り分けを管理する電話交換機です。最近はクラウドPBXも多いです。

**実務上のおすすめ**
最初のPoCなら、次のどちらかが現実的です。

- 既存番号 → 転送 → AI受付用クラウド電話番号
- 既存番号をクラウドPBXへ収容し、着信をAIへルーティング

最初から固定電話回線を直接PCへつなぐより、クラウドPBXやSIP基盤を1枚挟む方が作りやすいです。

C. クラウド電話サービス経由でPCに渡す

一番作りやすいのはこれです。

- 着信をクラウド電話基盤で受ける
- 着信イベントをWebhookで受信
- 音声をストリーミングAPIでアプリへ送る
- PC上またはサーバー上のAIが処理

この場合、厳密には「PCが直接固定電話回線を受ける」というより、「クラウドが受けた着信をPCアプリが扱う」形です。
でも実装上はこちらの方が圧倒的に楽です。

実務上の結論

「固定電話をPCでキャッチしたい」は、次のように読み替えるのが安全です。

- 固定電話番号への着信を、SIPまたはクラウド電話APIで扱える形にする
- その後PC/サーバーで処理する

この考え方にすると、設計がかなり楽になります。

**構成要素**
1. 音声認識

人間の話をテキスト化する部分です。
いわゆる STT です。

2. 会話エンジン

認識した内容を理解して、返答方針を決める部分です。
LLM やルールエンジンがここに入ります。

3. 音声合成

返答を音声で話す部分です。
いわゆる TTS です。
典型的にはこう動きます。

- 相手が話す
- 音声認識が文字化
- 会話エンジンが返答を生成
- 音声合成で読み上げる
- 必要なら人間に転送する

**実現レベル**
現在の技術では、次のような用途は十分可能です。

- 営業時間案内
- 担当部署への振り分け
- よくある問い合わせ対応
- 折り返し受付
- 予約受付の一次対応
- 用件ヒアリング

一方で、次は難しさが上がります。

- 雑音の多い環境での高精度対話
- 長い説明を正確に聞き取る
- 曖昧な依頼をミスなく事務処理する
- 法務・医療など厳密性が必要な会話
- 感情的なクレーム対応

つまり、「完全自律の電話秘書」はまだ設計が重要で、「限定された受付業務」ならかなり現実的、というのが実態です。


**想定するシナリオ**
1. AICに電話がかかってくる
2. 電話をAIで受け取る(固定電話の着信音はならない)
3. 電話相手が話したい相手を聞き出し、その人に取り次ぐ(AIの読み上げ or チャットで通知)

**拡張機能**
- 話したい相手のスケジュールを確認して応対可能か返答する
- 話したい相手が執務室にいるかを確認して応対可能か返答する
- チャットで指定して、相手に電話をかけてメッセージを伝える
- 通話相手の要件を聞き出してチャットで伝える


**おすすめフロー**

1. 既存番号はそのまま
2. 必要に応じてAI受付番号へ転送(まずは木下からかかってきた電話をすべて転送)
3. AI受付番号はクラウド電話サービスで受信
4. クラウド電話サービスからPC/サーバーへWebhookや音声ストリームで送信
5. AIが応答
6. 必要に応じて人へ転送、あるいはチャットで通知

| サービス           | 向いている使い方         | 利用方法のイメージ                                         | 料金の傾向                | 簡単さ                     |
| -------------- | ---------------- | ------------------------------------------------- | -------------------- | ----------------------- |
| Twilio         | 開発者向けPoC、本格API連携 | 番号取得 → 着信Webhook → 音声制御 → 必要ならMedia Streams等でAI連携 | 従量課金中心になりやすい         | 高いが開発は必要                |
| Vonage         | APIで音声制御したい      | 番号取得 → Voice API → Webhook/音声制御                   | 従量課金中心               | Twilioに近い               |
| Plivo          | 音声API中心で比較検討     | 着信Webhook → 音声応答/転送                               | 比較的シンプルな従量課金構造になりやすい | API実装は必要                |
| Telnyx         | SIP/音声API両方見たい   | 音声APIまたはSIP接続                                     | 用途次第で細かく変わる          | やや技術寄り                  |
| クラウドPBX系国内サービス | まず電話運用を整えたい      | 管理画面で着信ルール、転送、IVR設定                               | 月額課金が分かりやすいことが多い     | 非常に始めやすいがAIリアルタイム連携は要確認 |


PoCの簡単さだけで並べると、だいたいこう考えると分かりやすいです。

- 一番始めやすい: 国内クラウドPBX
- 開発しやすく情報量も多い: Twilio
- 比較候補: Vonage, Plivo
- SIPも含めて柔軟だがやや技術寄り: Telnyx

AI電話受付PoCで特に確認すべき機能は次です。

- 日本で取得できる番号種別
- 既存番号から転送して使えるか
- 着信時Webhook
- 音声ファイル再生
- TTS連携
- 録音
- 人への転送
- リアルタイム音声ストリーミング
- 日本語音声との相性
- 通話ログ取得

Vonage : SIPトランキング
https://www.vonagebusiness.jp/communications-apis/sip-trunking/


### Genspark

以下は「事務所に入ってくる電話を **Vonage に転送** → **AIが自動応対**」という PoC を、なるべく Python で最短に立ち上げるために必要な **Vonage 側の“買うもの/使うもの”** と **実装の全体像** です。結論から言うと、まず必要なのは **Vonage Communications APIs の Voice API + 電話番号（Virtual Number）+ Voice Application（Webhook設定）** です。通話音声をAIに渡してリアルタイム応答したい場合は、NCCO の `connect` で **WebSocket に通話音声をストリーミング**するのが王道です。 [Vonage Voice API WebSockets](https://developer.vonage.com/en/voice/voice-api/concepts/websockets)

---

## 1. PoCで必要な Vonage のソリューション（何を契約/購入するか）

### 必須： [Vonage Voice API](https://developer.vonage.com/en/voice/voice-api/ncco-reference)（音声通話の制御）
Vonage の「Voice API」は、電話の着信時に **Answer Webhook** にHTTPリクエストを飛ばし、あなたのサーバが返す **NCCO(JSON)** によって通話フロー（挨拶、転送、録音、WebSocket接続など）を制御します。 [Vonage NCCO Reference](https://developer.vonage.com/en/voice/voice-api/ncco-reference)

### 必須：検証用の **電話番号（Virtual Number）** を購入
事務所の電話を「転送」する先として、Vonageで受ける番号が必要です（国/用途により購入可能な番号種別が変わります）。サンプルリポジトリでも「Vonage番号を買う」→「アプリに紐付け」が手順に含まれています。 [GitHub sample](https://github.com/Vonage-Community/tutorial-voice-python-websocket_echo_server)

### 必須： [Voice Application](https://developer.vonage.com/en/voice/voice-api/webhook-reference)（Webhook URL を持つ“アプリ”）
Vonage では「番号」だけで動かず、番号を **Application（Voice対応）** にリンクし、その Application に **Answer webhook / Event webhook** を設定します。Webhooks は Voice API の中核で、少なくとも2つ（Answer / Event）が必須です。 [Voice API Webhook Reference](https://developer.vonage.com/en/voice/voice-api/webhook-reference)

---

## 2. 全体アーキテクチャ（転送 → AI応対）の最小構成

### A. “いちばん簡単”な PoC（電話会社/PBXの転送設定を使う）
1) 事務所の既存番号（PBXやキャリア）で **Vonageの検証番号へ無条件転送/時間外転送**  
2) Vonage が着信 → あなたの **Answer Webhook** を叩く  
3) Webhook が NCCO を返す（例：挨拶→WebSocketへ接続）  
4) WebSocketで通話音声（PCM）が双方向に流れるので、AI（STT→LLM→TTS）へ接続して応答音声を通話へ返す  

この「WebSocketで通話音声をリアルタイムに出し入れ」する用途が、Vonage Voice API WebSockets の想定ユースケースです。 [Vonage Voice API WebSockets](https://developer.vonage.com/en/voice/voice-api/concepts/websockets)

### B. PBXと“電話回線として”きれいに繋ぐ（SIPを使う）選択肢
既存PBX（Asterisk等）があり SIP 連携したい場合は **Programmable SIP** が候補になります。Vonage 側で SIP Domain を作り、SIP URI 宛の呼があなたの Application の `answer_url` に来る、という設計ができます。 [Programmable SIP](https://developer.vonage.com/en/voice/voice-api/concepts/programmable-sip)

---

## 3. Vonage 側の設定手順（PoCの最短ルート）

### Step 0：Webhook を公開できるURLを用意
Vonage からあなたのサーバへHTTP/HTTPSで到達できる必要があります。ローカル開発なら ngrok 等で一時公開URLを作るのが定番で、Vonage公式サンプルでもその前提が書かれています。 [GitHub sample](https://github.com/Vonage-Community/tutorial-voice-python-websocket_echo_server)

### Step 1：Voice Application を作る（Answer/Event Webhook を設定）
- **Answer webhook**：着信“応答時”に呼ばれ、NCCOを返す
- **Event webhook**：通話中のイベント（開始/切断など）が飛んでくる（ログ/監視/フォールバック制御に重要）

この2つが必須です。 [Voice API Webhook Reference](https://developer.vonage.com/en/voice/voice-api/webhook-reference)

### Step 2：検証用の番号を購入して、Application にリンク
番号を買い、Applicationにリンクすると、その番号への着信が Answer webhook に届くようになります（CLIでもDashboardでも可）。手順例は公式コミュニティサンプルにまとまっています。 [GitHub sample](https://github.com/Vonage-Community/tutorial-voice-python-websocket_echo_server)

---

## 4. Python実装（まず“WebSocketに繋がる”ところまで）

### 4.1 Answer Webhook（NCCOを返して WebSocket に接続）
VonageのPythonチュートリアルの最小例（Flask）が分かりやすいです。着信時に `talk` で一言流し、その後 `connect` で `type: websocket` に繋ぎます。 [Python tutorial](https://developer.vonage.com/en/tutorials/connect-to-a-websocket/write-answer-webhook/python)

```python
from flask import Flask, request, jsonify
from flask_sock import Sock

app = Flask(__name__)
sock = Sock(app)

@app.route("/webhooks/answer")
def answer_call():
    ncco = [
        {"action": "talk", "text": "ただいまAIで応対します。少々お待ちください。"},
        {
            "action": "connect",
            "endpoint": [
                {
                    "type": "websocket",
                    "uri": f"wss://{request.host}/socket",
                    "content-type": "audio/l16;rate=16000",
                }
            ],
        },
    ]
    return jsonify(ncco)
```

この `content-type`（例：`audio/l16;rate=16000`）は WebSocket の音声品質指定で、音声認識（STT）用途でよく使われます。 [Vonage Voice API WebSockets](https://developer.vonage.com/en/voice/voice-api/concepts/websockets)

### 4.2 WebSocketサーバ（通話音声の受信/送信）
Vonage WebSockets では、あなたのアプリは以下を扱います。

- Vonage → あなた：**バイナリ（音声PCMチャンク）** と **テキスト（JSONイベント）**
- あなた → Vonage：**バイナリ（通話へ流す音声）** と **テキスト（再生制御コマンド等）**

と明記されています。 [Vonage Voice API WebSockets](https://developer.vonage.com/en/voice/voice-api/concepts/websockets)

まずは公式の「エコーサーバ」（受けた音声をそのまま返す）を動かすのが最短で、PoCの導通確認に最適です：  
- サンプル: [Vonage-Community/tutorial-voice-python-websocket_echo_server](https://github.com/Vonage-Community/tutorial-voice-python-websocket_echo_server)

---

## 5. AI応対（STT→LLM→TTS）を繋ぐ時の要点（Vonage側制約）

### 音声バッファ/割り込み（barge-in相当）の考慮
Vonage 側には WebSocket のバッファがあり、再生はキューされます。途中で再生を止めたい場合は **`clear` コマンド**が必要、という運用上の注意があります（AIが話している途中でユーザが割り込む等）。 [Vonage Voice API WebSockets](https://developer.vonage.com/en/voice/voice-api/concepts/websockets)

### 切断・エラー時のフォールバック
WebSocket が切断されると `disconnected` イベントが上がる等、イベント駆動でフェイルオーバー（「ただいま担当にお繋ぎします」など）を設計できます。Event webhook は全イベントが届く前提です。 [Voice API Webhook Reference](https://developer.vonage.com/en/voice/voice-api/webhook-reference)

---

## 6. 「結局どれを買えば？」を一枚で整理

| 目的 | Vonageで必要なもの | 実装で必要なもの |
|---|---|---|
| 検証用に“着信できる番号”が欲しい | Virtual Number（購入） | なし（転送元の設定だけ） |
| 着信時に自分のサーバで制御したい | Voice Application（Answer/Event webhook） | 公開HTTPSサーバ（Flask等） |
| AIに通話音声をリアルタイムで渡し、返答音声を返したい | Voice API + NCCO `connect` WebSocket | WebSocketサーバ + STT/LLM/TTS |
| PBXとSIPでつなぎたい | Programmable SIP（SIP Domain等） | SIP側設定（PBX/回線） |

WebSocket連携が「AI応対」PoCの最短で、Vonageも“音声を双方向にストリーミングする”前提をガイドしています。 [Vonage Voice API WebSockets](https://developer.vonage.com/en/voice/voice-api/concepts/websockets)

---

## 7. 参考（図・デモ・学習リソース）

- 図（Vonage公式ブログのサムネ/図）：Streaming Calls to a Browser with Voice WebSockets  
  https://developer.vonage.com/en/blog/streaming-calls-to-a-browser-with-voice-websockets-dr （画像検索結果より）  
- 公式ワークショップ動画（Voice API入門）：Vonage Campus 2019: Getting started with Voice API  
  https://www.youtube.com/watch?v=93Z86UkR_kg （動画検索結果より）
- サンプル実装（Python, WebSocket echo）：  
  https://github.com/Vonage-Community/tutorial-voice-python-websocket_echo_server

---

## 次に確認したいこと（ここが決まると設計を確定できます）
1) **既存の事務所回線**は「キャリア直収容の固定電話」でしょうか、それとも **PBX（Asterisk等）/クラウドPBX** でしょうか？（前者なら“単純転送”でOK、後者ならSIP連携も検討価値あり） [Programmable SIP](https://developer.vonage.com/en/voice/voice-api/concepts/programmable-sip)  
2) AI応対は **リアルタイム（会話）** が必須ですか？ それとも **留守電→文字起こし→折返し**でもPoCとして十分ですか？（リアルタイムは割り込み・遅延設計が要点になります） [Vonage Voice API WebSockets](https://developer.vonage.com/en/voice/voice-api/concepts/websockets)

上の2点を教えてもらえれば、次は「Pythonでの最小AIボット構成（WebSocket受信→STT→LLM→TTS→WebSocket送信）」を、Vonageの音声フォーマット（L16/16k等）前提で、動く単位まで具体化して提示します。
