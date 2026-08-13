# PowerPoint AI レビュアー（re-architecture）

`.pptx` をアップロードすると、AIが「候補生成 → 過去レビュー参照 → 上司嗜好スコアリング → critic検証」の4層パイプラインでレビューを行うアプリです。[010_ai_reviewer](../010_ai_reviewer/) の後継として、固定観点のQ&A方式から、上司の確認観点・優先順位を再現するアーキテクチャに刷新しています。設計の背景は [docs/architecture.md](docs/architecture.md) を参照してください。

010_ai_reviewer は既存運用（exe配布・現行UI）のため引き続き独立して残しており、本アプリはそれとは別のアプリケーションです。

## できること
- `.pptx` をアップロードしてスライドを画像として表示（LibreOffice + Poppler による高品質レンダリング、010と同一の変換パイプライン）
- 資料全体の「伝えたいこと」・スライドごとの補足を入力
- Azure OpenAI を使い、候補生成 → 過去レビュー参照 → 上司嗜好スコアリング → critic検証の4層パイプラインで指摘事項（`issue` / `evidence` / `severity` / `manager_likeness` / `confidence` / `suggestion`）を生成
- AIによる修正提案（スライドごとの修正後画像＋修正内容の説明をSSEで順次表示。010の画像編集提案機能を移植）
- 修正提案のPDFダウンロード・指摘事項のMarkdownダウンロード

## セットアップ

### 1. 依存パッケージのインストール
```bash
pip install -r requirements.txt
```

### 2. LibreOffice のインストール（スライド画像化に必要）

**Windows**
[LibreOffice 公式サイト](https://www.libreoffice.org/download/) からインストーラーをダウンロードして実行します。
インストール後、`C:\Program Files\LibreOffice\program\soffice.exe` が自動的に検出されます。

### 3. Poppler のインストール（PDF→画像変換に必要）

**Windows**
[poppler-windows releases](https://github.com/oschwartz10612/poppler-windows/releases/) から最新版の zip をダウンロードし、展開後に `bin` フォルダをシステム PATH に追加してください。

### 4. 環境変数の設定
ワークスペースルート（`014_re_ai_reviewer` の1つ上の階層）に `.env` を作成し、Azure OpenAI の接続情報を記載してください（010_ai_reviewer と同じ `.env` を共有します）：
```
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/openai/deployments/your-deployment/
AZURE_OPENAI_KEY=your-api-key
```

> テキスト系（候補生成・スコアリング・critic）には `gpt-5.4-mini`、AI修正提案の画像生成には `gpt-image-2` / `gpt-image-2-2` を使用します。

### 5. サーバー起動
```bash
uvicorn app.main:app --reload --port 8000
```

ブラウザで `http://127.0.0.1:8000` を開いてください。

## Dockerでの起動

```bash
docker build -t re-ai-reviewer .
docker run --rm -p 8000:8000 --env-file ../.env re-ai-reviewer
```

`http://127.0.0.1:8000` で起動します。

## Azureへのデプロイ

`infra/containerapp.json`（Azure Container Apps 用ARMテンプレート）を用意しています。パラメータやデプロイ手順は [010_ai_reviewer/docs/azure_deploy.md](../010_ai_reviewer/docs/azure_deploy.md) の手順に準じます（リソース名は `re-ai-reviewer` 系に置き換えてください）。

## API エンドポイント

| メソッド | パス | 説明 |
|----------|------|------|
| GET | `/` | フロントエンド（index.html） |
| GET | `/api/health` | ヘルスチェック |
| POST | `/api/upload` | PPTX アップロード・スライド画像化 |
| POST | `/api/review` | 候補生成→過去レビュー参照→上司嗜好スコアリング→critic検証の4層パイプラインを実行し、指摘事項（Finding）一覧を返す |
| POST | `/api/suggest` | AIによるスライド修正提案（指摘事項をもとにSSEストリーミングで返却） |
| POST | `/api/suggest/export-pdf` | 修正後スライド画像をまとめて PDF 出力 |

## ファイル構成

```text
app/
  main.py                       FastAPI エントリポイント（upload / review / suggest / export-pdf）
  core/
    renderer.py                 LibreOffice + pdf2image によるスライド画像化（010から無改修で移植）
    azure_client.py             Azure OpenAI 呼び出し（テキスト: call_structured / 画像編集: call_image_edit）
  schemas/
    models.py                   Candidate / Finding / ReviewMemoryEntry 等のpydanticモデル
  prompts/
    candidate_prompts.py        候補生成層のプロンプト
    ranker_prompts.py           上司嗜好スコアリング層のプロンプト
    critic_prompts.py           critic検証層のプロンプト
    suggestion_prompts.py       画像編集提案（修正方針プラン・変更内容説明）のプロンプト
  pipeline/
    orchestrator.py             4層パイプラインの実行順序を制御
    candidate_generator.py      候補生成層
    review_memory.py            過去レビュー参照層（review_log.jsonlベース、データ未整備の間は空ログでフォールバック動作）
    manager_ranker.py           上司嗜好スコアリング層
    critic.py                   critic検証層
    suggestion.py               画像編集提案（010の/api/suggestを移植）
  static/                       フロントエンド（HTML / CSS / JS。010と同一デザイン、指摘事項タブのみ新形式）
data/
  seed_review_points.csv        候補生成層の観点シード（010の review_point.csv / pp_check_points.csv を統合）
  review_log.jsonl              過去レビュー指摘ログ（review_memory層が参照。データ整備中のため現状は空）
infra/
  containerapp.json             Azure Container Apps デプロイ用ARMテンプレート
Dockerfile                      コンテナ化定義（010と同じLibreOffice/Poppler/日本語フォント構成）
requirements.txt
```

## 010_ai_reviewer との違い

| 項目 | 010_ai_reviewer | 014_re_ai_reviewer |
|---|---|---|
| レビュー方式 | 固定観点でのQ&A形式チェック→要約 | 候補生成→過去レビュー参照→上司嗜好スコアリング→critic検証の4層パイプライン |
| 観点管理 | `review_point.csv` / `pp_check_points.csv` を直接レビューに使用、画面から apply_flag をON/OFF | 同CSVを統合した `seed_review_points.csv` を候補生成の「網羅観点ヒント」として使用（画面からの編集は非対応） |
| 過去レビューの扱い | 静的な観点として埋め込み | `review_log.jsonl` を検索してプロンプトに動的注入（データ整備中のため現状は0件でフォールバック） |
| 指摘結果の形式 | 観点カテゴリごとの要約文章 | スライド単位の `Finding`（issue / evidence / severity / manager_likeness / confidence / suggestion） |
| 画像編集提案 | あり（`/api/suggest`） | 移植済み（`/api/suggest`。指摘とスライドの対応づけがFinding生成時点で既に確定しているため、対応スライドをAIに判断させる工程は省略） |
| 想定質問生成・レビュー観点設定UI | あり | 未移植（新パイプラインに対応する機能が未整備のため） |

詳細な設計判断（なぜこの4層構成にしたか、review_memoryが空ログでも動く理由など）は [docs/architecture.md](docs/architecture.md) を参照してください。
