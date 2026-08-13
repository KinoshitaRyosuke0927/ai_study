# 上司レビュー再現型レビューアプリ：`014_re_ai_reviewer/` 新規構築 作業設計

## 1. 目的

`010_ai_reviewer/app/` は既存運用（exe配布・現行UI）を維持したまま残す。新しい多段パイプライン型レビュー（候補生成→過去レビュー参照→上司嗜好スコアリング→critic）は、`014_re_ai_reviewer/` 配下に**別アプリケーションとして新規構築**する。

方針は「**インフラは流用、パイプライン設計は新規**」。本ドキュメントでは、
1. `010_ai_reviewer/app/` のどのファイルをどう移植するか
2. `014_re_ai_reviewer/` の具体的なディレクトリ構成
3. 実装順序（作業タスク単位）
4. モデル改善のために別途取得すべきデータの種類・形式・目安件数

を作業レベルで定義する。

---

## 2. 移植対象と新規作成対象の切り分け

| 種別 | 対象 | 010から | 014での扱い |
|---|---|---|---|
| **流用（ほぼそのままコピー）** | `renderer.py`（PPTX→PDF→PNG/JPEG変換） | ✅ | `014_re_ai_reviewer/app/core/renderer.py` にコピー。中身は無改修 |
| **流用（インターフェースは維持、呼び出し方を汎用化）** | `azure_ai_service.py` のクライアント初期化・画像編集デプロイのラウンドロビン | ✅ | `014_re_ai_reviewer/app/core/azure_client.py` に移植。`call_review`/`call_qa` の代わりに、パイプライン各層から呼べる汎用関数 `call_structured(prompt_package, model)` に統合（呼び出し元が増えるため） |
| **流用（設定ファイルとして）** | `review_point.csv` / `pp_check_points.csv` | ✅ | `014_re_ai_reviewer/data/seed_review_points.csv` としてコピー。候補生成層の「網羅観点シード」として使う（後述） |
| **流用（Docker/デプロイ定義）** | `Dockerfile`, `infra/containerapp.json` | ✅ | パスとイメージ名のみ調整してコピー。LibreOffice/Poppler/日本語フォントのインストール部分は変更不要 |
| **新規設計** | `prompt.py`（プロンプト構築ロジック） | ❌ | 廃止し、`app/pipeline/` 配下に候補生成・ランキング・critic用の新規プロンプトモジュールを作成 |
| **新規設計** | `main.py`（APIルーティング・業務ロジック） | 部分参考 | アップロード系エンドポイント（`/api/upload`）はロジックをほぼ流用可能。レビュー系（`/api/review`, `/api/suggest`）はレスポンス構造が変わるため新規実装 |
| **新規設計** | フロントエンド（`static/`） | 部分参考 | アップロードUI・スライドプレビューは流用可、レビュー結果表示部分は構造化データ（issue/evidence/severity/manager_likeness）に合わせて作り直し |
| **完全新規** | 過去レビュー参照層・上司嗜好スコアリング層・critic層 | ❌ | `app/pipeline/review_memory.py`, `manager_ranker.py`, `critic.py` を新規作成 |

---

## 3. `014_re_ai_reviewer/` ディレクトリ構成案

```text
014_re_ai_reviewer/
  app/
    main.py                    # FastAPI エントリポイント（新規）
    core/
      azure_client.py          # 010の azure_ai_service.py を移植・汎用化
      renderer.py               # 010の renderer.py をそのままコピー
    schemas/
      models.py                 # Candidate / Finding / CriticResult 等の pydantic モデル（新規）
    pipeline/
      orchestrator.py           # 各層を順番に呼び出す（新規）
      candidate_generator.py    # 候補指摘の複数生成（新規）
      review_memory.py          # 過去指摘ログの検索・注入（新規）
      manager_ranker.py         # 上司らしさ・重要度スコアリング（新規）
      critic.py                 # 根拠検証・重複統合（新規）
    prompts/
      candidate_prompts.py
      ranker_prompts.py
      critic_prompts.py
    static/                     # 010の static/ を土台に、findings表示部分を作り直し
  data/
    seed_review_points.csv      # 010の review_point.csv / pp_check_points.csv を統合コピー
    review_log.jsonl            # 過去指摘・採否ログ（運用しながら蓄積、Phase2から使用）
  infra/
    containerapp.json           # 010から移植・調整
  Dockerfile                    # 010から移植（LibreOffice/Poppler部分は無改修）
  requirements.txt
  .env.example
```

