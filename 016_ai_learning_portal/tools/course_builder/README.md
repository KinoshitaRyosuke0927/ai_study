# course_builder(手本講座を作るツール)

手本講座(`content/<講座>/`)の .ipynb・図・データファイルを、原稿から作るツールです。
受講者のブラウザと同じ **Pyodide 314**(Python 3.14 / pandas 3.0)で実行するため、想定出力や図の見た目が受講画面とずれません。

## 準備

```bash
cd 016_ai_learning_portal/tools/course_builder
npm install        # pyodide(314.0.7)を入れる。パッケージ(pandas など)は初回実行時に CDN から取得する
```

以下のコマンドは `016_ai_learning_portal/` で実行します。

## フォルダ構成

```
tools/course_builder/
  build-course.mjs      原稿(units/*.txt)→ 講座フォルダの .ipynb
  make-figures.mjs      図のスクリプト → 講座フォルダの images/(共通スタイルを適用)
  run-py.mjs            Python スクリプトを実行(数値の確認、データファイルの作成)
  dump-outputs.mjs      .ipynb のコードセルの出力を一覧表示(確認用)
  validate_course.py    アプリの取り込み処理で講座フォルダを検証(DB には書き込まない)
  sources/<講座>/
    units/*.txt         単元・小テストの原稿
    figures/uNN.py      単元ごとの図のスクリプト
    checks/uNN.py       単元ごとの数値の確認スクリプト(問題文・解説の数値を計算して確かめる)
    make_data.py        図の材料のデータ(data/*.csv)を作るスクリプト
    data/*.csv          図・数値の確認に使うデータ(講座には含めない。受講者には図表として見せる)
```

## 原稿の書き方

`#%% md` / `#%% code` の行でセルを区切ったテキストです。セルの中身は [docs/notebook-format.md](../../docs/notebook-format.md) の書き方そのままです
(演習は `<!-- @question ... -->` の Markdown セル、またはコードの `# @starter` / `# @solution` セル)。

```
#%% md
# 単元タイトル
概要

#%% md
## 学習目標
- ...
```

## よく使うコマンド

```bash
# 図の材料のデータを作る(原稿フォルダの data/ に保存)
node tools/course_builder/run-py.mjs tools/course_builder/sources/stats2-descriptive/make_data.py --save-csv

# 単元の図を作る(共通スタイル backend/app/ai/figure_style.py を適用し、講座フォルダの images/ に保存)
node tools/course_builder/make-figures.mjs tools/course_builder/sources/stats2-descriptive/figures/u02.py content/stats2-descriptive

# 問題文・解説に使う数値を確かめる(原稿フォルダの data/ を読める)
node tools/course_builder/run-py.mjs tools/course_builder/sources/stats2-descriptive/checks/u02.py

# 原稿から .ipynb を作る(最後の引数でファイル名の先頭を指定すると、その単元だけ作る)
node tools/course_builder/build-course.mjs tools/course_builder/sources/stats2-descriptive content/stats2-descriptive 02

# アプリの取り込み処理で検証する
backend/.venv/Scripts/python.exe tools/course_builder/validate_course.py content/stats2-descriptive

# ローカル DB に取り込む(同じ識別名の講座は置き換え)
cd backend && .venv/Scripts/python.exe -m app.cli import-course ../content/stats2-descriptive --author admin --replace
```

## 作るときの方針(手本講座で決めたこと)

- 統計検定対策の講座で身につけたいのは **概念の理解と手計算の力**。解説は図・表・文章で説明し、Python のコードは載せない。
- 演習は試験形式(選択式・数値入力・表形式の選択)。問題文・解説の数値は、必ず `checks/` のスクリプトで計算して確かめる。
- 解説の例と演習で同じデータ・同じ区切りを使わない(解説から演習の答えが読めてしまうため)。
- 統計ソフトの出力を載せるときは、表示する要約統計量(n・平均・標準偏差など)から t・自由度・p 値などを計算し、
  すべての数値を整合させる(架空の出力でも、受講者が手計算で確かめたときに食い違わないように)。
- パーセント点(1.96、t 分布表の値など)は問題文で与える。値は `checks/` で scipy から求めて確かめる。
- 表形式の選択(matrix)の表のマスには `|` を書かない(取り込み時に列の区切りとして扱われる)。
- 学習目標に数式を書いてもよい(受講画面で Markdown として表示される)。
- 図は共通スタイル([docs/figure-style.md](../../docs/figure-style.md))で描く。図の中の文字は英語。
- コードを書かない講座では、データファイルは講座フォルダ(`content/<講座>/data/`)に置かない
  (置くと講座のデータファイルとして取り込まれる)。図の材料は原稿フォルダの `data/` に置く。

### コーディング中心の講座(実践型。手本: `content/titanic-eda`)

- 受講者が使うデータは講座のデータファイルとして `content/<講座>/data/` に置く(build-course は原稿フォルダの `data/` と、講座フォルダの `data/` の両方を作業ディレクトリに置いて実行する)。
- 受講者は初学者を想定し、例題・初期コード・解答のコードには、各処理の意味がわかるコメントを付ける。初期コードの空欄 `____` には、答えを書かずに「何を入れるか」をコメントで示す。
- 説明は「例題セル(実行できるコード)→ 結果の読み取り」の順に書く。本文の数値は build-course が保存した出力(`dump-outputs.mjs` で確認)と必ず一致させる。
- 演習はコード(空欄 `____` を埋める・数行を書く)を中心に、結果の解釈は選択式にする。演習は解説の例と別の列・別の切り口を使う。
- 演習の解答は単独で動くように書く(`import` と `read_csv` から)。受講者が例題を実行していなくても同じ出力になるようにする。
  `pd.set_option` などの表示設定に出力が左右されないよう、演習の出力は列の少ない表・Series にする。
- グラフは受講画面と同じ共通スタイル(matplotlibrc)で描かれる。色を指定しなければ PRIMARY → ACCENT の順になる。図の中の文字は英語。
- 公開データを使うときは、利用条件(出典の表記など)を講座の概要と単元1に書く。タイタニックのデータは `sources/titanic-common/`
  (元データ titanic3.csv と、train.csv / test.csv を作る `make_data.py`。test の正解 `out/test_answers.csv` は講座に含めない)。
