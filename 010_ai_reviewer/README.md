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
[LibreOffice 公式サイト](https://www.libreoffice.org/download/)あるいは[サイト](https://forest.watch.impress.co.jp/library/software/libreoffice/) からインストーラーをダウンロードして実行します。
インストール後、`C:\Program Files\LibreOffice\program\soffice.exe` が自動的に検出されます。

### 3. Poppler のインストール（PDF→画像変換に必要）

**Windows**
[poppler-windows releases](https://github.com/oschwartz10612/poppler-windows/releases/) から最新版の zip をダウンロードし、展開後に `bin` フォルダをシステム PATH に追加してください。

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
uvicorn app.main:app --reload --port 8000
```

ブラウザで `http://127.0.0.1:8010` を開いてください。

## API エンドポイント

| メソッド | パス | 説明 |
|----------|------|------|
| GET | `/` | フロントエンド（index.html） |
| GET | `/api/health` | ヘルスチェック |
| POST | `/api/upload` | PPTX アップロード・スライド画像化 |
| POST | `/api/review` | PPTX 解析 + AI レビュー実行 |

## ファイル構成
- `app/main.py` — FastAPI エントリポイント
- `app/renderer.py` — LibreOffice + pdf2image によるスライド画像化
- `app/prompt.py` — AI レビュー用プロンプト定義・レビュー観点・出力スキーマ
- `app/azure_ai_service.py` — Azure OpenAI 呼び出し
- `app/static/` — フロントエンド（HTML / CSS / JS）

## exe化（PyInstaller）

配布用に `ai_reviewer.exe` を作成する手順です。エンドユーザー向けの利用方法は [manual.md](manual.md) を参照してください。

### 1. PyInstaller のインストール
```bash
pip install pyinstaller
```

### 2. ビルド

`010_ai_reviewer` ディレクトリ直下（`app/` の一つ上の階層）で以下を実行します。

```powershell
pyinstaller --name ai_reviewer `
  --onedir `
  --noconfirm `
  --paths . `
  --add-data "app/static;static" `
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
  app/main.py
```

- `--onedir`（デフォルト）: exeと依存ライブラリを同一フォルダに展開する形式でビルドします。`--onefile` は起動のたびに一時フォルダへ全ライブラリを展開するため使用しません。
- `--paths .`: `app/main.py` が `from app.prompt import ...` のように `app` パッケージを絶対importしているため、その親ディレクトリ（カレントディレクトリ）をimport探索パスに追加します。
- `--add-data "app/static;static"`: フロントエンドの静的ファイルを同梱します。frozen実行時、エントリスクリプト（`app/main.py`）はサブフォルダの階層を保持せずトップレベルスクリプトとして組み込まれるため、`STATIC_DIR`（`app/main.py` の `BASE_DIR / "static"`）と一致させるには同梱先を `app/static` ではなく `static` にする必要があります。
- `--hidden-import uvicorn.*`: uvicornは動的importが多く、PyInstallerの静的解析だけでは検出できないモジュールがあるため明示指定します。

ビルド成果物は `dist/ai_reviewer/` フォルダに生成されます（`ai_reviewer.exe` 本体 + `_internal/` 配下の依存ライブラリ）。

### 3. 配布用ファイルの配置

`dist/ai_reviewer/` フォルダに、exeと同じ階層で以下を追加してください（PyInstallerには同梱されません）。

- `.env` — Azure OpenAI の接続情報（[manual.md](manual.md) の3-1を参照）
- `review_point.csv`（`010_ai_reviewer/review_point.csv` をコピー）— レビュー観点。exeの実行者が自由に編集できるよう、exeに同梱せず外部ファイルとして配置する構成にしています
- `起動.bat`（任意）— ダブルクリックでexe起動とブラウザオープンを行うショートカット
  ```bat
  @echo off
  start "" http://localhost:8000
  ai_reviewer.exe
  ```

`dist/ai_reviewer/` フォルダ一式を配布してください。実行環境側にはLibreOfficeとPopplerのインストールが別途必要です（[manual.md](manual.md) の2章を参照）。
