
## ✅ 推奨プロンプト（完全版）

```
# 操作マニュアル自動生成アプリケーションの実装依頼

## プロジェクト概要
アプリケーションの画面録画動画をアップロードすると、
AIが動画を解析して操作マニュアルを自動生成するWebアプリケーションを作成してください。

## 技術スタック
- フロントエンド: React (Vite) + TypeScript
- バックエンド: Python FastAPI
- 動画処理: FFmpeg (ffmpeg-python ライブラリ経由)
- AI解析: Google Gemini 2.5 Pro API (google-generativeai)
- 構造化出力: Pydantic v2
- スタイル: Tailwind CSS

---

## ディレクトリ構成

以下の構成で作成してください：

```
project-root/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── VideoUploader.tsx      # 動画アップロードUI
│   │   │   ├── ProgressTracker.tsx    # 処理進捗表示
│   │   │   └── ManualViewer.tsx       # マニュアルプレビュー
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   └── vite.config.ts
│
├── backend/
│   ├── main.py                        # FastAPI エントリポイント
│   ├── routers/
│   │   └── manual.py                  # マニュアル生成API
│   ├── services/
│   │   ├── video_processor.py         # 動画前処理サービス
│   │   ├── gemini_analyzer.py         # Gemini AI解析サービス
│   │   └── manual_generator.py        # マニュアル生成サービス
│   ├── models/
│   │   └── schemas.py                 # Pydanticスキーマ定義
│   ├── templates/
│   │   └── manual_template.html       # マニュアルHTMLテンプレート
│   ├── uploads/                       # 一時アップロードフォルダ
│   ├── outputs/                       # 生成マニュアル出力フォルダ
│   ├── requirements.txt
│   └── .env.example
```

---

## 実装仕様

###【PHASE 1】シンプルパイプライン（必ず実装）

#### バックエンド実装

**① schemas.py - データモデル定義**

以下のPydanticモデルを定義してください：

```python
from pydantic import BaseModel
from typing import Optional

class ManualStep(BaseModel):
    step_number: int
    title: str                    # 例: "プロジェクトの新規作成"
    action_type: str              # click / input / scroll / navigate / other
    target_element: str           # 例: "画面左上の「新規作成」ボタン"
    description: str              # 詳細な操作説明（敬体で統一）
    expected_result: str          # 操作後に起きる変化
    screenshot_filename: str      # 対応するキャプチャ画像ファイル名

class ManualStructure(BaseModel):
    title: str                    # マニュアルタイトル
    overview: str                 # 操作全体の概要
    target_application: str       # 対象アプリケーション名
    prerequisites: list[str]      # 前提条件リスト
    steps: list[ManualStep]       # 操作ステップリスト

class GenerateRequest(BaseModel):
    video_filename: str

class GenerateResponse(BaseModel):
    status: str
    manual_id: str
    manual_html_url: str
    manual_json: ManualStructure
```

**② video_processor.py - 動画前処理サービス**

以下の機能を実装してください：

```python
# 実装すべき関数

def extract_keyframes(video_path: str, output_dir: str, threshold: float = 0.3) -> list[str]:
    """
    FFmpegのsceneフィルタを使って画面変化が大きいフレームのみ抽出する。
    
    実装方法:
    - ffmpeg-pythonライブラリを使用
    - select='gt(scene,{threshold})' フィルタを適用
    - 抽出したフレームをJPEG形式で output_dir に保存
    - 抽出したフレームのファイルパスリストを返す
    - thresholdは0.3をデフォルトとする（ボタンクリック程度の変化を検出）
    - 最大フレーム数を30枚に制限する（コスト管理）
    - フレームが0枚の場合は threshold を 0.1 に下げて再試行する
    
    引数:
        video_path: 入力動画ファイルパス
        output_dir: フレーム画像の出力ディレクトリ
        threshold: シーン変化の閾値 (0.0-1.0)
    
    戻り値:
        抽出されたフレーム画像のパスリスト（時系列順）
    """

def get_video_metadata(video_path: str) -> dict:
    """
    ffprobeを使って動画のメタデータ（時間、解像度、FPS）を取得する
    """
```

**③ gemini_analyzer.py - Gemini AI解析サービス**

以下の機能を実装してください：

```python
# 実装すべき関数

