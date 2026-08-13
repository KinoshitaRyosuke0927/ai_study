# 上司レビュー再現型 PowerPoint レビューアプリ 設計メモ

## 1. 目的

本ドキュメントは、既存の「固定レビュー観点に基づく PowerPoint レビュー」アプリを拡張し、**特定の上司の確認観点・優先順位・指摘スタイルを再現する AI レビュアー**を実現するための設計案をまとめたものである。

想定する最終像は、単なるチェックリスト判定ではなく、スライド全体の文脈・意思決定観点・数値の妥当性・論理構成・説明責任まで含めて、**その上司なら何を気にし、どの順番で、どの粒度で指摘するか**を再現するレビュー体験である。

---

## 2. 背景整理

現状の方式では、上司レビュー動画から抽出した指摘事項をあらかじめ観点化し、その観点に沿って LLM にレビューさせている。この方式は、一定の再現性と実装容易性がある一方で、以下の限界がある。

- 指摘が**静的な観点一覧**に閉じる
- 上司が資料全体を見て行う**優先順位付け**を再現しにくい
- 「この会議ならここを突っ込む」「この数字は役員に刺さるか」などの**状況依存の判断**を扱いにくい
- 口調だけでなく、**何を重大とみなすか**という個人差が取り込めない

個人化 LLM 研究では、通常の RLHF は人間の嗜好を一様な分布として扱うため、個人差の再現が難しいとされている。一方で、個人化されたフィードバックから軽量なユーザモデルを学習し、応答を個別最適化する方向性が提案されている。これは「上司固有のレビュー観点」を学習する設計と親和性が高い。 [P-RLHF](https://arxiv.org/abs/2402.05133)

また、LLM によるレビュー研究では、単発生成よりも、**構造化された検討手順・外部根拠参照・自己検証**を取り入れた多段階方式のほうが品質が高いことが示されている。 [DeepReview](https://aclanthology.org/2025.acl-long.1420/) [CRITIC](https://proceedings.iclr.cc/paper_files/paper/2024/hash/fef126561bbf9d4467dbb8d27334b8fe-Abstract-Conference.html)

---

## 3. 設計方針

本アプリでは、次の思想を採用する。

1. **資料理解**と**上司らしさの判断**を分離する
2. 指摘を 1 発で生成せず、**候補生成 → 上司嗜好で再順位付け → critic 検証**の段階を踏む
3. 「一般に良いスライドか」と「その上司が気にするか」を分ける
4. 上司らしさは、ルールベースではなく、**pairwise preference / reward modeling** で学習する
5. 出力には必ず、**根拠スライド・根拠テキスト・重要度・修正提案**を付与する

この方針に基づき、推奨アーキテクチャは次の通りとする。

> **マルチモーダル LLM + 過去レビュー RAG + 上司嗜好の pairwise reward model + critic**

---

## 4. 全体アーキテクチャ

```text
[PowerPoint / PDF / 画像]
        |
        v
[前処理]
  - スライド画像化
  - テキスト抽出
  - ノート抽出
  - レイアウト/図表メタ情報抽出
        |
        v
[マルチモーダル資料理解]
  - 各スライド要約
  - 全体ストーリー把握
  - 数値/主張/根拠の抽出
        |
        +------------------------------+
        |                              |
        v                              v
[過去レビューRAG]               [汎用レビュー候補生成]
  - 類似スライド検索              - 論理/構成/数値/視認性など
  - 過去の上司コメント取得        - 指摘候補を複数生成
        |                              |
        +--------------+---------------+
                       |
                       v
         [上司嗜好 pairwise reward model]
         - 候補指摘を上司らしさで採点
         - 重要度 / 優先度を再順位付け
                       |
                       v
                 [critic / verifier]
                 - 根拠確認
                 - 幻覚検知
                 - 重複統合
                       |
                       v
                 [UI向け整形出力]
                 - 指摘一覧
                 - 重要度
                 - 該当スライド
                 - 根拠
                 - 修正案
```

---

## 5. 各コンポーネント設計

### 5.1 マルチモーダル LLM 層

#### 役割
- スライド画像とテキストを統合して理解する
- 各スライド単体だけでなく、**資料全体のストーリー**を把握する
- タイトル、本文、図表、強調、注記、発表者ノートなどを統合解釈する

#### 要件
- PPTX / PDF の両対応
- スライドごとの視覚特徴と言語特徴を同時に扱えること
- 長い資料でも文脈保持できること

#### 実装案（Python + Azure）
- PowerPoint から画像化: `python-pptx`, LibreOffice 変換, または Azure Functions / Container Apps 上の変換ワーカー
- OCR / レイアウト解析: **Azure AI Document Intelligence**
- 画像 + テキスト理解: **Azure OpenAI のマルチモーダルモデル**
- 中間表現保存: 各スライドの JSON 構造体

#### 推奨する中間表現
```json
{
  "slide_index": 3,
  "title": "市場規模と成長率",
  "bullets": ["TAM 1200億円", "CAGR 12%"],
  "speaker_note": "投資判断の前提として説明",
  "visual_elements": ["bar_chart", "callout", "annotation"],
  "claims": ["市場は高成長である"],
  "numbers": [{"value": "1200億円", "label": "TAM"}],
  "risks": ["出典がスライド上にない"]
}
```

---

### 5.2 過去レビュー RAG 層

#### 役割
- 過去に上司が実際に行った指摘を検索し、今回のレビュー時に参照する
- 「この上司はこういうスライドで何を気にしやすいか」を近傍事例から補強する

#### データソース
- レビュー会議動画の文字起こし
- 動画から抽出した指摘事項
- 指摘対象スライド
- 修正前後の資料
- レビュー時の会議コンテキスト（定例、役員報告、提案資料など）

#### 重要なインデックス単位
RAG はファイル全体ではなく、以下の粒度で持つべきである。

- `slide_chunk`: スライド単位
- `comment_chunk`: 指摘単位
- `review_session_chunk`: 会議単位
- `revision_pair_chunk`: 修正前後比較単位

#### 埋め込みに入れるメタデータ例
- 資料種別（提案、進捗、役員向け、障害報告など）
- スライドの役割（結論、根拠、市場、収支、ロードマップなど）
- レビュー対象レイヤ（論理、数字、粒度、表現、デザイン）
- 発話者（上司名）
- 指摘の強さ（must / should / nit）

#### Azure 実装案
- ベクトルストア: **Azure AI Search**
- 埋め込み生成: **Azure OpenAI Embeddings**
- 原文保存: **Azure Blob Storage** または Cosmos DB / PostgreSQL

---

### 5.3 上司嗜好の pairwise reward model

#### 役割
- 複数の指摘候補の中から、**その上司が実際に言いそうな指摘**を選ぶ
- 指摘の優先順位を学習する
- 口調ではなく、まず**選好構造**を再現する

#### なぜ pairwise か
学習データが少ない段階で、絶対スコア回帰よりも、

- A と B のどちらが上司らしいか
- A と B のどちらがより重大か

という**比較データ**のほうが作りやすく、ブレも少ないためである。個人化 LLM 研究の観点とも整合的である。 [P-RLHF](https://arxiv.org/abs/2402.05133)

#### 学習データ形式例
```json
{
  "slide_context": "市場規模を示すスライド。出典なし。TAM/SAM/SOM が未分離。",
  "candidate_a": "市場規模の数字に出典がなく、信頼性が担保されていない。",
  "candidate_b": "グラフの色使いがやや見づらい。",
  "preferred": "a",
  "reason": "この上司は意思決定に影響する数字の根拠を視認性より重視する"
}
```

#### モデル案
- 初期段階: Cross-encoder / BERT 系 reranker
- 拡張段階: 小型 Transformer による reward model
- 将来段階: LLM judge を蒸留したスコアラ

#### 学習タスク
- Pairwise ranking loss
- 重要度分類（blocker / high / medium / low）
- レビュー観点推定（論理 / 数字 / 結論 / ストーリー / 表現 / デザイン）

#### Python 実装候補
- `transformers`
- `sentence-transformers`
- `PyTorch Lightning`
- `MLflow` for experiment tracking

---

### 5.4 critic / verifier 層

#### 役割
- 生成された指摘が、実際に資料根拠に基づいているか検証する
- 幻覚・重複・根拠薄い指摘を落とす
- 「上司らしいが間違っている」指摘を防ぐ

LLM 批評能力に関する研究では、LLM は批評自体が難しく、自己批評だけでは安定しないことが示されている。外部検証や明示的な批評ステップを加える設計が有効である。 [Critique Ability of LLMs](https://arxiv.org/abs/2310.04815) [CRITIC](https://proceedings.iclr.cc/paper_files/paper/2024/hash/fef126561bbf9d4467dbb8d27334b8fe-Abstract-Conference.html)

#### critic のチェック項目
- 指摘内容が該当スライドに明示的に根拠を持つか
- 指摘が資料外の事実を勝手に仮定していないか
- 同趣旨の指摘が複数出ていないか
- 修正提案が指摘内容と整合しているか
- 資料全体の文脈と矛盾していないか

#### 出力形式例
```json
{
  "issue": "市場規模の出典不足",
  "evidence": ["slide_3:title", "slide_3:chart_caption"],
  "confidence": 0.91,
  "verdict": "keep",
  "critic_comment": "指摘は妥当。TAM 数値に出典表記がない。"
}
```

---

## 6. レビュー生成フロー

### Step 1. 資料取り込み
- PPTX / PDF アップロード
- スライド画像化
- テキスト・ノート・図表情報抽出

### Step 2. スライド理解
- 各スライド要約
- 主要主張、数値、根拠、結論の抽出
- 全体の論理展開を要約

### Step 3. 類似レビュー検索
- 類似する過去スライド・過去指摘を RAG で取得
- 上司が過去に似た資料へ何を指摘したかを補助コンテキストとして付加

### Step 4. 汎用レビュー候補生成
- LLM に複数候補を出させる
- 観点は固定せず、論理・数字・意思決定・表現・視認性を広めに見る

### Step 5. 上司嗜好による再順位付け
- 候補指摘を pairwise reward model でスコア化
- 「上司らしさ」「重要度」「会議影響度」で並べ替え

### Step 6. critic 検証
- 根拠確認
- 重複削除
- 不確実な指摘にフラグ付け

### Step 7. UI 出力
- 指摘一覧
- 該当スライド
- 重要度
- 上司らしさスコア
- 根拠
- 修正案

---

## 7. 推奨データモデル

### 7.1 エンティティ

#### `Presentation`
- id
- title
- author
- created_at
- presentation_type
- audience_type
- source_file_url

#### `Slide`
- id
- presentation_id
- slide_no
- image_url
- extracted_text
- speaker_note
- layout_features
- semantic_summary

#### `ReviewSession`
- id
- presentation_id
- reviewer_name
- meeting_type
- created_at
- transcript_url

#### `ReviewComment`
- id
- review_session_id
- slide_id
- raw_comment
- normalized_comment
- category
- severity
- actionability
- accepted_flag

#### `RevisionPair`
- id
- before_presentation_id
- after_presentation_id
- linked_comment_ids
- fix_applied_flag

#### `PreferencePair`
- id
- slide_context
- candidate_a
- candidate_b
- preferred
- reviewer_name
- rationale

---

## 8. Python / Azure 構成案

### 8.1 アプリケーション構成

#### フロントエンド
- React / Next.js など任意
- PowerPoint アップロード
- レビュー結果一覧表示
- 該当スライドプレビュー

#### バックエンド API
- **Python + FastAPI**
- 非同期処理: `Celery` または `Azure Functions` / `Azure Container Apps Jobs`

#### 推奨サービス分担
- API サーバ: **Azure App Service** または **Azure Container Apps**
- ファイル保存: **Azure Blob Storage**
- メタデータ DB: **Azure Database for PostgreSQL**
- ベクトル検索: **Azure AI Search**
- OCR / ドキュメント解析: **Azure AI Document Intelligence**
- LLM / Embeddings: **Azure OpenAI Service**
- 監視: **Azure Application Insights**
- シークレット管理: **Azure Key Vault**
- 学習ジョブ: **Azure Machine Learning**

### 8.2 ディレクトリ例

```text
backend/
  app/
    api/
    core/
    models/
    services/
      ingestion/
      slide_parser/
      rag/
      reviewer/
      reward_model/
      critic/
    schemas/
    repositories/
  scripts/
  tests/
  notebooks/
ml/
  datasets/
  training/
  evaluation/
infra/
  bicep/
  terraform/
```

---

## 9. 推論時のプロンプト/推論戦略

### 9.1 生成は 1 発で終わらせない
研究的にも、レビュー品質は構造化された検討を通すことで改善しやすい。DeepReview は、構造化分析・外部情報参照・根拠ベースの議論を取り入れることで、レビュー性能を向上させている。 [DeepReview](https://aclanthology.org/2025.acl-long.1420/)

そのため、推論は以下の 3 段階を推奨する。

1. **Observer**: スライドの主張・数字・構造を観察
2. **Reviewer**: 汎用的な指摘候補を複数生成
3. **Manager Persona Selector**: 上司嗜好で再順位付け
4. **Critic**: 根拠検証と整形

### 9.2 生成候補数
- 各スライド 5〜10 件程度の候補を一旦生成
- 最終表示は 1〜3 件に絞る

### 9.3 出力スキーマ固定
```json
{
  "slide_no": 5,
  "issue": "結論に対する根拠が不足している",
  "why_it_matters": "役員が投資判断できないため",
  "evidence": ["売上予測の前提条件が未記載"],
  "suggestion": "前提条件と感度分析を追記する",
  "severity": "high",
  "manager_likeness": 0.87,
  "confidence": 0.82
}
```

---

## 10. 学習データ作成戦略

### 10.1 既存資産の活用
現時点で既にある「上司レビュー動画から抽出した指摘事項」は非常に重要である。これを単なる観点一覧ではなく、次のように再構造化する。

- どのスライドに対する指摘か
- どの会議文脈か
- 指摘の背景理由は何か
- 実際に修正されたか
- 同じ場面で別の指摘候補がありえたか

### 10.2 pairwise データの作り方
ペア比較データは次の方法で作れる。

- 実指摘 vs 汎用 LLM が生成した別候補
- 修正につながった指摘 vs 採用されなかった指摘
- 同一スライドに対する複数候補を人手で比較

### 10.3 弱教師あり拡張
データ不足を補うために、次の半自動手法を使う。

- 過去コメントをカテゴリ正規化
- 類似スライドに対し LLM で候補指摘を増殖
- 人手は「採否」または「A/B 比較」だけ行う

---

## 11. 評価指標

### 11.1 オフライン評価
#### 上司再現性
- Top-k に実指摘が入る率
- Pairwise accuracy
- NDCG / MRR

#### レビュー品質
- 根拠一致率
- 幻覚率
- 重複率
- actionable rate（修正可能率）

#### 業務有用性
- 実際に採用された指摘率
- 修正後資料の改善度
- 人間レビュー時間削減率

### 11.2 オンライン評価
- 上司本人による「自分らしさ」評価
- 部下による「納得感」評価
- 実会議で追加指摘がどれだけ減るか

大規模ランダム化研究では、LLM フィードバックによりレビュー更新率や情報量が増加したことが示されており、オンライン評価で「人のレビュー行動がどう変わるか」を見るのは有効である。 [Can LLM feedback enhance review quality?](https://arxiv.org/abs/2504.09737)

---

## 12. MVP の切り方

### Phase 1: ルール拡張版
- マルチモーダル LLM で資料理解
- RAG で過去類似指摘を提示
- 上司プロファイルをプロンプト注入
- reward model なし

### Phase 2: pairwise reranker 導入
- 候補指摘を複数生成
- pairwise reward model で再順位付け
- 上司らしさスコアを出す

### Phase 3: critic 強化
- 根拠スパン抽出
- 幻覚フィルタ
- 重複統合

### Phase 4: 継続学習
- ユーザの採否・修正結果をログ化
- reward model を定期再学習

実装順としては、**いきなり end-to-end の大規模微調整を狙わず、reranker から始める**のが妥当である。

---

## 13. リスクと対策

### リスク 1. データ量不足
**対策**
- pairwise 比較に落とす
- 弱教師ありで候補を拡張する
- 修正前後資料を教師信号として使う

### リスク 2. 上司の気分依存・状況依存
**対策**
- 会議タイプや資料目的をメタデータ化
- レビュアープロファイルを固定ベクトルではなく文脈依存で持つ

### リスク 3. 幻覚指摘
**対策**
- critic で根拠スパン必須化
- 根拠が弱いものは UI 上で低信頼表示

### リスク 4. 「上司っぽいが不適切」な再現
**対策**
- 組織標準の guardrail を別途用意
- ハラスメント的表現や過度に曖昧な指摘をフィルタ

---

## 14. 実装技術スタック例

### Python ライブラリ
- API: `fastapi`, `uvicorn`, `pydantic`
- 非同期ジョブ: `celery`, `redis` あるいは Azure Queue ベース
- DB: `sqlalchemy`, `psycopg`
- ML: `torch`, `transformers`, `sentence-transformers`, `lightning`
- 実験管理: `mlflow`
- 前処理: `python-pptx`, `pymupdf`, `Pillow`
- テスト: `pytest`

### Azure SDK
- `azure-ai-documentintelligence`
- `azure-search-documents`
- `azure-storage-blob`
- `openai` または Azure OpenAI 対応 SDK
- `azure-identity`
- `azure-keyvault-secrets`

---

## 15. 最終提案

本アプリケーションに最も適した設計は、**マルチモーダル LLM を土台に、過去レビュー RAG で事例記憶を補い、上司嗜好を pairwise reward model で学習し、最後に critic で根拠検証する多段階アーキテクチャ**である。

これは、

- 固定観点レビューより柔軟で
- 単発生成より再現性が高く
- フル微調整より現実的に始めやすく
- Azure / Python で段階導入しやすい

という利点がある。

特に最初の実装では、以下の順を推奨する。

1. **資料理解 + RAG** を先に安定化
2. **候補指摘の複数生成** を導入
3. **pairwise reranker** で上司らしさを学習
4. **critic** で根拠確認
5. 収集ログを用いて継続改善

研究面でも、個人化フィードバック、批評能力、レビュー自動化、スライド品質評価の流れを組み合わせる構成になっており、先行研究との接続も良い。 [P-RLHF](https://arxiv.org/abs/2402.05133) [Critique Ability of LLMs](https://arxiv.org/abs/2310.04815) [DeepReview](https://aclanthology.org/2025.acl-long.1420/) [Can LLM feedback enhance review quality?](https://arxiv.org/abs/2504.09737) [AI-driven review systems](https://arxiv.org/abs/2408.10365) [Slide IQ framework](https://journals.sagepub.com/doi/abs/10.1177/0165551516661917)

---

## 16. 参考文献 / 参考URL

- Personalized Language Modeling from Personalized Human Feedback  
  https://arxiv.org/abs/2402.05133
- Critique Ability of Large Language Models  
  https://arxiv.org/abs/2310.04815
- CRITIC: Large Language Models Can Self-Correct with Tool-Interactive Critiquing  
  https://proceedings.iclr.cc/paper_files/paper/2024/hash/fef126561bbf9d4467dbb8d27334b8fe-Abstract-Conference.html
- DeepReview: Improving LLM-based Paper Review with Human-like Deep Thinking  
  https://aclanthology.org/2025.acl-long.1420/
- Can LLM Feedback Enhance Review Quality? A Randomized Study of 20k Reviews at ICLR 2025  
  https://arxiv.org/abs/2504.09737
- AI-driven review systems: evaluating LLMs in scalable and bias-aware academic reviews  
  https://arxiv.org/abs/2408.10365
- Developing information quality assessment framework of presentation slides  
  https://journals.sagepub.com/doi/abs/10.1177/0165551516661917
