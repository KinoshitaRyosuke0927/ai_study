
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
