<style>
.image-section {
  background: #e9f7ff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 16px;
  margin: 16px 0;
  display: inline-block;
  width: fit-content;
}
.output-section {
  background: #f9fafb;
  border: 1px solid #cbd5e0;
  border-radius: 8px;
  padding: 24px;
  margin: 16px 0;
}
</style>

## Code Review Supporter Applicationの拡張1
現在のCode Review Supporter Applicationは以下の課題を抱えている。

- ファイルを独立に翻訳している
- コード翻訳を非同期的に処理している

これらに対する解決策を探したい。

---

### 1. コード全体の翻訳
#### 1.1. 要件の定義
実際のプロジェクトでは、個別にコードの実装をすることは極めて稀であるといえる。
なぜなら既存のプロジェクトに途中参画する場合は当然すでに動いているコードがあるわけだし、
新規開発であってもシステムとよべるものである以上、ある程度まとまったコードが必要となるのは想像に難くない。

まずは本記事での**プロジェクト**(*project*)を定義しよう。

!!! note 定義 1.1. プロジェクト
    アプリケーションやシステムを動かすために実装されたコード全体、およびそのコードを実装するために制定されたルールのことを**プロジェクト**(*project*)とよぶことにする。

上記の定義では、既にチームで開発作業を行っている実装者や新規参画者に対して、実装されたコードの個人差をなくすために制定されたルールなども含めているが、これは「明文化されていない暗黙のルールについても可能な限り取り纏め、すべての開発者が確認可能にしておくぺきだ」という思想に基づく。

例えば、以下のようなフォルダ構成で作成されるコード全体がプロジェクトである。

```markdown

src/
├── main.py
├── models.py
├── common/
│   ├── constant.py
│   ├── common_validate.py
├── services/
│   ├── login_service.py
│   ├── task_list_service.py
│   ├── task_detail_service.py
├── tests/
│   ├── test_unit_common.py
│   ├── test_unit_login.py
...

```

次に、想定するシステムのユーザを設定する。
「プロジェクトで開発しているシステム」のユーザではなくCode Review Supporter Applicationのユーザであることに注意。

!!! note Fact 1.1. 想定システム利用ユーザ
    新たに案件に参画したシステム開発(初心)者。既存のシステムに対して機能拡充するタスクが割り当てられている。

上記の元、このユーザにインプットとして必要となる事柄について考えよう。

既存のシステムの追加開発においては、そのシステムがどのような物であるかの理解が求められるであろう。
どのような目的で作成されたシステムなのか、どのような機能があるのか、システム全体の構成はどうなっているのか、動作する環境はStand AloneなのかCloud Serviceなのか、...
確認すべき情報は山のようにあるが、コード自体からは読み取れないことも多い。差し当たってはコードの内容のみに注目し、以下を対象としよう。

- プロジェクト概要
- 各機能の説明

次にコード自体に着目する。
プロジェクトにはしばしば多数のフォルダやファイルがあり、それぞれに役割がある。
だがそれらの役割は中身を見なければ把握することは難しい。プロジェクトが大きくなればその分フォルダやファイル数は増加するだろう。
そのため、全体の構成を俯瞰して各々のフォルダやファイルがどのような役割を担っているのかを出力とする。

- プロジェクトのフォルダ構成
- フォルダごとの役割

最後に「明文化されていない暗黙のルール」である。
これは別途別のドキュメントなどで制定されていればそれらを参照すればよいが、開発スピードの早い実際の現場では実装者の癖が如実に表れる箇所である。
すべてのコーディングルールを取りまとめることは困難だが、明文化するという観点からAIに自動でやってもらうのも新規参画者の助けとなると信じて、ここでは出力観点に加える。

- プロジェクト内で制定されたコーディング規約

これらの出力がされることを目標にプロンプトを考える。

#### 1.2. プロンプトの作成
現在のCode Review Supporter Applicationの使用方法としては、任意のファイルを翻訳対象に設定可能である。
が、ここでは先ほどの想定システム利用ユーザに基づき翻訳対象はプロジェクト全体としよう。
幸いCode Review Supporter Applicationでは翻訳対象に指定されたファイルのフルパスを情報として持っているので、そのパス情報からフォルダ構成やファイルの位置づけ情報が抽出できるだろう。
フルパスとコードの中身を紐づけて、プロジェクトの全コードを分析可能にする。

入力例としては以下の形式をイメージしている。

