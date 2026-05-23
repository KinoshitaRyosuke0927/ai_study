# AIにコードレビューを任せたら思ったより賢かった話——Code Reading Supporter を拡張してみた

## はじめに

私が所属している **AIS（AIシステム開発事業部）** では、47期から月に1回の **帰社日** を設けています。

46期まではメンバーがそれぞれ客先で業務をすることが多く、お互いの顔を見る機会もなかなかありませんでした。そこで47期から、**部署内のコミュニケーション活性化・メンバー間の相互理解・技術向上** を目的として、月1回全員がAICに集まり、一緒に簡単なアプリケーション開発をする取り組みを始めました。

その47期の取り組みの中で生まれたのが **CRS（Code Reading Supporter）** です。AIがコードを読んで仕様書を自動生成・レビュー・修正してくれるアプリケーションで、「コードを読む手間をAIに任せる」ことをテーマに作りました。

なお、同等の機能を持つツールとしては **GitHub Copilot** をはじめ市場にすでに数多く存在しています。CRSはそれらに代わる実用ツールを目指したものではなく、**AISメンバーの学習・経験を積む取り組みとして** 作ったものです。実用性や市場価値よりも、「自分たちで作って動かす経験」を重視しています。

---

今回の記事では、その **CRSをさらに拡張** した際の内容を紹介します。使い込んでいくうちに「ここが惜しい」という点が2つ見えてきました。

1. **ファイルを1つずつ独立して翻訳している**　——プロジェクト全体の文脈が取れない
2. **翻訳処理が非同期**　——全ファイルの処理が終わるまで結果が確認できない

今回はこの2点を改善しながら、「AIが複数ファイルをまとめて読んでプロジェクトを理解する」「同期的に翻訳・レビュー・修正まで一気通貫でやる」ことに挑戦してみます。おまけで **単体テスト自動生成** と **ソース可視化（Mermaid図）** も試してみたので最後まで読んでいただけると嬉しいです。

---

## 1. プロジェクト全体を一度に読む

### そもそもなぜ「1ファイルずつ」では足りないのか

実際の開発現場でコードを1ファイルだけ渡して「このコードを理解してください」と言われても、文脈が足りなくてよく分からないですよね。「このクラスがどこから呼ばれているのか」「このフォルダはどういう役割なのか」——そういった情報は、プロジェクト全体を見て初めてわかります。

今回ターゲットにしたのは **新たに案件に参画したエンジニア** です。既存のシステムに対して機能追加タスクが割り当てられたばかりの人に「このプロジェクト、何をするシステムで、コードはどう整理されていて、どんなルールで書けばいいか」をAIに整理させることが目標です。

### 出力として欲しいもの

整理すると、欲しいアウトプットは以下の3点です。

- **プロジェクト概要**　——何をするシステムで、どんな機能があるか
- **フォルダ構成と役割**　——どのフォルダが何を担っているか
- **コーディング規約**　——暗黙のルールをコードから自動抽出する

### プロンプトの設計

入力はプロジェクトのすべてのファイルを以下の形式でまとめたJSONです。フルパスがあることで「このファイルはどのフォルダにある」という位置関係も把握できます。

```json
[
    {
        "full_path": "crs_backend/services/login_service.py",
        "contents": "from database import db_access_service\nfrom models import LoginResponse..."
    },
    {
        "full_path": "crs_backend/services/task_detail_service.py",
        "contents": "import json\nimport os\nfrom pathlib import Path\nimport pandas as pd..."
    }
]
```

プロンプトは、以前の「入力例と出力例を1セット丸ごと用意するOne-Shot形式」から **「出力のMarkdown構造を直接指定する形式」** に切り替えました。One-Shotだと例の作成が大変・出力形式の変更が難しい・送信トークンが増えるといった問題があったためです。

実際に使用したプロンプトはこちらです。

<div style="background: #f0fdf4; border: 1px solid #86efac; border-radius: 8px; padding: 24px; margin: 16px 0;">

**📝 プロンプト（プロジェクト要約）**

