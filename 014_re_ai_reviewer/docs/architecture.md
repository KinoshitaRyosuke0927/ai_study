# 014_re_ai_reviewer 設計書

## 1. 目的

本ドキュメントは、`014_re_ai_reviewer` のアーキテクチャと設計判断をまとめたものである。設計の出発点は [010_ai_reviewer/docs/model_brushup.md](../../010_ai_reviewer/docs/model_brushup.md)（上司レビュー再現型アーキテクチャの構想）と [010_ai_reviewer/docs/architecture_from_current_app.md](../../010_ai_reviewer/docs/architecture_from_current_app.md)（010の実装を踏まえた作業設計）であり、本アプリはそこで合意した「**インフラは010から流用、パイプライン設計は新規**」という方針に基づいて実装した。

## 2. 背景

010_ai_reviewer は、レビュー観点をCSVで固定管理し、観点ごとにLLMへQ&A形式でレビューさせて要約するという**1段構成**だった。この方式には以下の限界があった。

- 指摘が静的な観点一覧に閉じる
- 上司が資料全体を見て行う優先順位付けを再現しにくい
- 過去の実際のレビュー指摘を動的に参照する仕組みがない
- 生成された指摘の根拠検証ステップがない

014_re_ai_reviewer では、これらを解消するため「候補生成 → 過去レビュー参照 → 上司嗜好スコアリング → critic検証」の4層パイプラインを新規に構築した。010_ai_reviewer は既存運用（exe配布・現行UI）のため変更せず、本アプリを別ディレクトリの独立アプリケーションとして構築している。

## 3. 全体アーキテクチャ

```text
[PPTX アップロード]
        |
        v
[スライド画像化]            core/renderer.py（010から無改修で移植）
  LibreOffice --convert-to pdf → pdf2image でPNG/JPEG化
        |
        v
[候補生成層]                 pipeline/candidate_generator.py
  - seed_review_points.csv（010の観点CSVを統合）を観点ヒントとして使用
  - review_memory層のヒントがあれば注入
  - 資料全体を1回のLLM呼び出しでスキャンし、指摘候補を複数生成
        |
        v
[過去レビュー参照層]         pipeline/review_memory.py
  - review_log.jsonl を検索（キーワード類似度、ベクトル検索は未導入）
  - データ整備中のため現状は0件 → ヒントなしで後続処理にフォールバック
        |
        v
[上司嗜好スコアリング層]     pipeline/manager_ranker.py
  - 候補全体を1回のLLM呼び出しでまとめてスコアリング
  - manager_likeness（0.0〜1.0）と最終severityを付与
        |
        v
[critic検証層]               pipeline/critic.py
  - スライド単位でグループ化し、該当スライド画像に照らして根拠検証
  - 根拠が薄い・重複する指摘は verdict="drop" として除外
        |
        v
[Finding一覧]                 /api/review のレスポンス
  issue / evidence / category / severity / manager_likeness / confidence / suggestion
        |
        v
[画像編集提案]                pipeline/suggestion.py（010の/api/suggestを移植）
  - Finding を slide_number でグループ化し、画像編集AI向け指示に変換
  - gpt-image-2 / gpt-image-2-2 で修正後スライド画像を生成、SSEで順次返却
```

## 4. 各層の設計

### 4.1 スライド画像化（`core/renderer.py`）

010_ai_reviewer の `renderer.py` を無改修でコピーしている。LibreOffice（`soffice --headless --convert-to pdf`）でPPTXをPDF化し、`pdf2image`（Poppler）でスライドごとのPNG/JPEGに変換する。パイプラインの後段は画像化ロジックに依存しないため、レビュー方式を刷新してもこの層は変更不要だった。

### 4.2 候補生成層（`pipeline/candidate_generator.py` / `prompts/candidate_prompts.py`）

`data/seed_review_points.csv`（010の `review_point.csv` / `pp_check_points.csv` を統合したもの）を「網羅的に見るべき観点のヒント」としてプロンプトに埋め込み、資料全体の画像とあわせて1回のLLM呼び出しで指摘候補を複数生成する。010のQ&A形式（観点ごとに1問1答）とは異なり、1スライドあたり5〜10件程度の候補を幅広く出すことを優先し、後続の層で選別する設計にしている。

### 4.3 過去レビュー参照層（`pipeline/review_memory.py`）

`data/review_log.jsonl` に対して、`SequenceMatcher` によるキーワード類似度検索を行う。ベクトル検索（Azure AI Search + Embeddings）は導入していない。過去レビュー指摘ログのデータ整備が別途進行中のため、**現状は `review_log.jsonl` が空のままでもパイプライン全体が動作するフォールバック実装**にしている。データが揃い次第、`ReviewMemoryEntry` スキーマ（`slide_summary` / `category` / `comment` / `severity` / `accepted`）に沿って1行1件追記していけば、以降は自動的に候補生成・critic層のプロンプトに反映される。