```markdown

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

この入力に対して、上記の要件を満たす出力を与えるプロンプトを考える。
Code Review Supporter Applicationで使用しているプロンプトは具体的な入力例と出力例を与えて出力の形式を整えるOne-Shot形式を使用しているが、これには「学習用の例を作成するのが手間」「出力の形式を変えるのが難しい」「送信するデータ量が増える」などの問題がある。
これらを解決すべく、今回は直接出力形式を指定してみる。説明するより見たほうが早いだろう。

``` markdown

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

実際のコードでは前半の説明文と後半のMarkdown例が分かれているので出力形式の変更が簡単に行える他、出力例を都度用意する必要が解消されている。
このプロンプトを使用した、実際の出力結果を見てみよう。

<div class="output-section">

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
- DBおよびAzureリソースへの直接接続テストも含む総合検証を実装。

---

</div>

#### 1.3. 成果と課題

出力結果を見ると以下のことがわかる。

- プロンプトで指定した以下4つの項目が設定されている。
   - プロジェクト概要
   - プロジェクト構成
   - フォルダごとの役割
   - コーディング規約
- 「プロジェクト概要」ではシステム全体の説明と各機能ごとの説明が記載されている。
- 「プロジェクト構成」ではプロジェクトのフォルダ構成が再現されている。
- 「フォルダごとの役割」ではプロジェクトに存在するフォルダすべてと、それぞれのフォルダごとの位置づけが記載されている。
- 「コーディング規約」では、プロジェクトのコード群から統一したルールが抽出されている。

まだBrush up可能な箇所は見受けられるが、足掛かりとしては申し分ないだろう。
プロジェクトの実態と比較すると、以下の点が網羅されているとなおよい出力になるかと思う。

- 「ファイル共有機能」や「ユーザ認証機能」などはあくまでサーバ内部の処理の説明で、システムとしてユーザに提供している機能ではないよね。
- 「ドキュメンテーション」や「エラーハンドリング」などの部分でも、「命名規則」と同じように例が記載されているとわかりやすそう。
- 「データモデル設計」や「並列／非同期処理」の項目は書いている内容が抽象的過ぎて、この出力内容では役立てられないかも。

発展的な課題として以下を挙げておく。

- 既にまとめられた規約が別ファイルにある場合は、その内容も取り込んで出力できるとよい。
- コーディング規約以外にも、暗黙知としてコード内に存在する概念を抽出することが出来れば別の使い方ができるかもしれない。
- プロジェクトを構成するファイルが更新された場合、プロジェクトの要約結果も自動で更新されるとよい。

### 2. 非同期的なコード翻訳
#### 2.1. 要件の定義
現在Code Review Supporter Applicationでは以下のフローで処理を行っている。

```mermaid

graph LR   
A[コードアップロード] --> B[非同期翻訳処理] 
B --> C[翻訳結果登録]  
C --> D[翻訳結果確認] 

```

翻訳処理を非同期で行っているため、複数ファイルを同時に翻訳しようとした場合にすべてのファイルの処理が終わるまで結果を確認できないのである。
そのため、ここではコードの翻訳を同期的に実行する方法について考える他、Code Reviewの本義であるレビュー部分も同期的に行う機能を追加しよう。本格的な機能の実装は他の人に移譲するものとして、まずは1ファイルの同期翻訳を試みる。

**やりたいこと**

- ファイルの翻訳を同期的に行う
- コードのレビューを自動で行う
- レビューの指摘修正も自動で行う

つまり以下のフローで操作を行うことである。

```mermaid

graph LR   
A[コード登録] --> B[翻訳結果取得] 
B --> C[レビュー実施]  
C --> D[レビュー指摘反映] 

```