```
上記のJSONはプロジェクトを構成するファイルの情報からなるJSONです。
JSONの各要素ごとに、full_pathにはそのファイルのパスが、contentsにはそのファイルの中身のコードが設定されています。
このJSONで表されるプロジェクト全体の内容を要約して、標準Markdown形式で出力してください。
要約内容は、新たにこのプロジェクトの開発作業に参加したエンジニアが、既存のプロジェクト内容や開発ルールを把握できることを意識して記載してください。
要約結果として出力するmarkdownファイルは、以下に設定した項目と内容に合わせて作成してください。返答には要約結果のみを含め、他の文章は不要です。

### プロジェクト概要
ここには、プロジェクトファイル全体を見渡して、このプロジェクトで作成しているシステムがどのようなシステムで、どのような機能を実現しようとしているか記載してください。
個々の詳細なプログラムの処理内容を記載するのではなく、システムとしてどのような処理を行う機能が実装されているのかを意識して要約してください。
メインとなる機能が複数存在する場合は、以下のようにすべて記載してください。

- **機能1** : 機能1の説明
- **機能2** : 機能2の説明
...

### プロジェクト構成
ここには、プロジェクト全体のフォルダ構成を図示してください。

### フォルダごとの役割
ここには、プロジェクト内の各フォルダごとで管理されている機能や役割について説明してください。

| フォルダ名 | 役割・機能概要 |
|-------------|----------------|
| **folder1/** | folder1の説明 |
| **folder2/** | folder2の説明 |
| ... | ... |

### コーディング規約
ここには、プロジェクト全体で共通のコーディングルールがあると判断できる場合は、そのルールを記載してください。
変数名や関数名の設定ルールや、処理の書き方に特徴がある場合は記載してください。
特に関数の説明やコード内のコメントなど書き方が統一されている場合は、その書き方に合わせてください。
```

</div>

Markdownのテンプレートをプロンプト末尾に置いておくだけなので、出力構造の変更も楽です。

### 実際の出力結果

このプロンプトに対してAIが生成した結果がこちらです。

<div style="background: #f9fafb; border: 1px solid #cbd5e0; border-radius: 8px; padding: 24px; margin: 16px 0;">

**AIの生成結果**

### プロジェクト概要
このプロジェクトは、**Azure OpenAI**・**Azure Files**・**Azure SQL Database**を連携したクラウドアプリケーションであり、Pythonコードやプロジェクト全体をAIが自動解析・要約・レビュー・テストコード生成できるシステムを実現している。主にFastAPIを用いたAPIサーバ構成を採用し、バックエンドからAzureリソースへ安全にアクセスするためのサービス層を設けている。

メイン機能は次の通り。

- **コード解析機能** : アップロードされたPythonコードをAIモデル（Azure OpenAI）に送信し、Markdown形式の詳細な処理説明を生成する。
- **コード更新機能** : コードの仕様書（Markdown）に基づいて既存コードの修正を自動提案・更新する。
- **レビュー機能** : コードと仕様書を比較して内容の妥当性をAIでレビューし、指摘箇所をMarkdown形式で出力する。
- **テストコード生成機能** : 実装仕様から自動的に単体テストコードを生成する。
- **プロジェクト要約／構成図生成機能** : 全ファイル情報(JSON)をAIに送り、総合的な要約MarkdownとMermaid構成図（classDiagram）を生成する。
- **ファイル共有機能** : Azure Filesへの並列アップロード・ダウンロード・削除をサポートし、DBと連動したファイル管理を行う。
- **タスク管理機能** : SQL Database上でタスクの作成・更新・削除・状態遷移を管理する。
- **ユーザ認証機能** : bcryptを利用したパスワード認証により、ユーザの安全なログイン機構を提供。
- **自動並列バックグラウンド変換** : FastAPIのBackgroundTasksを活用して複数ファイルの自動変換・要約を非同期で実行。

---

### プロジェクト構成

```
project_root/
├── main.py
├── models.py
├── azure_operation/
│   ├── azure_ai_operation_service.py
│   ├── azure_files_operation_service.py
│   ├── azure_constant.py
├── common/
│   ├── constant.py
│   ├── common_validate.py
├── database/
│   ├── db_access_info.py
│   ├── db_models.py
│   ├── db_access_service.py
├── services/
│   ├── login_service.py
│   ├── task_list_service.py
│   ├── task_detail_service.py
│   ├── chat_translate_service.py
├── tests/
│   ├── test_unit_*.py （ユニットテスト群）
│   ├── test_db_access_service.py （DB接続検証）
│   ├── test_azure_access_service.py （Azure連携検証）
```

