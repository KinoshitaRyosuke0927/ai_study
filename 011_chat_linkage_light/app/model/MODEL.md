# リマインド必要度判定モデルについて(軽量モデル版)

`011_chat_linkage_light` アプリが、Mattermost・GROUPSESSIONの投稿の中から「リマインドすべき投稿」を
自動的に絞り込むために使っている、TF-IDF + ロジスティック回帰のモデルについて、概要・学習方法・
アプリケーションへの組み込み方をまとめる。

元のバージョン(`011_chat_linkage`)では、日本語BERTをファインチューニングしたモデルを使っていた。
このモデルに置き換えた理由(精度・動作面の比較)は、
[`011_chat_linkage/app/model/LIGHT_MODEL_EVALUATION.md`](../../../011_chat_linkage/app/model/LIGHT_MODEL_EVALUATION.md) を参照。

## このモデルは何をするものか

**入力**: 投稿・記事のテキスト1件
**出力**: その投稿が「リマインドが必要そうな内容(締め切り・提出物・注意喚起など)」である
確率(0.0〜1.0)

生成AI(Azure OpenAI、`app/azure_ai_service.py`)とは役割が異なる。

| | 役割 |
|---|---|
| このモデル(ロジスティック回帰) | 大量の投稿の中から「拾うべき投稿」を**選別**する |
| Azure OpenAI(GPT) | 選別された投稿から、実際の**リマインド文・アジェンダ文を生成**する |

## モデルの構造

scikit-learnの `Pipeline` で、次の3段階の処理を1つのモデルとしてまとめている。

```
投稿テキスト
  ↓
① 前処理(app/model/preprocess.py の preprocess_text)
   - 個人宛てメンション(@yamada など)→ @USER に置き換え(@channel/@here/@all はそのまま残す)
   - URL → "URL" に置き換え
   - 英字を小文字に統一
  ↓
② TF-IDFベクトル化(TfidfVectorizer)
   - 連続する1〜3文字(文字n-gram)を1単位として数える(例: 「お願い」→「お」「願」「い」「お願」「願い」「お願い」)
   - 3件以上の投稿に出現する文字列のみを使う
   - 投稿ごとに、各文字列の重要度(TF-IDF値)を並べたベクトルにする
  ↓
③ ロジスティック回帰(LogisticRegression)
   - 各文字列に学習で決めた重みを掛けて足し合わせ、シグモイド関数で0〜1の確率に変換する
  ↓
「リマインド必要(クラス1)」の確率 ← predict.py が返す値
```

- **前処理の目的**: 特定の人物名やURLの文字列に頼った判定にならないようにする。
  個人宛てメンションは「個別のやり取り(リマインド不要になりやすい)」という手がかりとして、`@USER` の形で残している
- **文字n-gramを使う理由**: 形態素解析(MeCab等)が不要で依存パッケージが増えない。
  表記ゆれや未知語にも比較的強い。比較検証では、単語単位の特徴量と同等以上の精度だった
- **保存形式**: `joblib` 形式の1ファイル(`app/model/reminder_classifier.joblib`、約350KB)。
  中身は、学習済みの `Pipeline` と学習条件の情報(scikit-learnのバージョン、学習日時、件数、パラメータ)をまとめた辞書

## 学習データの作り方(`app/model/collect_train_data.py`)

BERT版と同じ。

1. `mattermost_service.get_channel_posts_in_range()` で、指定チャンネル・期間の実際の
   Mattermost投稿を取得する(取得対象は `collect_train_data.py` 冒頭の
   `START_DATE`/`END_DATE`/`CHANNEL_DISPLAY_NAMES` で設定)。
2. `pickup_flag,user,text` 形式のCSV(`train_data/collected_posts.csv`)として出力する。
   この時点では `pickup_flag` 列は**空欄**。
3. 人間がExcel等でこのCSVを開き、各投稿に対して手動で `0`(不要)/`1`(必要)を入力してラベル付けする。

## 学習方法(`app/model/train_model.py`)

1. `load_labeled_posts()` が `train_data.csv`・`collected_posts.csv` を読み込み、
   `pickup_flag` が `0`/`1` の行だけを学習対象にする。
2. **正則化の強さ(C)の選択**: 候補(1 / 3 / 10 / 30)それぞれについて層化5分割交差検証を行い、
   PR-AUCが最も高いCを選ぶ(`GridSearchCV`)。Cが小さいほど重みが大きくなりすぎないよう抑える(過学習しにくい)。
3. **精度の確認**: 選んだCで交差検証の予測を作り、PR-AUCと、しきい値0.5でのprecision・recall・F1を表示する。
   Cの選択にも同じ分割を使っているため、表示される値は未知のデータでの精度よりわずかに高めに出る。
4. **全データで学習**: 選んだCで、全データを使って学習し直す。
5. **保存**: `app/model/reminder_classifier.joblib` に保存する(既存のモデルは上書き)。

### クラス不均衡への対応

実運用では「リマインド不要」な投稿が大多数で、「必要」な投稿は少数派になりやすい。
`LogisticRegression(class_weight="balanced")` により、各クラスの重みを件数に反比例させている
(少数派の「必要」の誤りを、件数比の分だけ重く扱う)。BERT版の `WeightedTrainer` と同じ考え方。

### 学習結果の例(2026年10月時点のデータ、1,369件)

| 項目 | 値 |
|---|---|
| 選ばれた正則化の強さ | C=3 |
| 交差検証 PR-AUC | 0.897 |
| しきい値0.5での precision / recall / F1 | 0.759 / 0.888 / 0.818 |
| 学習時間 | 1分程度(交差検証を含む) |
| モデルファイルのサイズ | 約350KB |

