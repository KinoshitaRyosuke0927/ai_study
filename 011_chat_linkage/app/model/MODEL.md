# リマインド必要度判定モデルについて

`011_chat_linkage` アプリが、Mattermost・GROUPSESSIONの投稿の中から「リマインドすべき投稿」を
自動的に絞り込むために使っている、独自にファインチューニングしたAIモデルの概要・学習方法・
アプリケーションへの組み込み方をまとめる。

## このモデルは何をするものか

**入力**: 投稿・記事のテキスト1件
**出力**: その投稿が「リマインドが必要そうな内容(締め切り・提出物・注意喚起など)」である
確率(0.0〜1.0)

生成AI(Azure OpenAI、`app/azure_ai_service.py`)とは役割が異なる。

| | 役割 |
|---|---|
| このモデル(BERT分類器) | 大量の投稿の中から「拾うべき投稿」を**選別**する |
| Azure OpenAI(GPT) | 選別された投稿から、実際の**リマインド文・アジェンダ文を生成**する |

## 使用しているモデル

- **ベースモデル**: [`cl-tohoku/bert-base-japanese-v3`](https://huggingface.co/cl-tohoku/bert-base-japanese-v3)
  (東北大学が公開している事前学習済み日本語BERT)
- **タスク**: 2クラス分類(0=リマインド不要, 1=リマインド必要)
- **ファインチューニング方式**: フルファインチューニング(BERT本体・分類ヘッドの両方を更新)
- **保存形式**: Hugging Face `transformers` 標準形式一式(`config.json`, `model.safetensors`,
  `tokenizer_config.json`, `training_args.bin`, `vocab.txt`)。サイズは約425MB。

## モデルの構造

事前学習済みBERTは「文脈を理解してベクトルに変換する」能力のみを持ち、分類機能は持たない。
`transformers`の`AutoModelForSequenceClassification`が、これに分類用の層を自動的に追加する。

```
入力トークン列
  ↓
埋め込み層(事前学習済み)
  ↓
Transformer Encoder層 × 12層(事前学習済み)
  ↓
[CLS]トークンの最終隠れ状態(768次元、文全体の要約表現)
  ↓
Dropout
  ↓
Linear(768 → 2)  ← ここだけ新規追加・ランダム初期化
  ↓
2つのロジット [クラス0のスコア, クラス1のスコア]
  ↓
softmax
  ↓
[クラス0の確率, クラス1の確率] ← predict.pyが1側を返す
```

学習(`train_model.py`の`trainer.train()`)では、BERT本体・新規追加した分類層のどちらも
凍結せず、両方の重みを誤差逆伝播でまとめて更新する(いわゆるフルファインチューニング)。
事前学習で得た汎用的な日本語理解の上に、少量のラベル付きデータだけで
「リマインドが必要そうな文章」の判定能力を上乗せできるのが転移学習の利点。

## 学習データの作り方(`app/model/collect_train_data.py`)

1. `mattermost_service.get_channel_posts_in_range()` で、指定チャンネル・期間の実際の
   Mattermost投稿を取得する(取得対象は`collect_train_data.py`冒頭の
   `START_DATE`/`END_DATE`/`CHANNEL_DISPLAY_NAMES`で設定)。
2. `pickup_flag,user,text` 形式のCSV(`train_data/collected_posts.csv`)として出力する。
   この時点では `pickup_flag` 列は**空欄**。
3. 人間がExcel等でこのCSVを開き、各投稿に対して手動で `0`(不要)/`1`(必要)を入力してラベル付けする。

つまり教師データは実際の社内投稿を人手でラベル付けした実データであり、合成データや
既存の公開データセットは使っていない。

## 学習方法(`app/model/train_model.py`)

### データ準備

- `load_labeled_posts()` が `train_data.csv`・`collected_posts.csv` を読み込み、
  `pickup_flag` が `0`/`1` の行だけを学習対象にする。
- `train_test_split(..., stratify=labels)` で、ラベル比率を保ったまま学習用85%・検証用15%に分割
  (`VAL_RATIO = 0.15`)。
- `AutoTokenizer.from_pretrained(MODEL_NAME)` で、投稿本文を最大256トークン
  (`MAX_LENGTH = 256`)にトークナイズ。

### クラス不均衡への対応

実運用では「リマインド不要」な投稿が大多数で「必要」な投稿は少数派になりやすい。そのため
`WeightedTrainer`(`CrossEntropyLoss`にクラスごとの重みを渡すカスタムTrainer)を使い、
少数派クラス(1)の重みを `多数派件数 ÷ 少数派件数` の比で大きくすることで、
モデルが少数派クラスを軽視しないようにしている。

### 学習条件

| 項目 | 値 |
|---|---|
| エポック数 | 5 |
| バッチサイズ | 8(学習・検証とも) |
| 学習率 | 2e-5 |
| 評価・保存タイミング | 各エポック終了時 |
| 採用モデル | 検証データのF1スコアが最良だった時点(`load_best_model_at_end`) |
| 乱数シード | 42(`RANDOM_SEED`、分割・学習の再現性のため固定) |

学習率が`2e-5`と非常に小さいのは、事前学習済みの重みを大きく壊さないよう慎重に
微調整するための典型的な設定。

### 評価

各エポック終了後、検証データに対して precision・recall・F1(`compute_metrics()`、
`sklearn.metrics.precision_recall_fscore_support`)を算出し、最終的に
`trainer.evaluate()` の結果を標準出力に表示する。

### 出力

学習済みモデル・トークナイザーを `app/model/reminder_classifier/` に保存する
(`trainer.save_model()` / `tokenizer.save_pretrained()`)。既存のモデルは上書きされる。

## アプリケーションへの組み込み方

### 推論の入り口(`app/model/predict.py`)

- `predict_reminder_score(text)`: 投稿1件のスコアを返す
- `predict_reminder_scores(texts)`: 投稿複数件をバッチでまとめてスコアリングする
  (実運用ではこちらが主に使われる)
- モデルは初回呼び出し時に1回だけ読み込み、モジュール内のグローバル変数
  (`_tokenizer` / `_model`)にキャッシュする(`_load_model()`)。2回目以降の呼び出しは
  読み込み処理をスキップする。

### 呼び出し元(`app/agenda_service.py` の `filter_posts_by_reminder_score()`)

`predict_reminder_scores()` を直接使う唯一の関数。投稿一覧としきい値(`threshold`)を受け取り、
スコアがしきい値以上の投稿だけを残す。この関数が、以下の複数箇所から共通で呼ばれている。

| 呼び出し元 | 用途 | しきい値の出どころ |
|---|---|---|
| `main.py` `GET /api/channels/{id}/posts` | 画面UI: Mattermostタブでの手動絞り込み | リクエストパラメータ(既定0.9) |
| `main.py` `GET /api/webpage/announcements` | 画面UI: GROUPSESSIONタブでの手動絞り込み | リクエストパラメータ(既定0.9) |
| `agenda_service.collect_mattermost_agenda_items()` | `/nightrain agenda`(自動アジェンダ作成)の対象投稿抽出 | `settings.ini` `[slash_watch] reminder_threshold`(既定0.9) |
| `reminder_service.build_reminder_list_message()` | `/nightrain remind`(自動リマインド一覧)の対象投稿抽出 | 同上 |

しきい値が高いほど「確実にリマインドが必要」と判定された投稿のみが残り、低いほど
拾い漏れは減るが誤検知(不要な投稿の混入)が増える。既定値0.9はかなり厳しめの設定。

### モデルファイルの配置場所(実行環境ごとの違い)

`predict.py` のモデル読み込み先(`MODEL_DIR`)は、実行環境に応じて3パターンに分岐する
(`app/model/predict.py` 冒頭)。

1. **PyInstaller配布のexe実行時**(`sys.frozen`): exeと同階層の
   `_internal/model/reminder_classifier/`(`--add-data`でexeにモデル一式を同梱)
2. **Azure Functions実行時**(`MODEL_CACHE_DIR`環境変数が設定されている場合): 環境変数が指す
   永続領域(`/home/data/model_cache/reminder_classifier`)。Azure Functionsのデプロイ
   パッケージには425MBのモデルファイルを含めていないため、初回起動時のみ
   `_ensure_model_cached()` がAzure Blob Storageの`models`コンテナからダウンロードして
   キャッシュする(詳細は [`functions/DEPLOYMENT.md`](../../functions/DEPLOYMENT.md) 参照)。
3. **通常のローカル実行(開発時)**: `app/model/reminder_classifier/`(リポジトリ内のファイルを
   そのまま参照)

いずれの場合も、読み込んだ後のモデルの動作(推論方法)自体は同一。

## モデルを再学習・更新する手順

1. `python -m app.model.collect_train_data` を実行し、対象期間・チャンネルの投稿を
   `train_data/collected_posts.csv` に出力する(実行前にファイル冒頭の設定値を編集)。
2. 出力されたCSVの `pickup_flag` 列を人手で 0/1 にラベル付けする。
3. `python -m app.model.train_model` を実行し、`app/model/reminder_classifier/` に
   新しいモデルを保存する(既存モデルは上書きされる)。
4. ローカル実行・exe配布であれば、そのまま新しいモデルが使われる。
5. Azure Functions環境で使う場合は、更新したモデルファイル一式をBlob Storageの
   `models/reminder_classifier/` に再アップロードし、Function App側のキャッシュ
   (`/home/data/model_cache/reminder_classifier`)を削除するか、新しいキャッシュ先パスに
   切り替える必要がある(そのままでは古いキャッシュが使われ続けるため)。

## 関連ファイル一覧

| ファイル | 役割 |
|---|---|
| `app/model/collect_train_data.py` | Mattermost投稿からラベル付け用CSVを作成 |
| `app/model/train_data/*.csv` | ラベル付け済み学習データ(git管理対象外) |
| `app/model/train_model.py` | BERTのファインチューニング(学習)スクリプト |
| `app/model/reminder_classifier/` | 学習済みモデル本体(git管理対象外、約425MB) |
| `app/model/predict.py` | 推論の入り口。モデルの読み込み・スコアリングを提供 |
| `app/agenda_service.py` | `filter_posts_by_reminder_score()` で推論結果をしきい値フィルタに使用 |
| `app/reminder_service.py` | 自動リマインド一覧作成時に同フィルタを利用 |
| `settings.ini` `[slash_watch] reminder_threshold` | 自動応答時のしきい値設定 |