def analyze_video_with_gemini(
    video_path: str,
    frame_paths: list[str]
) -> ManualStructure:
    """
    Gemini 2.5 Pro APIを使って動画とフレームを解析し、
    ManualStructure形式の構造化データを返す。
    
    実装方法:
    - google.generativeai ライブラリを使用
    - モデル: gemini-2.5-pro-preview-06-05
    - 動画ファイルをGemini File APIでアップロードする (genai.upload_file)
    - ファイルのstate が ACTIVE になるまでポーリングして待機する
    - 以下のシステムプロンプトを使用すること：
    
    SYSTEM_PROMPT = """
    あなたはソフトウェア操作マニュアルの専門ライターです。
    提供された画面録画動画を分析し、初めてこのソフトを使うユーザーが
    迷わず操作できる、明確で具体的な操作マニュアルを作成してください。
    
    【文体ルール】
    - 敬体（〜してください、〜します）で統一すること
    - 1ステップ = 1アクションの原則を守ること
    - UI要素は【】で囲む（例：【ファイル】メニュー、【保存】ボタン）
    - 操作場所は具体的に記述（例：「画面左上のナビゲーションバー内」）
    
    【必須記述事項】
    - 各ステップで操作後に何が起きるか（expected_result）を必ず記述
    - 前提条件（どの画面から始まるか）を明記
    
    【出力形式】
    必ず以下のJSON形式で出力すること。他の文字列は含めないこと：
    {
      "title": "マニュアルタイトル",
      "overview": "この操作の概要（2〜3文）",
      "target_application": "アプリケーション名",
      "prerequisites": ["前提条件1", "前提条件2"],
      "steps": [
        {
          "step_number": 1,
          "title": "ステップのタイトル",
          "action_type": "click|input|scroll|navigate|other",
          "target_element": "操作対象のUI要素と場所",
          "description": "詳細な操作説明（敬体）",
          "expected_result": "操作後の画面変化",
          "screenshot_filename": ""
        }
      ]
    }
    """
    
    - response_mime_type="application/json" を指定してJSON出力を強制する
    - レスポンスをManualStructureでパースして返す
    - 各ステップにフレーム画像を割り当てる処理も行う
      （ステップ数とフレーム数を等分割してマッピング）
    
    引数:
        video_path: 解析する動画ファイルパス
        frame_paths: 抽出済みフレーム画像パスリスト
    
    戻り値:
        ManualStructure オブジェクト
    """
```

**④ manual_generator.py - マニュアル生成サービス**

以下の機能を実装してください：

```python
# 実装すべき関数

def generate_html_manual(
    manual: ManualStructure,
    frame_paths: list[str],
    output_dir: str,
    manual_id: str
) -> str:
    """
    ManualStructureからHTMLマニュアルを生成して保存する。
    
    実装方法:
    - Jinja2テンプレートエンジンを使用
    - フレーム画像をBase64エンコードしてHTMLに埋め込む（外部ファイル参照なし）
    - 生成したHTMLを output_dir/{manual_id}/manual.html に保存
    - HTMLのスタイルはインラインCSSで記述（外部CSS不要）
    
    HTMLの構成:
    1. ヘッダー: タイトル、概要、対象アプリ、前提条件
    2. ステップ一覧: 
       - ステップ番号（大きく表示）
       - スクリーンショット（横幅100%、角丸）
       - ステップタイトル
       - 操作対象（ラベル付き）
       - 詳細説明
       - 操作後の変化（薄い背景色のボックスで強調）
    3. 印刷用CSSも追加（@media print）
    
    スタイル要件:
    - 清潔感のある白背景デザイン
    - アクセントカラー: #2563EB（青）
    - ステップ番号は青丸で強調
    - フォント: システムフォント（日本語対応）
    
    戻り値:
        生成されたHTMLファイルのパス
    """
```

**⑤ main.py と routers/manual.py - APIエンドポイント**

以下のエンドポイントを実装してください：

```
POST /api/upload
  - 動画ファイルを受け取り、uploads/ に保存
  - Request: multipart/form-data (video_file)
  - Response: { "filename": "xxx.mp4", "size": 1234567 }

POST /api/generate
  - マニュアル生成パイプラインを実行
  - Request: { "video_filename": "xxx.mp4" }
  - Response: {
      "status": "success",
      "manual_id": "uuid",
      "manual_html_url": "/api/manual/uuid/html",
      "manual_json": { ...ManualStructure... }
    }

GET /api/manual/{manual_id}/html
  - 生成済みHTMLマニュアルを返す
  - Response: HTMLファイル (text/html)

GET /api/manual/{manual_id}/download
  - HTMLファイルをダウンロード
  - Response: HTMLファイル (attachment)

GET /api/health
  - ヘルスチェック
  - Response: { "status": "ok" }