- `010_ai_reviewer/` は変更しない（既存exe配布・現行UIを維持するため独立させる）。
- 依存パッケージ（`python-multipart`, `pdf2image`, `openai`, `fastapi` 等）は `010/requirements.txt` をベースに、新規層で使うライブラリ（後述）を追加する。

---

## 4. 実装タスク（作業順）

### Step 0: 雛形作成
- `014_re_ai_reviewer/` ディレクトリと上記構成の空ファイルを作成
- `010_ai_reviewer/Dockerfile`, `requirements.txt`, `infra/containerapp.json` をコピーし、パス・イメージ名を `014_re_ai_reviewer` に置換
- `010_ai_reviewer/app/renderer.py` をそのまま `app/core/renderer.py` にコピー（動作確認: PPTXアップロード→画像化のみのエンドポイントで疎通確認）

### Step 1: インフラ層移植
- `010_ai_reviewer/app/azure_ai_service.py` のクライアント初期化部分・画像編集ラウンドロビン部分を `app/core/azure_client.py` に移植
- `_call_chat` 相当を `call_structured(prompt_package: dict, model: str) -> dict` として汎用化（用途を限定しない命名に変更）
- `call_image_edit` はそのまま移植（修正提案機能を014でも使う場合）

### Step 2: スキーマ定義
- `app/schemas/models.py` に以下を定義
  - `Candidate`（issue, evidence_hint, category, severity_guess, slide_no）
  - `Finding`（Candidateに evidence, severity, manager_likeness, confidence, verdict を加えたもの＝critic通過後の最終形）
  - `ReviewMemoryEntry`（review_memory.py が読み書きするログの1件）

### Step 3: 候補生成層
- `app/pipeline/candidate_generator.py` + `app/prompts/candidate_prompts.py` を新規実装
- `data/seed_review_points.csv`（010のCSVを統合コピー）を読み込み、観点ヒントとしてプロンプトに埋め込む
- 出力スキーマを `{"candidates": [{"issue", "evidence_hint", "category", "severity_guess", "slide_no"}]}` に固定し、1スライドあたり5〜10件生成

### Step 4: 過去レビュー参照層
- `app/pipeline/review_memory.py` を新規実装
- 最初はベクトル検索を導入せず、`data/review_log.jsonl` に対する `perspective_type`/`category` 一致 + キーワード類似度（`difflib.SequenceMatcher` 等）で十分
- ログが溜まるまでは空実装（検索結果0件）でも他層は動作するようフォールバックを用意

### Step 5: 上司嗜好スコアリング層
- `app/pipeline/manager_ranker.py` を新規実装
- MVPは学習不要のLLM判定方式: 候補ペアを渡し「どちらが上司らしいか」をJSONで判定させ、勝敗数からスコアを算出
- 上司の口調・重視観点（「数字の根拠を重視する」等）はシステムプロンプトに明文化した固定テキストとして注入（reward model学習前の代替）

### Step 6: critic層
- `app/pipeline/critic.py` を新規実装
- 上位候補ごとにスライド画像＋指摘文を再度渡し、根拠有無・重複・幻覚をJSONで判定
- `verdict: keep/drop`, `critic_comment`, `dedup_group` を返す

### Step 7: オーケストレーション
- `app/pipeline/orchestrator.py` で Step3〜6 を順に呼び出し、`Finding[]` を組み立てる
- スライド単位の並列化は010の `ThreadPoolExecutor` パターンを踏襲

### Step 8: API実装
- `main.py` に `/api/upload`（010から移植）、`/api/review`（新規、`Finding[]` を返す）、`/api/suggest`（010の画像編集ロジックを移植し、入力を `Finding[]` ベースに変更）を実装

### Step 9: フロントエンド
- `static/` を010からコピーし、レビュー結果表示部分のみ `Finding[]`（issue/evidence/severity/manager_likeness）を表示できるよう改修

### Step 10: 動作確認
- サンプルPPTXでアップロード→候補生成→（review_memory空でも）ranker→critic→表示までの一連の疎通確認
- `review_log.jsonl` にログが正しく追記されるか確認（Phase2以降のデータ蓄積の土台）

