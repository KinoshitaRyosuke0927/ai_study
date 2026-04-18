# YouTube Live Archive Viewer (uploads ベース版)

## 概要
YouTube チャンネルの `uploads` プレイリストを起点に動画一覧を走査し、`videos.list` の `liveStreamingDetails` を使って **ライブ配信アーカイブ** を抽出する FastAPI + GUI アプリです。

`search.list(eventType=completed)` を直接使う方式より、過去ライブの取りこぼしを減らしやすい構成です。

## 取得する情報
- チャンネル基本情報
- ライブ配信アーカイブの最新50件
- 各動画の以下の情報
  - タイトル
  - 公開日
  - 動画ID
  - 動画の長さ
  - 視聴回数
  - サムネイル画像

## 入力形式
- `channel_id`
- `https://www.youtube.com/channel/...`
- `@handle`
- `https://www.youtube.com/@handle`

## 事前準備
Google Cloud で **YouTube Data API v3** を有効化し、API キーを発行してください。

環境変数に API キーを設定します。

### Windows (PowerShell)
```powershell
$env:YOUTUBE_API_KEY="AIzaSyBZx8kthL0tcbJT6apU4HNopZ2VNAG65eo"
```

### Windows (cmd)
```cmd
set YOUTUBE_API_KEY=YOUR_API_KEY
```

## セットアップ
```bash
pip install -r requirements.txt
```

## 起動
```bash
uvicorn app:app --reload
```

ブラウザで以下を開きます。

```text
http://127.0.0.1:8000
```

## 実装方針
1. `channels.list` でチャンネル基本情報と `uploads` プレイリストIDを取得
2. `playlistItems.list` で uploads の動画一覧を最大500件まで新しい順に走査
3. `videos.list` で動画詳細を取得
4. `liveStreamingDetails` をもとにライブアーカイブを抽出
5. 先頭から最大50件を表示

## 補足
- 走査上限は `MAX_SCAN_VIDEOS = 500` です。古いライブが多く、最新500本の中に50件見つからない場合は `app.py` のこの値を増やしてください。
- 非公開・限定公開動画は API の見え方により取得できない場合があります。
- YouTube 側のメタデータ状態によっては、一部の過去ライブが `liveStreamingDetails` に十分な情報を持たないことがあります。