### 4.4 上司嗜好スコアリング層（`pipeline/manager_ranker.py` / `prompts/ranker_prompts.py`）

候補指摘リストと過去レビューヒントをまとめて1回のLLM呼び出しに渡し、各候補に `manager_likeness`（上司らしさスコア）と最終的な `severity` を付与する。

当初の設計案（010の作業設計書 Step5）では「候補ペアをLLMに見せてどちらが上司らしいか判定する」pairwise方式をMVPとして想定していたが、候補数 n に対し O(n²) 回のLLM呼び出しが必要になり実用速度を欠くため、**候補リスト全体を1回のLLM呼び出しでスコアリングする方式に簡略化**した。関数のインターフェース（`Candidate` のリストを受け取りスコア付きリストを返す）は変えていないため、Phase3で実データを使ったpairwise reward modelに置き換える際もこの層の呼び出し元（`orchestrator.py`）は変更不要である。

### 4.5 critic検証層（`pipeline/critic.py` / `prompts/critic_prompts.py`）

スコアリング済みの候補を `slide_number` でグループ化し、該当スライド画像1枚につき1回のLLM呼び出しで、そのスライドに紐づく候補すべての根拠検証を行う。同じスライド画像を候補ごとに何度も送る無駄を避けるための設計である。根拠が確認できない、または資料外の事実を仮定していると判定された候補は `verdict="drop"` となり、最終的な `Finding` 一覧には含まれない。

### 4.6 画像編集提案（`pipeline/suggestion.py` / `prompts/suggestion_prompts.py`）

010_ai_reviewer の `/api/suggest`（画像編集AIによるスライド修正提案、SSEストリーミング）を移植した機能。010との差分は次の1点のみである。

- 010は「どの指摘がどのスライドに該当するか」をLLMに判断させてから編集指示を生成していたが、014の `Finding` は生成時点で既に `slide_number` が確定しているため、**その判断ステップを省略**し、「指摘事項を画像編集AI向けの具体的な指示文に変換する」ことだけをLLMに依頼している。UI上の挙動（該当スライドのみ編集、指摘がないスライドはスキップ、SSEで完了順に返却、PDFエクスポート）は010と同一。

## 5. データモデル

### 5.1 Candidate（候補生成層の出力）
`slide_number` / `issue` / `evidence_hint` / `category` / `severity_guess`

### 5.2 Finding（critic検証を通過した最終指摘、UI表示・画像編集提案の入力）
`slide_number` / `issue` / `evidence` / `category` / `severity` / `manager_likeness` / `confidence` / `verdict` / `critic_comment` / `suggestion`

### 5.3 ReviewMemoryEntry（過去レビュー指摘ログ、`review_log.jsonl` の1行）
`slide_summary` / `category` / `comment` / `severity` / `accepted`

## 6. フロントエンド

010_ai_reviewer と同じ2カラムレイアウト・タブ構成（伝えたいこと／指摘事項／修正方針）・スライド一覧・画像ライトボックス・修正対象指摘事項選択モーダルを踏襲している。変更したのは「指摘事項」タブ（旧「総評」タブ）のみで、観点カテゴリ別の集約文章表示から、選択中スライドに紐づく `Finding` のカード表示（severity・上司らしさスコア・根拠・critic検証コメント・修正提案）に置き換えている。

010にあった「レビュー観点設定」モーダル（CSVのapply_flagをUIから編集する機能）と「想定質問」タブは、新パイプラインに対応する機能が未整備のため本アプリでは未移植である。

## 7. 今後の拡張フェーズ

| フェーズ | 内容 |
|---|---|
| 現状 | `review_log.jsonl` は空。review_memory層はヒント0件で動作 |
| Phase 2 | 過去レビュー指摘ログの整備（スライド要約付きで指摘事項を再構造化）が完了次第、`review_log.jsonl` に投入し、検索ヒントとして活用開始 |
| Phase 3 | ログが十分溜まった段階で、pairwise比較データを作成し、`manager_ranker.py` をLLM判定方式から学習済みreranker（`sentence-transformers`等）に置き換え |
| Phase 4 | `review_memory.py` の検索方式を、キーワード類似度からAzure AI Search + Embeddingsのベクトル検索に置き換え |

必要なデータの種類・目安件数は [010_ai_reviewer/docs/architecture_from_current_app.md](../../010_ai_reviewer/docs/architecture_from_current_app.md) の「5. モデル改善のためのデータ取得要件」を参照。