#### 2.2. プロンプトの作成
コード翻訳自体はすでにプロンプトが用意されているので、それを使用することにする。
考えるべくは取得したコードに対してどのようにレビューするかだが、ここで[前項](#1-コード全体の翻訳)で作成したプロジェクト全体の要約が生きてくる。
他に実装されているコードと書き方の平仄があっているかを確認するため、この要約の内容を加味するようにプロンプトを作成したい。

レビューで確認したい観点としては以下。

- 想定する機能が正しく実装されているか
  - 必要な処理が実現されているか
  - 不要な処理が記載されていないか
  - プログラム上の誤りがないか
- 他のコードと比べて実装方法の平仄がとれているか

前項で作成したプロンプトと同様に、「学習用の例を作成するのが手間」「出力の形式を変えるのが難しい」などの問題を解決すべく以下のようにプロンプトを設定した。

```markdown

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

さらにレビュー時にはプロジェクトの要約を加味するように、プロジェクトの情報と以下のプロンプトを追加。

```markdown

このプロジェクトでは、上記のMarkdownに記載されている開発ルールを順守して開発を行っています。
既存のフォルダ構成やファイル名はこちらを参考にしてください。
今後コードの修正や追加、レビューを行う場合は、可能な限りこの開発ルールに準拠するようにしてください。
```

では実際の出力結果を確認しよう。

**入力**
- コード
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
- 設計
    ```markdown

    ## 定数  
    なし

    ---

    ## クラス  

    ### `LoginResponse`
    - **説明**: ログイン処理の結果を返すレスポンスモデル。  
    - ログインの成否を示すステータスコード、エラーメッセージ、ユーザ情報を保持する。
    - **メンバー**:  
    - `status`: 処理結果のステータスコード（例: 200）。  
    - `messages`: エラーや警告を含むメッセージリスト。  
    - `user_id`: ユーザID。  
    - `user_name`: ユーザ名。  
    - **備考**: コード内ではインスタンス生成時にプロパティに値が割り当てられるのみで、処理ロジックは持たない。

    ---

    ## 関数  

    ### `login(mail_address: str, password: str) -> LoginResponse`

    #### 処理目的  
    ユーザのメールアドレスとパスワードを用いてログイン認証を行い、その結果を `LoginResponse` オブジェクトとして返す。

    #### 入力  
    - `mail_address`: ログイン対象のユーザのメールアドレス（文字列）。  
    - `password`: ユーザが入力した平文パスワード（文字列）。

    #### 出力  
    - `LoginResponse`: ログイン処理結果。成功の場合はユーザ情報を含み、失敗の場合はエラーメッセージを返す。

    #### アルゴリズム  
    1. **ユーザ情報の取得**  
    - `db_access_service.select_user(mail_address)` を呼び出して、引数のメールアドレスに対応するユーザ情報をデータベースから取得。  
    - 結果は `df` （DataFrame形式）に格納される。  

    2. **ユーザ存在チェック**  
    - 取得結果の `df.empty` を確認。  
    - `df` が空（対象ユーザが存在しない）場合：
        1. エラーメッセージを取得するため、`db_access_service.select_message("msg-E-0001")` を呼び出す。  
            - `"msg-E-0001"` はユーザ未登録または認証失敗時に用いるメッセージID。  
        2. 新しい `LoginResponse` を生成し、以下を設定して返却する。  
            - `status=200`  
            - `messages=[message_dict]`  
            - 他の項目（`user_id`, `user_name`）は省略される。  

    3. **ユーザが存在する場合**  
    - データベースから取得した `df["password"].values[0]` に格納されたハッシュ化済パスワードと、入力パスワードの照合を行う。  
    - `bcrypt.checkpw(password.encode("utf-8"), df["password"].values[0])` を使用：  
        - 入力パスワードを UTF-8 にエンコードし、DB上のハッシュ値と照合。  
        - `True` の場合：パスワード一致。  
        - `False` の場合：不一致。  

    4. **パスワード一致時の処理**  
    - パスワードが正しければ、ログイン成功。  
    - 以下を設定して `LoginResponse` を返却：  
        - `status=200`  
        - `messages=[]`（エラーなし）  
        - `user_id=df["user_id"].values[0]`  
        - `user_name=df["user_name"].values[0]`

    5. **パスワード不一致時の処理**  
    - エラーメッセージを再取得：`db_access_service.select_message("msg-E-0001")`  
    - 以下を設定して `LoginResponse` を返却：  
        - `status=200`  
        - `messages=[message_dict]`
    ---
    ```

**出力**

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
| **例外・エラーハンドリング** | 仕様書および開発ルールでは、DB呼び出し部分に対して `try-except` 構文によるエラーハンドリングを行うことが求められています。本関数では例外捕捉処理がありません。以下のような修正が必要です。  
python
try:
    df = db_access_service.select_user(mail_address)
except Exception as e:
    message_dict = db_access_service.select_message("msg-E-0002")
    return LoginResponse(status=500, messages=[message_dict])
 |
| **docstringの詳細化** | 「処理目的」「Args」「Returns」を明示したdocstringが漏れています。開発ルールに則り修正が必要です。 |

### 不要な処理
| 指摘箇所 | 指摘理由 |
|-------------|----------------|
| 該当する指摘事項なし。 |

### その他の指摘や懸念事項
| 指摘箇所 | 指摘理由 |
|-------------|----------------|
| **statusコードの固定値200の使用** | 成否に関係なく常にHTTPステータスコード200が返却されています。仕様書上は明示されていませんが、一般的なREST API設計の観点からは、認証失敗時には401等のエラーコードを返す方が適切です。 |
| **変数dfの命名** | `df` は抽象的な名称で可読性が低いです。開発ルール上、関数・変数名にはスネークケースを用い意味を明確にすることが推奨されているため、例: `user_df` などに変更するとより望ましいです。 |
```

出力結果が若干見づらいなどの課題はあるものの、レビューするという観点は満たされていると言えるだろう。
特に「開発ルール」と銘打たれた、「明文化されていないプロジェクトのコーディング規則」に則り指摘事項を挙げている点は高評価。

次の手順に移ろう。
このレビュー結果をもって既存のコードを修正する。プロンプトとしては以下を用意した。

```markdown

上記のMarkdownファイルに記載されている仕様に基づいて、以下のコードを修正してください。
コード修正の際は以下のルールを必ず守ってください。
    1. コードの実装内容に基づいてコード内にコメントを追加してください。
    2. markdownファイルに記載されている処理がコードに存在しない場合は、それをコードに実装してください。
    3. markdownファイルに記載されていない処理がコードに存在する場合は、その処理をコードから削除してください。
    4. コードに問題がない箇所については変更しないようにしてください。
    5. 返答には修正したコード全体のみを含め、他の文章は不要です。
```

実際の出力結果を確認する。

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

エラーメッセージ`msg-E-0002`が勝手に選択されている問題はあるが、型アノテーションや変数名、処理の仕方を見るに前述の指摘事項が反映されたコードとなっていることが確認できる。

#### 2.3. 成果と課題
一連の操作を経て、レビュー前と修正後のコードを比較してみよう。

<div class="image-section">

![alt text](/image/crs_extend_01/image_001.png)

</div>

実際の処理については確認する必要はあるが、docstringをはじめ必要なコメントが付与されていてより品質の高いコードに仕上がっているように見える。
今回は完成状態のコードを翻訳した結果を設計としたが、設計自体の品質が向上すれば結果として出力される結果の品質も上がることは想像に難くない。
また、現在は既存のコードが持つ「明文化されていないプロジェクトのコーディング規則」が単一のファイルであくまで要約結果でしかないため、プロジェクトにコードが追加されて進化するごとに更新されていけば、より実態に即したレビューができるだろう。

発展的な課題として以下を挙げておく。
- プロジェクトの要約ではなく、個別のコードの情報を保持したまま同様の処理があればロジックを併せるなど、参照してレビューが行えるとよい。
- ExcelファイルやPDFなど、設計情報として受け取れるデータの形式が増やせるとよい。

### 3. Cパート
既存の課題解決とは別に、今回以下の機能をおためしで実装してみた。

- 単体テスト自動作成
- Source Visualizer

#### 3.1. 単体テスト自動作成
作成したコードと設計情報から以下のプロンプトで単体テストのコード作成を試みる。

```markdown

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
    expect_res = {""status": "success", "user_id": 1, "user_name": "test user"}

    ## テスト処理
    result_res = login_service.login(mail_address=mail_address, password=password)

    ## 検証
    assert result_res == expect_res
```

このプロンプトで以下のテストコードが得られた。

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

テスト観点やテスト関数の名称については指定通りだが、肝心のテストの書き方が指定と違ってしまっている。
またテスト部分のコードに説明が一切存在しなかったり使用していないライブラリがインポートされていたりなど、些か品質に問題があると言わざるを得ない。

総じて、テストコードを作成する場合にはより具体的な仕様の情報とテストデータの例、さらに具体的なプロンプトでの指示が必要だと言えよう。

#### 3.2. Source Visualizer
[コード全体の翻訳](#1-コード全体の翻訳)で抽出したプロジェクト全体のファイル間の関係性を図示してみてはどうかと考えた。
入力としては要約作成に使用したデータと同じデータを使用し、出力はMermaidで作成されたファイル同士の関係性図を想定。
Chat-GPTに入力データを渡していくつか出力のパターンを提示してもらいながら、イメージに合う図示の形式を決定。最初の入力から期待する出力図を作成するためのプロンプトの作成を依頼した。
結果として以下のプロンプトが得られた。

<div class="output-section">
あなたはソフトウェア解析アシスタントです。
これから渡す JSON はプロジェクトを構成する全ファイルの情報で、各要素は次の形式です。
- full_path: ファイルのフルパス（例：app/services/login_service.py）
- contents: ファイルの中身（Pythonコード文字列）

このJSONを解析し、Mermaidの classDiagram を1つ出力してください。出力は Mermaidコードブロックのみ（mermaid ～ ）にしてください。説明文や前置きは不要です。

## 目的

プロジェクト全体の「ファイル単位の構造（何がどこにあるか）」と「ファイル間の参照関係（import依存）」を、視認性重視で俯瞰できる図を作る。

## 作図ルール（厳守）

1. Mermaidは classDiagram を使用し、先頭に direction LR を入れること。
2. 各ファイルを1つのクラスとして表現すること。
    - クラス名はファイルパスを元に一意になるように作ること（例：services/login_service.py → services_login_service_py）。
    - 記号（/ . -）はクラス名に使えないため、すべて _ に置換し、末尾の .py は _py に置換するなどして 衝突しない命名にすること。
3. 各クラス（=ファイル）のボディには、そのファイルで 定義されている関数を列挙すること。
    - Pythonの def を対象（トップレベル関数、クラス内メソッドの両方を含めて良い）。
    - 表示形式は +関数名() とする。
    - async def は +関数名() の末尾に %% async コメントを付けても良い（任意）。
    - クラス定義（class X:）がある場合は、関数ではないが可視化したいので +X として列挙して良い（任意）。
4. 矢印（依存関係）はファイル間のみを表現する。関数同士の矢印は描かないこと。
5. 依存関係は import依存から抽出すること。対象は以下：
    - import xxx
    - from xxx import yyy
    - 相対import（from .xxx import yyy, from ..xxx import yyy）も可能な範囲で解決すること。
6. 依存矢印は 「ファイルA → ファイルB」で1本のみにすること（同一ペアで複数importがあっても1本に集約）。
7. 矢印は classDiagram の依存表現として A ..> B を使用すること。
8. テストファイルは除外すること。
9. 外部ライブラリ（例：fastapi, pydantic, sqlalchemy, azure 等）は図の対象外。
10. 依存関係の矢印も、プロジェクト内ファイル同士の関係だけを出すこと。
11. 出力は 1つの classDiagram にまとめること。

## 出力フォーマット

出力は必ず次の形式にすること：
```
classDiagram
direction LR
...（クラス定義）
...（依存矢印：A ..> B）
```
それでは、以下のJSONを解析してMermaidを出力してください。
</div>

このプロンプトにより作成されたMermaid図は以下のようになる。

<div class="image-section">

![alt text](/image/crs_extend_01/image_002.png)

</div>

...見づらい。
小規模なシステムでこの有様である。より実践的な場面では役に立たないだろう。
一応元となった[Mermaid](/appendix/crs_extend_01/Code%20Review%20Supporter_構成図.md)も添付しておく。

見る限り出力された情報に誤りはなさそうなのだが、各クラスの位置が固定されていて全体を画面に収めることが難しく、どうしても各要素が小さくなってしまう。
では要素を移動可能な形式で出力するのはどうかと考えるのは自然な発想だが、入力として渡しているコードが問題で、ただただファイルの中身を文字列として渡してしまっているため、ファイル間の関係性の理解がAIの解析頼みになってしまっている。さらにこの図を作成するためにすべてのファイルの中身をAIが読み込まねばならず、処理にも当然時間がかかる。
問題を挙げればキリがないが、何より根本的な問題が、この図から何も有益な情報を抽出できないことである。
「どのクラスがどのクラスを参照しているか」というインポート部分の情報のみを抽出した抽象度の高い情報では、肝心な関数単位や機能単位の関係性の解析まで踏み込めておらず、結局個々のコードを見ないとプロジェクトの実態が何も分からない。

プロジェクトの全体の様子をVisualizeして表示するというのはよい試みだったと思うが、本システムでは実現に乏しい状況だったと言わざるを得ない。

#### 3.3. 総括
今回は既存のシステムCode Review Supporter Applicationに対して追加機能という形でモデルの性能検証を行った。
この検証を経て以下の知見が得られた。

- プロジェクト要約作成による暗黙知の明文化
- 出力形式を指定したプロンプトによる事前学習の簡素化
- AIによるプロンプトの作成
- Mermaidによる図作成

これらの得られた知見は有意義なものであるが、同時に課題もいくつか残している。

- プロジェクトコードの更新による要約内容の化石化
- 作成するコードの厳密な構成指定
- プロジェクト全体の参照関係の図示

今後のモデルの性能向上と共に、これらの問題が解消されることに期待することにする。
