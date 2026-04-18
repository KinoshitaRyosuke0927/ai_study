# Graph GUI

PythonファイルをASTで解析し、関数呼び出しグラフとフローチャートをブラウザで可視化するWebアプリケーションです。

## 機能

- Pythonファイル（単一・複数）をアップロードして関数呼び出しグラフを生成
- 各関数のフローチャートをCytoscape.js形式で可視化
- Azure OpenAI を使用してフローチャートのラベルを日本語化

## 必要なソフトウェア

- Python 3.10 以上
- pip

## 環境変数の設定

Azure OpenAI への接続に以下の環境変数が**必須**です。

| 環境変数名 | 必須 | 説明 |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | **必須** | Azure OpenAI のエンドポイント URL |
| `AZURE_OPENAI_KEY` | **必須** | Azure OpenAI の API キー |
| `AZURE_API_VERSION` | 任意 | API バージョン（デフォルト: `2024-12-01-preview`）|
| `AZURE_MODEL_NAME` | 任意 | デプロイしたモデルの名称（デフォルト: `gpt-5-chat`）|

### .env ファイルを使用する方法（推奨）

アプリは起動時に **`graph_gui` の親ディレクトリ（`education/`）にある `.env` ファイル**を自動的に読み込みます。

`.env` ファイルが存在しない場合は以下の内容で作成してください。

```
education/
└── .env          ← このファイルを作成する
    graph_gui/
    └── app.py
```

**`.env` ファイルの記載例:**

```env
AZURE_OPENAI_ENDPOINT=https://<リソース名>.openai.azure.com/openai/deployments/<デプロイ名>/chat/completions?api-version=2025-01-01-preview
AZURE_OPENAI_KEY=<APIキー>
AZURE_API_VERSION=2024-12-01-preview
AZURE_MODEL_NAME=gpt-5-chat
```

> **注意:** `.env` ファイルには機密情報が含まれます。Git などのバージョン管理システムにコミットしないよう `.gitignore` に追加してください。
>
> ```gitignore
> .env
> ```

### 環境変数を直接設定する方法

`.env` ファイルを使わずにシェルで直接設定することもできます。

**Windows（PowerShell）:**

```powershell
$env:AZURE_OPENAI_ENDPOINT = "https://<リソース名>.openai.azure.com/..."
$env:AZURE_OPENAI_KEY      = "<APIキー>"
```

**Linux / macOS:**

```bash
export AZURE_OPENAI_ENDPOINT="https://<リソース名>.openai.azure.com/..."
export AZURE_OPENAI_KEY="<APIキー>"
```

## インストール

```powershell
cd graph_gui
pip install fastapi uvicorn openai rustworkx python-multipart python-dotenv
```

## アプリケーションの起動

```powershell
cd graph_gui
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

起動後、ブラウザで以下のURLにアクセスしてください。

```
http://localhost:8000
```

## API エンドポイント

| メソッド | パス | 説明 |
|---|---|---|
| `GET` | `/` | フロントエンド（index.html）を返す |
| `GET` | `/api/graph` | 保存済みのグラフデータを取得 |
| `POST` | `/api/graph` | グラフデータを保存 |
| `POST` | `/api/analyze` | 単一の `.py` ファイルをアップロードして解析 |
| `POST` | `/api/analyze-multiple` | 複数の `.py` ファイルをアップロードして解析（統合グラフ生成）|
| `GET` | `/api/flowchart/{identifier}` | キャッシュ済みフローチャートを取得 |
| `POST` | `/api/flowchart` | Pythonコードからフローチャートを生成 |

## ファイル構成

```
graph_gui/
├── app.py                      # FastAPI サーバー（エントリーポイント）
├── analyze_and_visualize.py    # Pythonファイル解析 + Cytoscape形式への変換
├── generate_graph_json.py      # AST解析による呼び出しグラフ生成
├── flowchart_gen.py            # 制御フロー解析によるフローチャート生成
├── azure_ai_operation_service.py # Azure OpenAI API 呼び出し
├── azure_constant.py           # プロンプト定数
├── data/
│   ├── graph.json              # 最後に生成されたグラフデータ
│   └── flowcharts/             # 生成済みフローチャートのキャッシュ
└── static/
    └── index.html              # フロントエンド（Cytoscape.js 使用）
```

## コマンドラインからの単体実行

`analyze_and_visualize.py` はスクリプトとしても実行できます。

```powershell
# 単一ファイルを解析
python analyze_and_visualize.py path/to/target.py

# フォルダ内の全 .py ファイルを解析
python analyze_and_visualize.py src/

# 出力先を指定
python analyze_and_visualize.py path/to/target.py --out data/graph.json
```