```

CORS設定:
- フロントエンド開発サーバー (http://localhost:5173) からのアクセスを許可すること

**⑥ .env.example と設定**

```
GEMINI_API_KEY=your_gemini_api_key_here
UPLOAD_DIR=uploads
OUTPUT_DIR=outputs
MAX_FRAMES=30
SCENE_THRESHOLD=0.3
```

---

#### フロントエンド実装

**App.tsx - メインコンポーネント**

以下の3つの画面状態を管理してください：
1. `idle` - 初期状態（アップロード待ち）
2. `processing` - 処理中（進捗表示）
3. `completed` - 完了（マニュアル表示）

**VideoUploader.tsx**

- ドラッグ&ドロップ対応のファイルアップロードエリア
- 対応フォーマット: mp4, mov, avi, webm
- ファイルサイズ上限: 500MB
- アップロード後、自動的に /api/generate を呼び出す
- アップロード中はプログレスバーを表示

**ProgressTracker.tsx**

以下のステップをアニメーション付きで表示してください：
1. ✅ 動画のアップロード完了
2. ⏳ キーフレームの抽出中...
3. ⏳ AIによる動画解析中...（※数十秒かかる旨を表示）
4. ⏳ マニュアルの生成中...

実装方法：
- バックエンドの /api/generate が完了するまでの間、
  フロントエンド側でタイマーで各ステップを疑似的に進行させる
  （実際の処理時間に合わせて各ステップの待機時間を設定）

**ManualViewer.tsx**

- 生成されたManualStructureのJSONをもとに以下を表示：
  - マニュアルタイトル（大見出し）
  - 概要・前提条件（カード形式）
  - 各ステップ（番号、タイトル、スクリーンショット、説明）
- 「HTMLとしてダウンロード」ボタンを追加
- 「別の動画で試す」ボタンで初期状態に戻れるようにする

---

### 【PHASE 2】品質向上オプション（Phase 1完成後に追加）

以下は Phase 1 完成後に追加する機能としてコメントアウトした状態でコードに含めてください：

1. OpenAI GPT-4o による2段階解析 (gemini_analyzer.py に追加)
2. Whisper音声認識との組み合わせ
3. OpenCVによるカーソル位置検出
4. sentence-transformers による重複ステップマージ

---

## requirements.txt の内容

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
python-multipart==0.0.9
pydantic==2.7.0
pydantic-settings==2.3.0
google-generativeai==0.8.0
ffmpeg-python==0.2.0
Jinja2==3.1.4
python-dotenv==1.0.1
aiofiles==23.2.1
openai==1.40.0
```

## package.json の主要依存関係

```json
{
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "axios": "^1.7.0"
  },
  "devDependencies": {
    "typescript": "^5.4.0",
    "vite": "^5.3.0",
    "tailwindcss": "^3.4.0",
    "@types/react": "^18.3.0"
  }
}
```

---

## 動作確認用のサンプル動画

FFmpegがインストールされていない環境向けに、
フレーム画像が存在しない場合のフォールバック処理を必ず実装してください：
- フレーム抽出に失敗した場合はモックのフレームリストを使用
- Gemini APIキーが未設定の場合はモックのManualStructureを返す

---

## 起動方法

README.mdに以下を記載してください：

### バックエンド起動
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# .envにGEMINI_API_KEYを設定
uvicorn main:app --reload --port 8000
```

### フロントエンド起動
```bash
cd frontend
npm install
npm run dev
```

### アクセスURL
- フロントエンド: http://localhost:5173
- バックエンドAPI: http://localhost:8000
- APIドキュメント: http://localhost:8000/docs

---

## 実装時の注意事項

1. Gemini APIの呼び出しは非同期（async/await）で実装すること
2. 動画ファイルのアップロードは大容量対応のため streaming で処理すること
3. エラーハンドリングを必ず実装し、フロントエンドにエラーメッセージを返すこと
4. アップロードされた動画・生成マニュアルは uuid でユニークなIDを付与すること
5. Gemini File APIのファイル状態ポーリングには最大60秒のタイムアウトを設けること
```

---

## 📌 プロンプト使用時のポイント

AIデベロッパーに渡す際、以下の点を補足として伝えると精度が上がります：

| 補足内容 | 伝え方 |
|---------|--------|
| **優先順位** | 「まずPhase 1のみ完全に動く状態にしてください」と冒頭に追記 |
| **APIキー** | 「GEMINI_API_KEYは私が後で設定します。モックフォールバックを必ず入れてください」 |
| **UIデザイン** | こだわりがあれば「シンプルでビジネス向けの白基調デザイン」など追記 |
| **出力形式** | 「まずHTMLのみ対応、PDFは後回し」など絞ると実装がブレにくい |

---

## 🔑 実装後の確認チェックリスト

AIデベロッパーが実装したら、以下を確認してください：

```
□ backend/.env.example に GEMINI_API_KEY の記載がある
□ /api/health にアクセスして {"status":"ok"} が返る
□ モックモードで動画なしでもマニュアルが生成される
□ フロントエンドの3画面遷移（idle→processing→completed）が動作する
□ /api/docs でSwagger UIが表示される
□ HTMLダウンロードボタンが機能する
```

このプロンプトをそのままAIデベロッパーに貼り付ければ、Phase 1の動くプロトタイプが生成されるはずです。まず動かしてみて、品質を確認したらPhase 2の追加機能を別プロンプトで依頼する形が効率的です！