---

### フォルダごとの役割

| フォルダ名 | 役割・機能概要 |
|-------------|----------------|
| **azure_operation/** | Azure OpenAIおよびAzure Filesとの通信を行う基盤モジュール群。AIモデル呼び出しとファイルストレージ操作機能を提供。 |
| **common/** | 共通定義および入力値検証処理を担当。定数管理、バリデーションロジックを集約。 |
| **database/** | Azure SQL Databaseへのアクセス層。SQLAlchemy ORMを使用してテーブルモデル定義、CRUD操作を実装。 |
| **services/** | ビジネスロジック層。ログイン処理、タスクリスト取得、タスク詳細操作、AIチャット変換などアプリケーション機能全般を担当。 |
| **tests/** | 単体テスト・統合テスト用ディレクトリ。モックを用いたサービスロジック確認や実際のAzure／SQL動作検証を実施。 |
| **main.py** | FastAPIのエントリーポイント。エンドポイント定義、CORS設定、リクエストルーティングを行う。 |
| **models.py** | Pydanticモデル群。APIリクエスト／レスポンスの型定義を集中管理。 |

---

### コーディング規約
- **言語・フレームワーク** : Python（FastAPI、SQLAlchemy、Azure SDK）
- **命名規則** :
  - 定数：すべて大文字（例：`AZURE_OPENAI_ENDPOINT`）
  - クラス：CapWords方式（例：`MUser`, `AzureOpenAI`）
  - 関数・変数：スネークケース（例：`select_task_by_user_id`）
- **ドキュメンテーション** :
  - すべての関数は引数・返値を明記したdocstringを持つ。
  - コメントヘッダには「処理目的」「Args」「Returns」を明示。
- **エラーハンドリング** :
  - DB・Azure呼び出し部分でtry-except構文を用い、ログ出力とロールバック処理を統一的に実施。
  - サービス層ではAPIレスポンスとして整形済みのメッセージ辞書を返却。
- **データモデル設計** :
  - SQLAlchemyモデルとPydanticモデルを分離し、永続化層とAPI層の責務を明確化。
- **並列／非同期処理** :
  - ファイル処理をThreadPoolExecutorまたはFastAPIのBackgroundTasksで並列実行。
- **テスト方針** :
  - unittest.mockおよびpytestを使用し、機能単位・サービス層単位・Azure接続単位でテストを実施。

</div>

### この出力、どうだった？

欲しかった4セクション（概要・構成・フォルダ役割・規約）が揃っているのはしっかり合格点です。ただ、見ていくと改善できそうな点も。

- 「ファイル共有機能」「ユーザ認証機能」はシステム内部の処理であって、ユーザに提供する機能ではない
- 「ドキュメンテーション」「エラーハンドリング」の説明に、命名規則のような具体例があるともっとわかりやすい
- 「データモデル設計」「並列／非同期処理」の記述が抽象的すぎて実際に役立てにくい

「足掛かりとしては十分、でももう一歩」という感じ。

また、今後に向けた発展課題として以下も残っています。

- コードが更新されると要約が古くなる（鮮度を保つ仕組みが必要）
- 別ファイルに規約がある場合、それも取り込んで合算したい
- 規約以外の暗黙知（設計思想・命名の哲学など）も抽出できると面白い

---

## 2. 翻訳・レビュー・修正を一気通貫でやる

### これまでの流れと変えたいこと

これまでのCRSは翻訳処理を非同期で行っていたため、複数ファイルをまとめて送ると全部終わるまで結果が見えませんでした。

今回は **1ファイルを対象に、翻訳→レビュー→修正まで同期で一気に通す** ことを目指します。

```
コード登録 → 翻訳結果取得 → レビュー実施 → レビュー指摘反映
```

### レビュープロンプトの設計

翻訳プロンプトは既存のものを流用し、新たに **レビュープロンプト** を設計しました。先ほど生成したプロジェクト要約を「開発ルール」として一緒に渡して、「このプロジェクトのコーディング規約に沿っているか」もチェックさせます。

<div style="background: #f0fdf4; border: 1px solid #86efac; border-radius: 8px; padding: 24px; margin: 16px 0;">

**📝 プロンプト（コードレビュー）**

```
上記のMarkdownの仕様書ファイルに記載されている仕様に基づいて以下のコードをレビューして、レビュー結果をまとめて標準Markdown形式で出力してください。
コードレビューの際は以下のルールを必ず守ってください。
    1. プロジェクト全体の開発ルールが明示されている場合は、レビュー対象のコードが開発ルールに沿っているかをチェックして、適していない箇所があればその個所と修正方法を明記してください。
    2. レビュー対象のコード内にプログラム上の実装の誤りが存在する場合は、誤っている個所と修正方法を記載してください。
    3. markdownの仕様書ファイルに記載されている処理がコードに実装されていない場合は、仕様書に記載されているどの処理の実装が漏れているかと実装方法を明記してください。
    4. markdownの仕様書ファイルに記載されていない不要な処理やプログラム上不要な処理がコードに存在する場合は、その処理が記載されている個所と、その処理が不必要である理由を明記してください。
    5. コードとmarkdownを比較してプログラムとして問題がない箇所については指摘の必要はありません。
    6. 返答にはレビュー結果のMarkdown部分のみを含め、他の文章は不要です。
    7. レビュー結果として出力するmarkdownファイルは、以下に設定した項目と内容に合わせて作成してください。

以下の項目ごとにレビュー結果をまとめて記載してください。
各項目ごとに、レビューの結果問題のある個所が無いと判断された場合は、「該当する指摘事項なし。」と記載してください。

## コードレビュー結果

### 開発ルールとの相違点
ここには、プロジェクト全体の開発ルールに関する指摘事項について記載してください。

| 指摘箇所 | 指摘理由 |
|-------------|----------------|
| **taskName = "タスク"** | 変数名はスネークケースにしてください。 |
| **def update_user_info(user_id):** | 関数の引数は型を明示してください。また関数の処理内容についてコメントを記載してください。 |
| ... | ... |

### プログラム上の誤り
ここには、プログラム上の実装の誤りに関する指摘事項について記載してください。

| 指摘箇所 | 指摘理由 |
|-------------|----------------|
| **count = int(div_s)** | 変数div_sはfloat型のため、そのまま整数にcastするとエラーになる可能性があります。 |
| **update_user_info()** | 関数update_user_infoは引数にuser_idが必要です。 |
| ... | ... |

### 実装漏れ
ここには、仕様書には記載されているがコードには実装されていない処理に関する指摘事項について記載してください。

| 指摘箇所 | 実装方法 |
|-------------|----------------|
| **ユーザ名称更新処理** | ユーザ名称更新処理が実装されていません。例えば次のような処理の追加が必要です。```python def update_user_info(user_id: int) -> pd.DataFrame: ... ``` |
| ... | ... |

### 不要な処理
ここには、プログラム上の不要な処理に関する指摘事項について記載してください。

| 指摘箇所 | 指摘理由 |
|-------------|----------------|
| **user_name = "sample user"** | 16行目で定義されている変数user_nameは、他の処理で参照されていないため不要です。 |
| **def update_user_info(user_id: int) -> pd.DataFrame:** | 30行目で実装されている関数update_user_infoは、他の処理で参照されていないため不要です。 |
| ... | ... |

### その他の指摘や懸念事項
ここには、上記のいずれにも該当しない指摘事項や懸念事項について記載してください。

| 指摘箇所 | 指摘理由 |
|-------------|----------------|
| **# 該当するユーザ情報を削除する** | 23行目で定義されているコメントと、実装されている内容に相違があります。 |
| **derivery** | 34行目で使用されている英単語deriveryの綴りに誤りがあります。配送や配達を意味する英単語の正しい綴りはdeliveryです。 |
| ... | ... |
```

</div>

プロジェクト要約をシステムに渡す際には、以下のひと言を付け加えています。

<div style="background: #f0fdf4; border: 1px solid #86efac; border-radius: 8px; padding: 24px; margin: 16px 0;">

**📝 プロンプト（プロジェクトルールの注入）**

```
このプロジェクトでは、上記のMarkdownに記載されている開発ルールを順守して開発を行っています。
既存のフォルダ構成やファイル名はこちらを参考にしてください。
今後コードの修正や追加、レビューを行う場合は、可能な限りこの開発ルールに準拠するようにしてください。
```

</div>

### 実際に動かしてみる

入力はこのコードです。`login_service.py` の `login` 関数——ログイン処理そのままの、よくある書きかけ実装です。

```python
import bcrypt

from database import db_access_service
from models import LoginResponse


def login(mail_address, password):
    """
    ログイン処理
    """
    df = db_access_service.select_user(mail_address)
    if df.empty:
        message_dict = db_access_service.select_message("msg-E-0001")
        return LoginResponse(status=200, messages=[message_dict])
    else:
        if bcrypt.checkpw(password.encode("utf-8"), df["password"].values[0]):
            return LoginResponse(status=200, messages=[], user_id=df["user_id"].values[0], user_name=df["user_name"].values[0])
        else:
            message_dict = db_access_service.select_message("msg-E-0001")
            return LoginResponse(status=200, messages=[message_dict])
```

**レビュー結果**

<div style="background: #f9fafb; border: 1px solid #cbd5e0; border-radius: 8px; padding: 24px; margin: 16px 0;">

**AIの生成結果（レビュー）**

```markdown
## コードレビュー結果

### 開発ルールとの相違点
| 指摘箇所 | 指摘理由 |
|-------------|----------------|
| **def login(mail_address, password):** | 引数に型アノテーションが欠けています。プロジェクトの開発ルールでは「すべての関数は引数・返値を明記したdocstringを持つ」とあるため、引数・返値の型指定および詳細なdocstring記述が必要です。例: `def login(mail_address: str, password: str) -> LoginResponse:` |
| **docstring内容** | docstringが最小限であり、開発ルールに定める「処理目的」「Args」「Returns」を明示した形式になっていません。 |

### プログラム上の誤り
| 指摘箇所 | 指摘理由 |
|-------------|----------------|
| **bcrypt.checkpw(password.encode("utf-8"), df["password"].values[0])** | DataFrame内の値が文字列（ハッシュ化済みパスワードの文字列）である場合、`bcrypt.checkpw` の第二引数は `bytes` でなければならないため、`df["password"].values[0].encode("utf-8")` にする必要があります。現状では型不一致が発生する可能性があります。 |

### 実装漏れ
| 指摘箇所 | 実装方法 |
|-------------|----------------|
| **例外・エラーハンドリング** | 仕様書および開発ルールでは、DB呼び出し部分に対して `try-except` 構文によるエラーハンドリングを行うことが求められています。本関数では例外捕捉処理がありません。 |
| **docstringの詳細化** | 「処理目的」「Args」「Returns」を明示したdocstringが漏れています。開発ルールに則り修正が必要です。 |

### 不要な処理
該当する指摘事項なし。

### その他の指摘や懸念事項
| 指摘箇所 | 指摘理由 |
|-------------|----------------|
| **statusコードの固定値200の使用** | 成否に関係なく常にHTTPステータスコード200が返却されています。認証失敗時には401等のエラーコードを返す方が適切です。 |
| **変数dfの命名** | `df` は抽象的な名称で可読性が低いです。`user_df` などに変更するとより望ましいです。 |
```

</div>

「開発ルール」の観点から型アノテーションやdocstringの欠如を指摘しているのがポイントです。プロジェクト要約を渡したことで、コードの正確性だけでなく「このプロジェクトでの書き方」という視点でのレビューができています。

### レビュー結果を元に自動修正

最後のステップ、レビュー指摘をコードに反映します。

<div style="background: #f0fdf4; border: 1px solid #86efac; border-radius: 8px; padding: 24px; margin: 16px 0;">

**📝 プロンプト（コード修正）**

```
上記のMarkdownファイルに記載されている仕様に基づいて、以下のコードを修正してください。
コード修正の際は以下のルールを必ず守ってください。
    1. コードの実装内容に基づいてコード内にコメントを追加してください。
    2. markdownファイルに記載されている処理がコードに存在しない場合は、それをコードに実装してください。
    3. markdownファイルに記載されていない処理がコードに存在する場合は、その処理をコードから削除してください。
    4. コードに問題がない箇所については変更しないようにしてください。
    5. 返答には修正したコード全体のみを含め、他の文章は不要です。
```

</div>

**修正後のコード**

<div style="background: #f9fafb; border: 1px solid #cbd5e0; border-radius: 8px; padding: 24px; margin: 16px 0;">

**AIの生成結果（修正後コード）**

```python
import bcrypt
from database import db_access_service
from models import LoginResponse


def login(mail_address: str, password: str) -> LoginResponse:
    """
    ユーザのメールアドレスとパスワードを用いてログイン認証を行う。

    Args:
        mail_address (str): ログイン対象のユーザのメールアドレス。
        password (str): ユーザが入力した平文パスワード。

    Returns:
        LoginResponse: ログイン処理結果。成功の場合はユーザ情報を含み、失敗の場合はエラーメッセージを返す。
    """
    try:
        # ユーザ情報をDBから取得
        user_df = db_access_service.select_user(mail_address)
    except Exception as e:
        # DBアクセス時の例外発生時は、汎用エラーメッセージを返却
        message_dict = db_access_service.select_message("msg-E-0002")
        return LoginResponse(status=500, messages=[message_dict])

    # ユーザ存在チェック
    if user_df.empty:
        # 対象ユーザが存在しない場合のエラーメッセージ取得
        message_dict = db_access_service.select_message("msg-E-0001")
        return LoginResponse(status=200, messages=[message_dict])

    # パスワード照合処理
    stored_password = user_df["password"].values[0].encode("utf-8")
    if bcrypt.checkpw(password.encode("utf-8"), stored_password):
        # パスワード一致時：ログイン成功レスポンスを返却
        return LoginResponse(
            status=200,
            messages=[],
            user_id=user_df["user_id"].values[0],
            user_name=user_df["user_name"].values[0],
        )
    else:
        # パスワード不一致時：エラーメッセージを返却
        message_dict = db_access_service.select_message("msg-E-0001")
        return LoginResponse(status=200, messages=[message_dict])
```

</div>

修正前と修正後を並べるとこんな感じです。

<div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

![レビュー前後のコード比較](/docs/Qiita/image/crs_extend_01/image_001.png)
*左：修正前（型アノテーションなし・docstringが1行・変数名`df`）　右：修正後（型アノテーション付き・詳細docstring・try-except・変数名`user_df`に変更）*

</div>

型アノテーション・詳細なdocstring・try-except・変数名 `user_df` への変更と、指摘事項がちゃんと反映されています。`msg-E-0002` を勝手に選んでいるなど完全ではないですが、方向としては正しい修正です。

### この仕組みの面白いところ

プロジェクト要約を「開発ルール」として渡すことで、**「このプロジェクトでの暗黙のルール」を軸にしたレビュー** ができるのが今回一番面白かった点です。

ただ、現状の要約はあくまでスナップショットなので、プロジェクトにコードが追加・変更されるたびに古くなっていきます。「コードが変わったら要約も自動更新する」仕組みを入れると、より実用的になりそうです。

---

## おまけ：単体テスト自動生成と Source Visualizer を試してみた

### 単体テスト自動生成

同じコードと仕様書を使って、テストコードも自動生成できるか試してみました。

<div style="background: #f0fdf4; border: 1px solid #86efac; border-radius: 8px; padding: 24px; margin: 16px 0;">

**📝 プロンプト（単体テスト生成）**

```
上記のMarkdownファイルに記載されている仕様に基づいて、以下のコードをテストするための単体テストコードを作成してください。
単体テスト作成の際は以下のルールを必ず守ってください。
    1. コードに実装されている各関数ごとに、正常系と異常系の単体テストを作成してください。
    2. テストの名称はテスト対象の関数名を使用して、正常系は「test_関数名_OK_関数ごとの連番」、異常系は「test_関数名_NG_関数ごとの連番」としてください。
    3. 引数の型や数が正しくないケースや、関数の戻り値の型が想定通りであるかどうかの確認など、自明なテストケースは不要です。
    4. 実装されているテスト対象の関数の分岐処理などをもれなく網羅することを意識してテストコードを作成してください。
    5. テスト対象のファイル以外で定義されている関数やクラスはモック化してテストコードを作成してください。
    6. 返答には作成したテストコード全体のみを含め、他の文章は不要です。
    7. テストに使用するデータや期待値の設定の方法、およびテストコードの書き方は、以下に記載するサンプルに可能な限り合わせて作成してください。

# 正常系
# 正しいIDとパスワードでログインできることを確認するテスト
def test_login_OK_01():
    ## テストデータ
    # メールアドレス
    mail_address = "sample@test.co.jp"
    # パスワード
    password = "pass"

    ## 期待値
    expect_res = {"status": "success", "user_id": 1, "user_name": "test user"}

    ## テスト処理
    result_res = login_service.login(mail_address=mail_address, password=password)

    ## 検証
    assert result_res == expect_res
```

</div>

生成されたテストコードがこちら。

<div style="background: #f9fafb; border: 1px solid #cbd5e0; border-radius: 8px; padding: 24px; margin: 16px 0;">

**AIの生成結果（テストコード）**

```python
import pytest
import bcrypt
import pandas as pd
from unittest.mock import patch, MagicMock
from models import LoginResponse
import services.login_service as login_service


# 正常系: 正しいメールアドレスとパスワードでログイン成功
def test_login_OK_01():
    mail_address = "sample@test.co.jp"
    password = "pass"
    hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    mock_user_df = pd.DataFrame({
        "user_id": [1],
        "user_name": ["test user"],
        "password": [hashed_pw]
    })

    with patch("services.login_service.db_access_service.select_user", return_value=mock_user_df):
        with patch("services.login_service.db_access_service.select_message") as mock_msg:
            result = login_service.login(mail_address, password)

    assert isinstance(result, LoginResponse)
    assert result.status == 200
    assert result.messages == []
    assert result.user_id == 1
    assert result.user_name == "test user"


# 異常系: DBアクセス時に例外が発生
def test_login_NG_01():
    mail_address = "sample@test.co.jp"
    password = "pass"

    with patch("services.login_service.db_access_service.select_user", side_effect=Exception("DB error")):
        with patch("services.login_service.db_access_service.select_message", return_value={"msg": "DB error"}) as mock_msg:
            result = login_service.login(mail_address, password)

    assert isinstance(result, LoginResponse)
    assert result.status == 500
    assert len(result.messages) == 1
    assert result.messages[0]["msg"] == "DB error"


# 異常系: ユーザが存在しない場合
def test_login_NG_02():
    mail_address = "sample@test.co.jp"
    password = "pass"
    mock_empty_df = pd.DataFrame()

    with patch("services.login_service.db_access_service.select_user", return_value=mock_empty_df):
        with patch("services.login_service.db_access_service.select_message", return_value={"msg": "user not found"}) as mock_msg:
            result = login_service.login(mail_address, password)

    assert isinstance(result, LoginResponse)
    assert result.status == 200
    assert len(result.messages) == 1
    assert result.messages[0]["msg"] == "user not found"


# 異常系: パスワード不一致の場合
def test_login_NG_03():
    mail_address = "sample@test.co.jp"
    password = "wrong_pass"
    stored_pw = bcrypt.hashpw("correct_pass".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    mock_user_df = pd.DataFrame({
        "user_id": [1],
        "user_name": ["test user"],
        "password": [stored_pw]
    })

    with patch("services.login_service.db_access_service.select_user", return_value=mock_user_df):
        with patch("services.login_service.db_access_service.select_message", return_value={"msg": "login failed"}) as mock_msg:
            result = login_service.login(mail_address, password)

    assert isinstance(result, LoginResponse)
    assert result.status == 200
    assert len(result.messages) == 1
    assert result.messages[0]["msg"] == "login failed"
```

</div>

正常系・異常系の網羅という観点は指示通りです。ただ、いくつか惜しい点も。

- テストの書き方（テストデータ・期待値・テスト処理・検証のコメント区切り）がサンプルと違う
- 説明コメントがほぼない
- 使っていない `MagicMock` がインポートされている

テストコードを任せる場合は「書き方のサンプルをより具体的に」「テストデータの注釈を細かく指定する」といったプロンプトの作り込みがさらに必要そうです。

---

### Source Visualizer：ソースの依存関係をMermaidで図示する

「プロジェクト全体のファイル間の関係を図にできたら、参画直後のエンジニアが全体像を掴みやすいのでは？」と思って試してみました。

入力はプロジェクト要約と同じJSON、出力はMermaidの `classDiagram` 形式です。Chat-GPTにいくつかのパターンを出してもらいながらプロンプトを設計しました。

<div style="background: #f0fdf4; border: 1px solid #86efac; border-radius: 8px; padding: 24px; margin: 16px 0;">

**📝 プロンプト（ソース可視化）**

```
あなたはソフトウェア解析アシスタントです。
これから渡す JSON はプロジェクトを構成する全ファイルの情報で、各要素は次の形式です。
- full_path: ファイルのフルパス（例：app/services/login_service.py）
- contents: ファイルの中身（Pythonコード文字列）

このJSONを解析し、Mermaidの classDiagram を1つ出力してください。出力は Mermaidコードブロックのみにしてください。説明文や前置きは不要です。

## 目的

プロジェクト全体の「ファイル単位の構造（何がどこにあるか）」と「ファイル間の参照関係（import依存）」を、視認性重視で俯瞰できる図を作る。

## 作図ルール（厳守）

1. Mermaidは classDiagram を使用し、先頭に direction LR を入れること。
2. 各ファイルを1つのクラスとして表現すること。
3. 各クラス（=ファイル）のボディには、そのファイルで定義されている関数を `+関数名()` 形式で列挙すること。
4. 矢印（依存関係）はファイル間のみを表現する。関数同士の矢印は描かないこと。
5. 依存関係は import依存から抽出すること。
6. 依存矢印は「ファイルA → ファイルB」で1本のみにすること（複数importがあっても1本に集約）。
7. 矢印は A ..> B を使用すること。
8. テストファイルと外部ライブラリは除外すること。
9. 出力は1つの classDiagram にまとめること。
```

</div>

出力された図がこちらです。

<div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

![Mermaidによるファイル依存関係の図示](/docs/Qiita/image/crs_extend_01/image_002.png)
*CRSアプリ内の「プロジェクト構成図」画面。生成されたMermaidのクラス図がそのままWeb UI上に表示される。ズームや図のダウンロードにも対応している*

</div>

...正直、見づらいです。

出力された情報自体は正確なのですが、これだけファイルが多いと全体を1画面に収めることが難しく、各要素がとても小さくなってしまいます。「インポート関係のみ」という抽象度では、関数単位・機能単位の関係性まで掘り下げられず、結局「コードを見る」のと変わらない情報量になってしまいました。

根本的な問題は「ファイルの中身をそのままテキストとして渡している」点で、AIによる解析頼みになってしまっていること。ファイル間の関係を事前にパースして構造化したうえで渡せれば、もっとうまくいきそうです。プロジェクトの全体像をビジュアル化するというアイデアは面白いので、アプローチを変えて再挑戦したいところです。

---

## まとめ

今回の拡張で得られた知見をまとめます。

**うまくいったこと**

- プロジェクト全体のコードを渡すことで、フォルダ構成・機能概要・コーディング規約を自動でまとめられた
- One-Shot形式から「出力形式をMarkdownで直接指定する形式」に変えたことで、プロンプトの管理が楽になった
- プロジェクト要約をレビューに活用することで「このプロジェクト固有の開発ルール」に基づいた指摘ができた
- 翻訳→レビュー→修正の一気通貫フローで、コードの品質改善が自動的に行えた

**残った課題**

- プロジェクトのコードが更新されると要約が古くなる（要約の自動更新が必要）
- テストコードの書き方はプロンプトをより具体的にしないと指定通りにならない
- ファイル依存関係の可視化は、情報量が多いとMermaidでは限界がある

CRSはAISのメンバーが「自分たちの手でAIアプリを設計・実装する」という学習目的でスタートしたプロジェクトです。車輪の再発明であることは承知の上で、あえて一から作ることに意味があると考えています。既存ツールをそのまま使うだけでは得られない、「なぜこのプロンプトが機能するのか」「どこに限界があるのか」という肌感覚を、チームで議論しながら積み上げてきました。

AISではこうした取り組みを通じて、AIの可能性を実践的に探っていく活動も行っています。この記事がAISの活動を知っていただくきっかけになれば嬉しいです。

最後まで読んでいただきありがとうございました！
