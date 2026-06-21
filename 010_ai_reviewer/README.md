# PowerPoint AI レビュアー

`.pptx` をアップロードしてスライドを画像として表示し、AI がレビューするアプリです。

## できること
- `.pptx` をアップロードしてスライドを画像として表示（LibreOffice による高品質レンダリング）
- スライドごとに「伝えたいこと」を入力
- Azure OpenAI を使って structure / visual / content の3観点で5点満点採点＋改善提案
- 全体評価・スライド別レビュー結果を画面に表示

## セットアップ

### 1. 依存パッケージのインストール
```bash
pip install -r requirements.txt
```

### 2. LibreOffice のインストール（スライド画像化に必要）

**Windows**
[LibreOffice 公式サイト](https://www.libreoffice.org/download/) からインストーラーをダウンロードして実行します。
インストール後、`C:\Program Files\LibreOffice\program\soffice.exe` が自動的に検出されます。

**Ubuntu / Debian**
```bash
sudo apt install libreoffice
```

### 3. Poppler のインストール（PDF→画像変換に必要）

**Windows**
[poppler-windows releases](https://github.com/oschwartz10612/poppler-windows/releases/) から最新版の zip をダウンロードし、展開後に `bin` フォルダをシステム PATH に追加してください。

**Ubuntu / Debian**
```bash
sudo apt install poppler-utils
```

### 4. 環境変数の設定
`education/.env` に Azure OpenAI の接続情報を記載してください：
```
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/...
AZURE_OPENAI_KEY=your-api-key
AZURE_API_VERSION=2024-12-01-preview
AZURE_MODEL_NAME=gpt-4o
```

### 5. サーバー起動
```bash
uvicorn app.main:app --reload --port 8010
```

ブラウザで `http://127.0.0.1:8010` を開いてください。

## API エンドポイント

| メソッド | パス | 説明 |
|----------|------|------|
| GET | `/` | フロントエンド（index.html） |
| GET | `/api/health` | ヘルスチェック |
| POST | `/api/upload` | PPTX アップロード・スライド画像化 |
| POST | `/api/review` | PPTX 解析 + AI レビュー実行 |

## スライド画像の仕組み

| 種別 | 形式 | 用途 |
|------|------|------|
| LibreOffice PNG (200 DPI) | PNG | スライドプレビュー（高品質）/ 将来の AI ビジョン API 用 |
| LibreOffice JPEG | JPEG | スライド一覧サムネイル（軽量） |
| Pillow 簡易レンダリング | PNG | LibreOffice 未インストール時のフォールバック |

LibreOffice が未インストールの場合、自動的に Pillow による簡易レンダリングにフォールバックします。
画面左上のスライドラベルに `LibreOffice` バッジが表示された場合は高品質レンダリングが有効です。

## ファイル構成
- `app/main.py` — FastAPI エントリポイント
- `app/renderer.py` — LibreOffice + pdf2image によるスライド画像化
- `app/slide_renderer.py` — Pillow による簡易サムネイル（フォールバック用）
- `app/pptx_parser.py` — `.pptx` の構造解析（テキスト・フォント・ヒューリスティックフラグ抽出）
- `app/prompt.py` — AI レビュー用プロンプト定義・レビュー観点・出力スキーマ
- `app/azure_ai_service.py` — Azure OpenAI 呼び出し
- `app/static/` — フロントエンド（HTML / CSS / JS）
