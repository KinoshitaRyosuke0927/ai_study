# AI PowerPoint レビュアー 利用手順

`.pptx` ファイルをアップロードすると、スライドを画像化し AI がレビューしてくれるアプリケーションです。

## 1. フォルダ構成

配布フォルダ（例: `ai_reviewer`）には以下が含まれています。

```
ai_reviewer/
├── ai_reviewer.exe   ... アプリ本体
├── 起動.bat           ... ダブルクリックで起動＆ブラウザを開くショートカット
├── .env               ... Azure OpenAI の接続情報
├── review_point.csv   ... レビュー観点一覧（自分で編集可能）
└── _internal/         ... アプリ動作用の内部ファイル（触らないでください）
```

## 2. 事前にインストールが必要なもの

このアプリはPowerPointをPDF経由で画像化するため、以下の2つを事前にPCへインストールしておく必要があります（exeには同梱されていません）。

### 2-1. LibreOffice（PowerPoint → PDF変換に使用）

1. [LibreOffice 公式サイト](https://www.libreoffice.org/download/) からWindows版インストーラーをダウンロードして実行します。
2. インストール先はデフォルト（`C:\Program Files\LibreOffice\`）のままで問題ありません。アプリが自動的に `C:\Program Files\LibreOffice\program\soffice.exe` を検出します。

### 2-2. Poppler（PDF → 画像変換に使用）

1. [poppler-windows releases](https://github.com/oschwartz10612/poppler-windows/releases/) から最新版のzipをダウンロードします。
2. 任意の場所（例: `C:\poppler`）に展開します。
3. 展開したフォルダ内の `bin` フォルダ（例: `C:\poppler\poppler-24.xx.x\Library\bin`）を、Windowsのシステム環境変数 `PATH` に追加します。
   - 「システムの詳細設定」→「環境変数」→「Path」を編集 →「新規」で上記パスを追加 → OK
4. 追加後は一度PCを再起動するか、コマンドプロンプトを開き直してから利用してください。

## 3. レビュー観点の設定

`ai_reviewer.exe` と同じフォルダに配置された `review_point.csv` を編集することで、AIがレビューする観点を自由にカスタマイズできます。

- 列構成: `role,perspective_type,detail`
- `role`列は現在使用していないので適当に設定してください。
- `perspective_type` は `overall` / `story` / `plan` / `assignment` / `priority` / `feasibility` / `evaluation` のいずれかを指定します。
- 編集後は保存するだけで反映されます（アプリの再起動は不要です）。

## 4. アプリの起動方法

`起動.bat` をダブルクリックしてください。自動的にアプリが起動し、既定のブラウザで `http://localhost:8000` が開きます。

（`起動.bat` を使わず `ai_reviewer.exe` を直接ダブルクリックした場合は、手動でブラウザから `http://localhost:8000` にアクセスしてください。）

起動時に黒いコンソール画面が表示されますが、これはアプリのログ出力用の画面です。閉じるとアプリが終了するため、利用中は閉じないでください。

## 5. 使い方

1. ブラウザ上で `.pptx` ファイルをアップロードします。
2. スライドが画像として表示されます。
3. 必要に応じて各スライドの「伝えたいこと」を入力します。
4. レビューを実行すると、AIが観点別にレビュー結果を返します。
5. 修正方針を提案してもらうと、AIがスライド別に修正案を返します。

## 6. アプリの終了方法

起動中のコンソール画面を閉じるか、`Ctrl + C` を押してください。

## 7. トラブルシューティング

| 症状 | 原因・対処 |
|------|-----------|
| 起動直後にコンソールが閉じてエラーで落ちる（`KeyError: 'AZURE_OPENAI_ENDPOINT'`） | `.env` がexeと同じフォルダに無い、または内容が未設定です。 |
| PPTXアップロード時に「LibreOffice が見つかりません」エラー | LibreOfficeが未インストール、または既定パス以外にインストールされています。2-1を確認してください。 |
| PPTXアップロード時に「Poppler が必要です」エラー | Popplerが未インストール、またはPATHが通っていません。2-2を確認し、PC再起動後に再度お試しください。 |
| レビュー観点を変えたい | `review_point.csv` を編集してください。 |
| ブラウザで画面が表示されない | コンソール画面にエラーが出ていないか確認し、`http://localhost:8000` に手動でアクセスしてください。すでに同じポートで別プロセスが起動している場合は、そちらを終了してから再度お試しください。 |