---

## 5. モデル改善のためのデータ取得要件

パイプラインの各層で必要になるデータを、**いつ必要か**・**形式**・**目安件数**で整理する。候補生成層自体は `seed_review_points.csv` の流用で着手できるため、追加データが必須なのは Step4以降。

### 5.1 過去レビュー指摘ログ（review_memory層／Step4で使用開始）

| 項目 | 内容 |
|---|---|
| 用途 | 類似スライドに対して過去にどんな指摘をしたかを検索・プロンプト注入する |
| 必要なフィールド | `slide_summary`（スライド内容の要約）, `perspective_type` / `category`（論理・数字・表現など）, `raw_comment`（実際の指摘文）, `severity`（must/should/nit）, `meeting_type`（定例/役員向け等、任意）, `accepted_flag`（指摘が採用され修正されたか、任意） |
| 取得元 | 既存の「上司レビュー動画から抽出した指摘事項」（`review_point.csv`/`pp_check_points.csv` の元データ）を、スライド単位・指摘単位に再構造化 |
| 形式 | CSV または JSONL（1行1指摘） |
| 目安件数 | **検索が意味を持ち始める最低ライン: 50〜100件**。実用的な精度を狙うなら **300件以上**が目標。0件でも動作はするが検索結果が常に空になる |
| 優先度 | Phase2着手前に着手可。件数が少ないうちから運用しながら追加していく形でよい（一括収集は不要） |

### 5.2 上司嗜好のpairwise比較データ（manager_ranker層／Phase3でモデル学習する場合のみ）

| 項目 | 内容 |
|---|---|
| 用途 | LLM判定方式（Step5のMVP）から、学習済みrerankerへ置き換える際の学習データ |
| 必要なフィールド | `slide_context`（スライド要約）, `candidate_a` / `candidate_b`（2つの指摘案）, `preferred`（a/b）, `rationale`（なぜそちらが上司らしいか、任意だが精度に効く） |
| 取得元 | (a) 実際の上司コメント vs LLM生成の別候補、(b) 修正が採用された指摘 vs 見送られた指摘、(c) 同一スライドに対する複数候補を人手でA/B比較 |
| 形式 | JSONL |
| 目安件数 | **PoCとして最低1000件程度**が目安（5.1のログが300件溜まった段階で、そこから機械的にペア化すれば人手ラベリングは「A/B比較」だけで済み、件数を稼ぎやすい） |
| 優先度 | **今すぐ着手する必要はない**。Step5はLLM判定方式で運用開始し、5.1のログが十分溜まってから着手すればよい |

### 5.3 critic層の検証用データ（Phase3以降、任意）

| 項目 | 内容 |
|---|---|
| 用途 | critic判定（keep/drop）の精度評価・改善 |
| 必要なフィールド | 指摘文, 該当スライド, 実際に妥当だったか（人手ラベル）, 幻覚だった場合はその理由 |
| 目安件数 | 評価用として **100件程度**あれば hallucination reject rate 等の指標が測れる |
| 優先度 | 低。critic層が動き始めてから、抽出精度を見ながら随時収集で良い |

### 5.4 まとめ（今すぐ着手すべきもの）

- **最優先**: 5.1の過去レビュー指摘ログの構造化（既存の抽出済み指摘事項を、スライド要約・カテゴリ・指摘文・severityの形に整形するだけなので、新規収集ではなく**既存データの再整形**で足りる）
- **後回しでよい**: 5.2のpairwise比較データ、5.3のcritic評価データは、いずれもStep5・critic層をLLM判定で動かしながら並行して溜めていける性質のものなので、Step0〜9の実装着手をデータ収集完了まで待つ必要はない

---

## 6. まとめ

`014_re_ai_reviewer/` は、`renderer.py`・Azure OpenAIクライアント初期化・Docker/インフラ定義をそのまま流用しつつ、プロンプト構築とAPIロジックを「候補生成→過去レビュー参照→上司嗜好スコアリング→critic」の4層パイプラインとして新規に組み立てる。上司嗜好スコアリングとcriticの精度向上に使う学習データは実装と並行して蓄積すればよく、実装開始のブロッカーにはならない。最初に着手すべきデータ整備は、既存の抽出済み指摘事項をスライド単位で再構造化する5.1のみである。
