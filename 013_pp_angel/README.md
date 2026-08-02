# AI資料作成チャット（プロトタイプ）

チャットでAIとやり取りしながら資料の方向性を固め、スライドごとの資料イメージ（画像）を生成・修正できるプロトタイプアプリです。

## できること

- チャットでAIがヒアリングを進行（一度に資料を作らず、質問を重ねながら方向性を固める）
- AIが提示する選択肢をクリックして回答できる（テキストの選択肢／資料スタイルの画像案）
- 資料のスタイル案を3つ、画像イメージとして生成して提示（完成した案から順に表示）
- ヒアリングが完了すると、選択したスタイルをベースにスライドごとの資料イメージを自動生成（完成したスライドから順にカード表示）
- 各カードの入力欄に修正指示を入力し、「修正依頼」で該当スライドのみ一斉に再生成
- 資料イメージのカードをクリックして拡大表示
- 生成した資料イメージをまとめてPDFとしてダウンロード
- チャット履歴の初期化

## セットアップ

### 1. 依存パッケージのインストール
```bash
pip install -r requirements.txt
```

### 2. 環境変数の設定

ワークスペースルート（`013_pp_angel` の2つ上の階層）に `.env` を作成し、Azure OpenAI の接続情報を記載してください：
```
AZURE_OPENAI_ENDPOINT=https://your-resource.services.ai.azure.com/openai/v1
AZURE_OPENAI_KEY=your-api-key
```

> チャットの発言生成には `gpt-5.4-mini`、資料スタイル案・スライド画像の生成/編集には `gpt-image-2` を使用します。

### 3. サーバー起動
```bash
uvicorn app.main:app --reload --port 8000
```

ブラウザで `http://127.0.0.1:8000` を開いてください。

## API エンドポイント

| メソッド | パス | 説明 |
|----------|------|------|
| GET | `/` | フロントエンド（index.html） |
| GET | `/api/health` | ヘルスチェック |
| POST | `/api/chat` | チャット履歴を送信し、AIの発言・選択肢・スタイル案・スライド構成案（準備が整った場合）を返す |
| POST | `/api/chat/style-images` | 資料スタイル案ごとの画像を生成（SSEストリーミング） |
| POST | `/api/slides/generate` | スライド構成案とスタイル画像をもとに、スライドごとの資料イメージを生成（SSEストリーミング） |
| POST | `/api/slides/revise` | カードごとの修正指示にもとづき、対象スライドの資料イメージを修正（SSEストリーミング） |
| POST | `/api/slides/export-pdf` | 表示中の資料イメージをまとめてPDF出力 |

## ファイル構成

- `app/main.py` — FastAPI エントリポイント
- `app/prompt.py` — チャット用システムプロンプト（ヒアリング〜構造化出力のスキーマ定義）・画像生成/編集ガイダンス
- `app/azure_ai_service.py` — Azure OpenAI 呼び出し（チャット: `gpt-5.4-mini` / 画像生成・編集: `gpt-image-2`）
- `app/static/` — フロントエンド（HTML / CSS / JS）
- `images/` — チャットのAIアイコンなど、アプリで使用する画像素材
- `sample_story.md` — チャットの対話例・利用シナリオ

## チャットの構造化レスポンス

`/api/chat` は以下の形式のJSONを返します。AIは資料の方向性が十分に固まるまで `ready_to_generate: false` のまま質問を続け、固まった時点でスライド構成案を返します。

```json
{
  "message": "AIの発言",
  "options": ["選択肢", "..."] ,
  "style_proposals": [{"label": "案1", "image_prompt": "..."}, "..."],
  "ready_to_generate": false,
  "slide_plan": [{"slide_number": 1, "title": "...", "description": "..."}, "..."]
}
```

`style_proposals` が含まれる場合、フロントエンドは `/api/chat/style-images` を呼び出して画像を別リクエストで生成します（チャットの発言をすぐに表示できるようにするため）。