## しきい値について

BERT版は確率を0か1に近い極端な値で出す傾向があり、しきい値0.9でも多くの投稿を拾えていた。
このモデルは確率を控えめに出すため、0.9のままでは「必要」な投稿の多くを見逃してしまう(再現率30〜40%程度)。
そのため、しきい値の既定値を **0.5** に変更している(交差検証でF1が最良になるしきい値が約0.5のため)。

## アプリケーションへの組み込み方

### 推論の入り口(`app/model/predict.py`)

- `predict_reminder_score(text)`: 投稿1件のスコアを返す
- `predict_reminder_scores(texts)`: 投稿複数件をまとめてスコアリングする
  (実運用ではこちらが主に使われる)
- モデルは初回呼び出し時に1回だけ読み込み、モジュール内のグローバル変数(`_model`)にキャッシュする
  (`_load_model()`)。2回目以降の呼び出しは読み込み処理をスキップする。
- 関数名・引数・戻り値はBERT版と同じなので、呼び出し元のコードは変更していない。

### 呼び出し元(`app/agenda_service.py` の `filter_posts_by_reminder_score()`)

`predict_reminder_scores()` を直接使う唯一の関数。投稿一覧としきい値(`threshold`)を受け取り、
スコアがしきい値以上の投稿だけを残す。この関数が、以下の複数箇所から共通で呼ばれている。

| 呼び出し元 | 用途 | しきい値の出どころ |
|---|---|---|
| `main.py` `GET /api/channels/{id}/posts` | 画面UI: Mattermostタブでの手動絞り込み | リクエストパラメータ(既定0.5) |
| `main.py` `GET /api/webpage/announcements` | 画面UI: GROUPSESSIONタブでの手動絞り込み | リクエストパラメータ(既定0.5) |
| `agenda_service.collect_mattermost_agenda_items()` | `/nightrain agenda`(自動アジェンダ作成)の対象投稿抽出 | `settings.ini` `[slash_watch] reminder_threshold`(既定0.5) |
| `reminder_service.build_reminder_list_message()` | `/nightrain remind`(自動リマインド一覧)の対象投稿抽出 | 同上 |

しきい値が高いほど「確実にリマインドが必要」と判定された投稿のみが残り、低いほど
拾い漏れは減るが誤検知(不要な投稿の混入)が増える。

### モデルファイルの配置場所(実行環境ごとの違い)

`predict.py` のモデル読み込み先(`MODEL_PATH`)は、実行環境に応じて2パターンに分岐する。

1. **PyInstaller配布のexe実行時**(`sys.frozen`): exeと同階層の `_internal/model/reminder_classifier.joblib`
   (`--add-data` でexeに同梱)
2. **それ以外(ローカル実行・Azure Functions)**: `app/model/reminder_classifier.joblib`

BERT版では、Azure Functionsのデプロイパッケージに大容量のモデルを含められなかった。
そのため、Blob Storageからモデルをダウンロードしてキャッシュする仕組み(`MODEL_CACHE_DIR`)が必要だった。
このモデルは約350KBと小さいので、デプロイパッケージにそのまま同梱しており、この仕組みは削除した。

### 依存パッケージとバージョンの注意

- 推論に必要なのは `scikit-learn`(と、その依存の `numpy`・`scipy`・`joblib`)のみ。`torch`・`transformers`・`fugashi` は不要
- joblib形式のモデルは、**学習時と同じバージョンのscikit-learnでないと読み込めない**場合がある。
  そのため `requirements.txt`・`functions/requirements.txt` で `scikit-learn==1.8.0` に固定している。
  バージョンを上げる場合は、モデルを再学習すること(学習時のバージョンは、保存した辞書の `sklearn_version` で確認できる)
- 学習済みモデルには、前処理関数 `app.model.preprocess.preprocess_text` への参照が含まれる。
  この関数の名前・モジュールの場所を変えた場合も、モデルの再学習が必要

## モデルを再学習・更新する手順

1. `python -m app.model.collect_train_data` を実行し、対象期間・チャンネルの投稿を
   `train_data/collected_posts.csv` に出力する(実行前にファイル冒頭の設定値を編集)。
2. 出力されたCSVの `pickup_flag` 列を人手で 0/1 にラベル付けする。
3. `python -m app.model.train_model` を実行し、`app/model/reminder_classifier.joblib` に
   新しいモデルを保存する(既存モデルは上書きされる)。表示される精度を確認する。
4. ローカル実行であれば、アプリを再起動すると新しいモデルが使われる。
5. exe配布の場合は再ビルド、Azure Functionsの場合は `functions/build_package.ps1` で
   パッケージを作り直して再デプロイする(モデルはパッケージに同梱されるため、別途のアップロードは不要)。

## 関連ファイル一覧

| ファイル | 役割 |
|---|---|
| `app/model/collect_train_data.py` | Mattermost投稿からラベル付け用CSVを作成 |
| `app/model/train_data/*.csv` | ラベル付け済み学習データ |
| `app/model/preprocess.py` | 学習・推論で共通のテキスト前処理 |
| `app/model/train_model.py` | TF-IDF + ロジスティック回帰の学習スクリプト |
| `app/model/reminder_classifier.joblib` | 学習済みモデル本体(約350KB) |
| `app/model/predict.py` | 推論の入り口。モデルの読み込み・スコアリングを提供 |
| `app/agenda_service.py` | `filter_posts_by_reminder_score()` で推論結果をしきい値フィルタに使用 |
| `app/reminder_service.py` | 自動リマインド一覧作成時に同フィルタを利用 |
| `settings.ini` `[slash_watch] reminder_threshold` | 自動応答時のしきい値設定(既定0.5) |
