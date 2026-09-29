# 講座ノートブックの書き方

Jupyter / VS Code / Google Colab で書いた `.ipynb` を、そのまま講座として取り込めます。
取り込みは `python -m app.cli import-course <講座フォルダ>`(`backend/` で実行)で行います。
見本は [`content/statistics-basics/`](../content/statistics-basics/) です。

## 講座フォルダの構成

```
statistics-basics/
  course.json            講座情報と単元の並び順
  01_data_types.ipynb    単元(1ファイル = 1単元)
  02_frequency.ipynb
  data/
    scores.csv           演習で使うデータ(任意)。コードからは pd.read_csv("scores.csv") で読める
```

### course.json

```json
{
  "slug": "statistics-basics",
  "title": "統計の基礎",
  "summary": "講座の説明文",
  "level": "basic",
  "tags": ["統計", "pandas"],
  "outcomes": ["この講座で身につくこと", "..."],
  "libraries": ["pandas", "numpy", "matplotlib"],
  "prerequisites": [],
  "status": "published",
  "units": [
    { "file": "01_data_types.ipynb", "minutes": 20 },
    { "file": "02_frequency.ipynb", "minutes": 25 }
  ]
}
```

| 項目 | 内容 |
|---|---|
| `slug` | 講座の識別名(英数字とハイフン)。URL に使われる |
| `level` | `basic`(基礎)/ `intermediate`(応用)/ `advanced`(実践) |
| `prerequisites` | 前提講座の `slug` の一覧(先に取り込まれている必要がある) |
| `status` | `published`(公開)/ `draft`(下書き。管理者にだけ見える) |
| `units` | 単元の並び順と目安時間(分) |

## 単元ノートブックの書き方

### 1. 先頭のセル:タイトルと概要(Markdown)

```markdown
# 代表値:平均・中央値・最頻値
3つの代表値の違いと、外れ値が与える影響を学びます。
```

1行目の `# ` 見出しが単元タイトル、2行目以降が講座詳細に表示される概要になります。

### 2. 学習目標(任意、Markdown)

```markdown
## 学習目標
- 平均・中央値・最頻値の違いを説明できる
- pandas で代表値を計算できる
```

`## 学習目標` で始まるセルの箇条書きは、単元画面の「学習目標」の枠に表示されます。

### 3. 説明セルと例題セル

- Markdown セル → 説明セル(表・数式 `$...$` が使えます)。`## 見出し` は単元画面の目次に出ます
- 下記の記号で始まらないコードセル → 例題セル(受講者が自由に実行できます)

### 4. 演習(3〜4つのセルの組)

| セル | 1行目 | 内容 |
|---|---|---|
| Markdown | (何でもよい) | **問題文**。演習の直前の Markdown セルが問題文になります |
| コード | `# @starter` | 受講者に最初に表示する **初期コード**(空欄 `____` を含めてよい) |
| コード | `# @solution` | 作成者の **解答**。**実行して出力を保存しておく**(この出力が想定出力になります) |
| コード | `# @test` | (任意)テストコード。`@grading: test` の場合は必須 |

解答セルの先頭には、`# @項目: 値` の形で設定を書けます。

```python
# @solution
# @title: 外れ値を含むデータの代表値
# @hint: pandas の Series には .mean() と .median() メソッドがあります。
# @explanation: 平均は大きく動きましたが、中央値はほとんど変わりません。
import pandas as pd
scores = pd.Series([62, 75, 75, 81, 94, 58, 75, 88, 300])
print(f"平均: {scores.mean():.2f}")
print(f"中央値: {scores.median()}")
```

| 設定 | 内容 |
|---|---|
| `@title` | 演習のタイトル |
| `@hint` | 「ヒント」ボタンで表示する文 |
| `@explanation` | 正解したときに表示する解説 |
| `@grading` | `output`(出力一致、既定)または `test`(テストコード) |
| `@tolerance` | 数値比較の許容誤差(既定 `1e-6`) |

### 採点方式

- **出力一致(`output`)**:受講者のコードの出力(`print` の内容と、セル最後の式の値)を、解答セルに保存された出力と比べます。
  行末の空白や、数値の桁数による列揃えの違いは無視します。数値は許容誤差内なら一致とみなします。
- **テストコード(`test`)**:受講者のコードを実行したあと、同じ環境で `# @test` セルを実行し、すべての `assert` が通れば正解です。
  結果が一意に決まらない問題(乱数を使う、形式が自由など)に向いています。

### 注意

- **単元には演習が1問以上必要です**(単元は、演習をすべて正解したときに完了になります)。
- 初期コードに `____` があると、Jupyter で「すべて実行」したときにそこで止まります。解答セルは個別に実行してから保存してください。
- 受講者の環境はブラウザ内の Python(Pyodide 314 / Python 3.14 / pandas 3.0)です。
  想定出力は、同じバージョンの pandas で作ると表示形式のずれが起きません。
- matplotlib の図は画像として表示されます。日本語フォントは入っていないため、軸ラベルなどは英語にしてください。
