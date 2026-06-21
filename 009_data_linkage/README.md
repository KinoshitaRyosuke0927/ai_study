# 009 Trello カード追加アプリ

Flask + Trello API を使って、指定ボードのリストへカードを追加するミニマル Web アプリです。

## ディレクトリ構成

```
009_data_linkage/
├── app.py                # Flask バックエンド
├── templates/
│   └── index.html        # メイン画面
├── static/
│   ├── style.css         # スタイル
│   └── app.js            # フロントエンドロジック
├── requirements.txt
├── .env.example
└── README.md
```

## セットアップ手順

### 1. 仮想環境を作成して有効化

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Mac/Linux
python -m venv .venv
source .venv/bin/activate
```

### 2. 依存パッケージをインストール

```bash
pip install -r requirements.txt
```

### 3. 環境変数を設定

`.env.example` を `.env` にコピーして、実際の値を記入します。

```bash
cp .env.example .env
```

`.env` を編集:

```
TRELLO_API_KEY=実際のAPIキー
TRELLO_TOKEN=実際のトークン
TRELLO_BOARD_ID=9SxsLnD4
```

### 4. Trello API Key / Token の取得方法

1. **API Key の取得**
   - https://trello.com/power-ups/admin にアクセス
   - 新しいパワーアップを作成し、API Key を確認

2. **Token の取得**
   - 以下の URL を開く（`<YOUR_API_KEY>` を実際の値に置換）
   ```
   https://trello.com/1/authorize?expiration=never&scope=read,write&response_type=token&key=<YOUR_API_KEY>
   ```
   - Trello の認証画面で「許可」をクリックしてトークンをコピー

### 5. アプリを起動

```bash
python app.py
```

### 6. ブラウザで確認

http://localhost:5000 にアクセスしてください。

## 画面の使い方

1. 「追加先リスト」プルダウンからリストを選択
2. 「カードタイトル」に追加したいカードの名前を入力（必須）
3. 「説明」に詳細を入力（任意）
4. 「カードを追加」ボタンをクリック
5. 成功すると画面下部に Trello カードの URL が表示されます

## API エンドポイント

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/` | メイン画面 |
| GET | `/api/lists` | ボード内リスト一覧取得 |
| POST | `/api/cards` | カード追加 |

### POST /api/cards リクエスト例

```json
{
  "list_id": "リストのID",
  "title": "カードタイトル",
  "description": "説明文（任意）"
}
```

#### Trelloシステムアカウント情報
```
e-mail : aissystemadmin@gmail.com
pass : JBDais0343308194
```
