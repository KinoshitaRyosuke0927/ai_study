# 操作マニュアル自動生成アプリケーション

画面録画動画をアップロードすると、Google Gemini 2.5 Pro が動画を解析して操作マニュアルを自動生成します。

## 構成

```
movie_to_manual/
├── backend/          # Python FastAPI
└── frontend/         # React (Vite) + TypeScript + Tailwind CSS
```

## 前提条件

- Python 3.11+
- Node.js 18+
- FFmpeg（キーフレーム抽出に使用。未インストールの場合はモックフォールバック）
- Google Gemini API キー（未設定の場合はモックデータを返す）

## セットアップと起動

### バックエンド

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# .env を開いて GEMINI_API_KEY を設定してください
uvicorn main:app --reload --port 8000
```

### フロントエンド

```bash
cd frontend
npm install
npm run dev
```

## アクセスURL

| サービス | URL |
|---------|-----|
| フロントエンド | http://localhost:5173 |
| バックエンドAPI | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |

## APIエンドポイント

| メソッド | パス | 説明 |
|---------|------|------|
| `GET` | `/api/health` | ヘルスチェック |
| `POST` | `/api/upload` | 動画アップロード |
| `POST` | `/api/generate` | マニュアル生成 |
| `GET` | `/api/manual/{id}/html` | HTMLマニュアル表示 |
| `GET` | `/api/manual/{id}/download` | HTMLマニュアルダウンロード |

## 確認チェックリスト

```
□ backend/.env.example に GEMINI_API_KEY の記載がある
□ GET /api/health → {"status":"ok"} が返る
□ モックモード（GEMINI_API_KEY未設定）でマニュアルが生成される
□ フロントエンドの3画面遷移（idle→processing→completed）が動作する
□ http://localhost:8000/docs でSwagger UIが表示される
□ HTMLダウンロードボタンが機能する
```

## 環境変数

| 変数名 | デフォルト | 説明 |
|--------|-----------|------|
| `GEMINI_API_KEY` | - | Gemini API キー（必須、未設定でモックモード） |
| `UPLOAD_DIR` | `uploads` | 動画アップロード先ディレクトリ |
| `OUTPUT_DIR` | `outputs` | マニュアル出力先ディレクトリ |
| `MAX_FRAMES` | `30` | キーフレーム最大枚数 |
| `SCENE_THRESHOLD` | `0.3` | シーン変化検出閾値（0.0〜1.0） |
