# DocAI UI/UXリデザイン実施プロンプト v2（Claude Code用）

> **このプロンプトは前バージョンの完全置き換え版です。**
> タスク詳細画面の翻訳結果表示部分を 3カラムレイアウト（display_b2 デザイン）に全面改訂しています。

---

## ■ タスク概要

このプロジェクトのフロントエンドのUI/UXを全面的にリデザインしてください。
デザインの方針・仕様はすべて本プロンプトに定義しています。
**ビジネスロジック・APIコール・バックエンドの処理は一切変更しないでください。変更するのは見た目（HTML/CSS/テンプレート/スタイルシート）に関する部分のみです。**

---

## ■ 事前確認事項

作業を開始する前に、以下を必ず確認してください。

1. **プロジェクト構成の把握**
   - フレームワークは何か（React / Vue / Next.js / Jinja2 / Django Templates / plain HTML など）
   - CSS の管理方法（CSS Modules / Tailwind CSS / SCSS / グローバルCSS / styled-components など）
   - コンポーネントの分割構成（どのファイルがどの画面・コンポーネントに対応するか）
   - 既存のスタイル変数・テーマ設定ファイルの有無（`theme.ts`, `variables.css`, `tailwind.config.js` など）

2. **対象画面の特定**
   以下3画面に対応するテンプレート・コンポーネントファイルをすべて列挙してください。
   - ログイン画面
   - タスク一覧画面
   - タスク詳細画面（翻訳結果表示ページ）

3. **共通コンポーネントの特定**
   以下が独立したコンポーネントとして実装されているか確認し、そのファイルパスを列挙してください。
   - ナビゲーションバー（ヘッダー）
   - ステータスバッジ
   - ボタン
   - フォームインプット
   - カード

構成を把握した上で、以下の仕様に従いリデザインを実施してください。

---

## ■ デザインシステム定義

### 1. カラーパレット

以下の色をプロジェクトの管理方式に合わせて定義してください。
CSS変数が使える場合は `:root` に定義し、Tailwindの場合は `tailwind.config.js` の `extend.colors` に追加してください。

```css
/* 背景・サーフェス */
--color-bg:           #F8FAFC;   /* ページ背景 */
--color-surface:      #FFFFFF;   /* カード・パネル背景 */
--color-surface-sub:  #F1F5F9;   /* サブ背景（テーブルヘッダー、コードブロック外枠など） */
--color-surface-code: #1E293B;   /* コードブロック背景（ダーク） */

/* ボーダー */
--color-border:       #E2E8F0;   /* 通常ボーダー */
--color-border-sub:   #F1F5F9;   /* 薄いボーダー（テーブル行区切り） */

/* テキスト */
--color-text-primary:     #1E293B;  /* 見出し・重要テキスト */
--color-text-secondary:   #374151;  /* 通常テキスト */
--color-text-muted:       #64748B;  /* 補助テキスト・ラベル */
--color-text-placeholder: #CBD5E1;  /* プレースホルダー・「該当なし」テキスト */

/* アクセントカラー（Blue/Indigo） */
--color-accent:            #3B82F6;
--color-accent-dark:       #2563EB;
--color-accent-gradient:   linear-gradient(135deg, #3B82F6, #6366F1);
--color-accent-bg:         #EFF6FF;  /* アクセント薄背景 */
--color-accent-border:     #BFDBFE;  /* アクセント薄ボーダー */

/* セクションアイコン背景 */
--color-icon-purpose-bg:  #DBEAFE;  /* 処理目的 */
--color-icon-purpose-fg:  #2563EB;
--color-icon-input-bg:    #EDE9FE;  /* 入力パラメータ */
--color-icon-input-fg:    #7C3AED;
--color-icon-output-bg:   #D1FAE5;  /* 出力 */
--color-icon-output-fg:   #059669;
--color-icon-algo-bg:     #FEF3C7;  /* アルゴリズム */
--color-icon-algo-fg:     #D97706;

/* ステータスカラー */
--color-status-translating-bg:   #FEF3C7;
--color-status-translating-text: #D97706;
--color-status-done-bg:          #D1FAE5;
--color-status-done-text:        #059669;
--color-status-preparing-bg:     #EDE9FE;
--color-status-preparing-text:   #7C3AED;
--color-status-reviewing-bg:     #DBEAFE;
--color-status-reviewing-text:   #2563EB;

/* エラー */
--color-error-bg:   #FEF2F2;
--color-error-text: #EF4444;
```

### 2. タイポグラフィ

```css
font-family: 'Noto Sans JP', 'Segoe UI', sans-serif;

/* 見出し（ページタイトル） */
font-size: 22px; font-weight: 700; color: var(--color-text-primary);

/* セクションタイトル */
font-size: 18px; font-weight: 700; color: var(--color-text-primary);

/* カードタイトル */
font-size: 15px; font-weight: 700; color: var(--color-text-primary);

/* 本文 */
font-size: 14px; color: var(--color-text-secondary); line-height: 1.6;

/* 補助テキスト・日付 */
font-size: 13px; color: var(--color-text-muted);

/* テーブルヘッダー */
font-size: 11px; font-weight: 700; color: var(--color-text-muted);
text-transform: uppercase; letter-spacing: 0.8px;

/* コード（インライン） */
font-family: 'Courier New', monospace; font-size: 12px;
background: #EFF6FF; color: #1D4ED8;
padding: 1px 5px; border-radius: 4px; border: 1px solid #BFDBFE;

/* コード（関数シグネチャ・ブロック） */
font-family: 'Courier New', monospace; font-size: 13px;
background: #1E293B; color: #E2E8F0;
border-radius: 8px; padding: 10px 16px;
```

### 3. 共通スペーシング・角丸

```css
/* ページ最大幅 */
max-width: 1100px; margin: 0 auto; padding: 32px 24px;

/* カード角丸 */
border-radius: 16px;   /* 通常カード・パネル */
border-radius: 20px;   /* ログインカード */
border-radius: 10px;   /* インプット・ボタン・小カード */
border-radius: 8px;    /* アイコン系・コードブロック */

/* カードシャドウ */
box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 0 0 1px #E2E8F0;

/* ログインカードシャドウ */
box-shadow: 0 20px 60px rgba(59,130,246,0.12), 0 4px 16px rgba(0,0,0,0.06);
```

### 4. Google Fonts の読み込み

以下を HTML の `<head>` に追加してください（まだ読み込まれていない場合のみ）：

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;600;700;800&display=swap" rel="stylesheet">
```

---

## ■ コンポーネント仕様

### 【コンポーネント1】ナビゲーションバー

```
背景:          #FFFFFF
下ボーダー:    1px solid #E2E8F0
高さ:          60px
横パディング:  32px
配置:          fixed（top: 0, left: 0, right: 0）
z-index:       100
box-shadow:    0 1px 3px rgba(0,0,0,0.08)
```

**左側：ブランドエリア**（display: flex, align-items: center, gap: 24px）
- ブランドロゴ部分（display: flex, align-items: center, gap: 10px）
  - ブランドアイコン（32×32px, border-radius: 8px）
    - background: linear-gradient(135deg, #3B82F6, #8B5CF6)
    - 文字「D」（color: #fff, font-size: 14px, font-weight: 800）
  - ブランド名「DocAI」（font-size: 20px, font-weight: 700, color: #3B82F6）
- ページ名（font-size: 15px, color: #64748B, font-weight: 500, 画面に応じて変更）
  - ログイン画面: 「ログイン」
  - タスク一覧画面: 「タスク一覧」
  - タスク詳細画面: 「タスク詳細」

**右側：ユーザーエリア**（ログイン後のみ表示、display: flex, align-items: center, gap: 16px）
- ユーザーバッジ（padding: 6px 12px, border-radius: 24px, background: #F1F5F9）
  - ユーザーアバター（28×28px, 円形, background: linear-gradient(135deg, #3B82F6, #8B5CF6), color: #fff）
    - ユーザー名の頭文字1文字
  - ユーザー名（font-size: 14px, color: #374151, font-weight: 500）
- ログアウトボタン（32×32px, border-radius: 8px, color: #94A3B8, ホバー: background: #FEF2F2, color: #EF4444）

---

### 【コンポーネント2】プライマリボタン

```css
background:    linear-gradient(135deg, #3B82F6, #6366F1);
color:         #FFFFFF;
border:        none;
border-radius: 10px;
padding:       12px 24px;  /* 通常サイズ */
font-size:     14px;
font-weight:   600;
box-shadow:    0 4px 12px rgba(59,130,246,0.25);
cursor:        pointer;
transition:    all 0.2s;

/* ホバー */
transform:    translateY(-1px);
box-shadow:   0 6px 20px rgba(59,130,246,0.4);
```

全幅バージョン（ログインボタン）: `width: 100%; padding: 14px; font-size: 15px;`

---

### 【コンポーネント3】セカンダリボタン

```css
background:    #FFFFFF;
border:        1.5px solid #E2E8F0;
border-radius: 10px;
padding:       12px 20px;
font-size:     14px;
font-weight:   600;
color:         #374151;
cursor:        pointer;
transition:    all 0.2s;

/* ホバー */
background:    #F8FAFC;
border-color:  #CBD5E1;
```

---

### 【コンポーネント4】フォームインプット

```css
background:    #F8FAFC;
border:        1.5px solid #E2E8F0;
border-radius: 10px;
padding:       12px 16px;
font-size:     14px;
color:         #1E293B;
outline:       none;
width:         100%;
transition:    all 0.2s;

/* フォーカス */
border-color:  #3B82F6;
background:    #FFFFFF;
box-shadow:    0 0 0 3px rgba(59,130,246,0.1);

/* プレースホルダー */
color: #CBD5E1;
```

---

### 【コンポーネント5】ステータスバッジ

```css
/* 共通 */
display:       inline-flex;
align-items:   center;
gap:           5px;
padding:       4px 10px;
border-radius: 20px;
font-size:     12px;
font-weight:   600;

/* ドット（疑似要素） */
content: '';
width: 6px; height: 6px; border-radius: 50%;
```

| ステータス | 表示文字 | background | color | ドット色 | アニメーション |
|-----------|---------|------------|-------|---------|---------------|
| 翻訳中 | 翻訳中 | #FEF3C7 | #D97706 | #D97706 | pulse（点滅）|
| 翻訳済 | 翻訳済 | #D1FAE5 | #059669 | #059669 | なし |
| 準備中 | 準備中 | #EDE9FE | #7C3AED | #7C3AED | pulse（点滅）|
| 審査中 | 審査中 | #DBEAFE | #2563EB | #2563EB | なし |

```css
/* pulseアニメーション */
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.3; }
}
animation: pulse 1.5s infinite;
```

---

### 【コンポーネント6】カード（共通）

```css
background:    #FFFFFF;
border-radius: 16px;
box-shadow:    0 1px 3px rgba(0,0,0,0.08), 0 0 0 1px #E2E8F0;
overflow:      hidden;
```

---

## ■ 画面別実装仕様

### 【画面1】ログイン画面

**ページ背景：**
```css
min-height: calc(100vh - 60px);
display: flex; align-items: center; justify-content: center;
background: linear-gradient(135deg, #EFF6FF 0%, #F5F3FF 100%);
padding: 40px 16px;
```

**ログインカード：**
```css
background: #FFFFFF;
border-radius: 20px;
padding: 48px 40px;
max-width: 420px; width: 100%;
box-shadow: 0 20px 60px rgba(59,130,246,0.12), 0 4px 16px rgba(0,0,0,0.06);
```

**カード内ヘッダー（text-align: center）：**
- アプリアイコン（56×56px, border-radius: 14px, background: linear-gradient(135deg, #3B82F6, #8B5CF6), margin: 0 auto 16px）
  - 文字「D」（color: #fff, font-size: 22px, font-weight: 900）
- タイトル「DocAI へようこそ」（font-size: 24px, font-weight: 700, color: #1E293B, margin-bottom: 4px）
- サブタイトル「Pythonコードを自然言語に翻訳するAIツール」（font-size: 14px, color: #94A3B8）
- margin-bottom: 36px

**フォーム：**
- form-group（margin-bottom: 20px）
  - ラベル（font-size: 13px, font-weight: 600, color: #374151, display: block, margin-bottom: 6px）
  - インプット（コンポーネント4）
- メールアドレスフィールド
- パスワードフィールド
- ログインボタン（コンポーネント2 全幅版, margin-top: 8px）

---

### 【画面2】タスク一覧画面

**ページ全体：**
```css
background: #F8FAFC;
padding-top: 60px;  /* ナビバー分 */
```

**コンテンツエリア：**
```css
max-width: 1100px; margin: 0 auto; padding: 32px 24px;
```

**新規タスク作成カード：**
- コンポーネント6, padding: 28px 32px, margin-bottom: 32px
- タイトル「新しいレビューを開始」（font-size: 16px, font-weight: 700, margin-bottom: 4px）
- ヒントテキスト（font-size: 13px, color: #94A3B8, margin-bottom: 16px）
- 入力行（display: flex, gap: 12px）
  - タスク名入力（flex: 1, コンポーネント4）
  - 「▶ レビューを開始する」ボタン（コンポーネント2, white-space: nowrap）

**セクションタイトル「過去のレビュー」：**
```css
font-size: 18px; font-weight: 700; color: #1E293B;
margin-bottom: 16px;
display: flex; align-items: center; gap: 8px;

/* 左端縦線（疑似要素） */
content: '';
width: 4px; height: 20px;
background: linear-gradient(180deg, #3B82F6, #8B5CF6);
border-radius: 2px;
```

**タスク一覧テーブルカード：**
- background: #fff, border-radius: 16px, overflow: hidden
- box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 0 0 1px #E2E8F0

```css
/* テーブル全体 */
width: 100%; border-collapse: collapse;

/* thead */
background: #F8FAFC;

/* th */
padding: 14px 20px;
font-size: 12px; font-weight: 700; color: #64748B;
text-transform: uppercase; letter-spacing: 0.5px;
border-bottom: 1px solid #E2E8F0;

/* td */
padding: 16px 20px;
font-size: 14px;
border-bottom: 1px solid #F1F5F9;

/* tbody tr */
cursor: pointer; transition: background 0.15s;
ホバー: background: #F8FAFC;
```

| 列名 | 内容 | スタイル |
|------|------|---------|
| タスク名 | タスク名テキスト | font-weight: 500, color: #1E293B |
| ステータス | ステータスバッジ（コンポーネント5） | — |
| 最終更新日時 | 日付文字列 | color: #94A3B8, font-size: 13px |

---

### 【画面3】タスク詳細画面（翻訳結果表示）

> **この画面は 3カラムレイアウト** です。以下の仕様に従い既存の詳細ページを全面的に置き換えてください。

#### 3-1. ページ構造

```css
/* ページ全体 */
body: background: #F8FAFC;
.page { padding-top: 60px; height: 100vh; display: flex; flex-direction: column; }

/* コンテンツエリア */
.page-content {
  max-width: 1300px; width: 100%; margin: 0 auto;
  padding: 24px 24px 16px;
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
}
```

#### 3-2. ページヘッダー

```css
display: flex; align-items: center; gap: 16px;
margin-bottom: 20px; flex-shrink: 0;
```

- 戻る矢印「←」（font-size: 20px, color: #94A3B8, cursor: pointer, ホバー: color: #374151）
- タイトル部
  - タスク名（font-size: 22px, font-weight: 700, color: #1E293B）
  - ステータスバッジ（コンポーネント5, margin-top: 5px）

#### 3-3. 3カラムグリッド

```css
.three-col {
  display: grid;
  grid-template-columns: 230px 1fr 260px;
  gap: 20px;
  flex: 1;
  overflow: hidden;
  min-height: 0;
}
```

---

#### 3-4. 左パネル（インポート / 関数タブ）

```css
.left-panel {
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 0 0 1px #E2E8F0;
  overflow: hidden;
  display: flex; flex-direction: column; height: 100%;
}
```

**タブ行（パネル上部）：**

```css
/* パネルヘッダー */
padding: 14px 14px 12px; border-bottom: 1px solid #E2E8F0; flex-shrink: 0;

/* タブ行 */
display: flex; gap: 4px;

/* タブボタン共通 */
flex: 1; padding: 7px 4px; border: none;
background: #F1F5F9; border-radius: 8px;
font-size: 12px; font-weight: 700; color: #64748B;
cursor: pointer; transition: all 0.2s;

/* アクティブタブ */
background: linear-gradient(135deg, #3B82F6, #6366F1); color: #fff;

/* 非アクティブホバー */
background: #E2E8F0;
```

⚠️ **タブ順序と初期状態：**
- **1枚目（左）：「インポート」タブ → デフォルトでアクティブ**
- **2枚目（右）：「関数」タブ → 初期は非アクティブ**

---

**インポートタブ（デフォルト表示）：**

```css
.import-list-body {
  overflow-y: auto; padding: 8px; flex: 1; min-height: 0;
}

.import-mini-item {
  padding: 10px 12px; border-radius: 8px; margin-bottom: 6px;
  background: #F8FAFC; border: 1px solid #E2E8F0;
  transition: border-color 0.15s;
}
.import-mini-item:hover { border-color: #BFDBFE; }

/* モジュール名 */
.import-mini-name {
  font-family: 'Courier New', monospace; font-size: 11px; font-weight: 700;
  color: #1D4ED8; margin-bottom: 4px;
}

/* 説明文 */
.import-mini-desc { font-size: 11px; color: #64748B; line-height: 1.5; }
```

インポートデータはバックエンドから取得した値をそのまま表示してください。
各インポートアイテムには「モジュール名」と「説明文」の2要素を持たせてください。

---

**関数タブ（非アクティブ時は非表示）：**

```css
.func-list-body {
  overflow-y: auto; padding: 8px; flex: 1; min-height: 0;
}

.func-list-item {
  padding: 10px 12px; border-radius: 8px; cursor: pointer;
  transition: all 0.15s; margin-bottom: 3px;
  border: 1.5px solid transparent;
}
.func-list-item:hover  { background: #F0F7FF; }
.func-list-item.active { background: #EFF6FF; border-color: #BFDBFE; }

/* 関数名 */
.func-item-name {
  font-family: 'Courier New', monospace; font-size: 12px; font-weight: 700;
  margin-bottom: 3px; color: #2563EB;
}
.func-list-item.active .func-item-name { color: #1D4ED8; }

/* 処理目的（サマリー） */
.func-item-purpose {
  font-size: 11px; color: #94A3B8; line-height: 1.4;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.func-list-item.active .func-item-purpose { color: #64748B; }
```

関数リストはバックエンドから取得した翻訳結果データを元に動的に生成してください。
各リストアイテムをクリックすると中央パネルに対応する関数の詳細が表示されます。

---

#### 3-5. 中央パネル（関数詳細）

```css
.detail-panel {
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 0 0 1px #E2E8F0;
  overflow: hidden;
  display: flex; flex-direction: column; height: 100%;
}
```

---

**【状態A】未選択時（空状態）：**

インポートタブが表示されているとき、または関数が未選択のときに表示します。

```css
.detail-empty {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 12px;
  color: #94A3B8; padding: 40px;
}
.detail-empty-icon { font-size: 40px; opacity: 0.5; }
.detail-empty-text {
  font-size: 14px; font-weight: 500; text-align: center; line-height: 1.6;
}
```

表示テキスト：
```
⚙️
左の「関数」タブから
確認したい関数を選択してください
```

---

**【状態B】関数選択後：**

##### ① 関数シグネチャヘッダー

⚠️ **◀▶ ナビゲーション矢印は設置しないでください。**

```css
.detail-panel-header {
  padding: 16px 22px; border-bottom: 1px solid #E2E8F0;
  background: #FAFBFC; flex-shrink: 0;
}

/* シグネチャ（ダークコードブロック） */
.detail-func-sig {
  font-family: 'Courier New', monospace; font-size: 13px;
  background: #1E293B; color: #E2E8F0;
  padding: 10px 16px; border-radius: 8px; line-height: 1.6;
  word-break: break-all;
}
/* シンタックスカラー */
.detail-func-sig .fn  { color: #7DD3FC; font-weight: 700; }  /* 関数名 */
.detail-func-sig .arg { color: #FDE68A; }                     /* 引数 */
.detail-func-sig .ret { color: #86EFAC; }                     /* 戻り値型 */
```

##### ② 詳細ボディ

```css
.detail-panel-body {
  padding: 22px; overflow-y: auto; flex: 1; min-height: 0;
}
```

**セクション共通スタイル：**
```css
.detail-section { margin-bottom: 22px; }
.detail-section:last-child { margin-bottom: 0; }

.detail-section-title {
  font-size: 11px; font-weight: 700; color: #94A3B8;
  text-transform: uppercase; letter-spacing: 0.8px;
  margin-bottom: 10px; padding-bottom: 8px;
  border-bottom: 1px solid #F1F5F9;
  display: flex; align-items: center; gap: 6px;
}

/* セクションアイコン */
.section-icon {
  width: 18px; height: 18px; border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  font-size: 10px; font-weight: 700; flex-shrink: 0;
}
.icon-purpose { background: #DBEAFE; color: #2563EB; }  /* 目 */
.icon-input   { background: #EDE9FE; color: #7C3AED; }  /* 入 */
.icon-output  { background: #D1FAE5; color: #059669; }  /* 出 */
.icon-algo    { background: #FEF3C7; color: #D97706; }  /* 手 */
```

---

**⚠️ 重要：4セクションは常に表示してください。データが存在しない場合もセクション自体を非表示にせず、「該当なし」を示すプレースホルダーを表示してください。**

---

**セクション①：処理目的**

```css
/* 通常テキスト */
.purpose-text {
  font-size: 14px; color: #374151; line-height: 1.8;
  background: #F8FAFC; border-left: 3px solid #3B82F6;
  padding: 12px 16px; border-radius: 0 8px 8px 0;
}
```

データなし時：
```html
<div class="no-item-text">処理目的の情報はありません</div>
```

---

**セクション②：入力パラメータ**

```css
/* パラメータテーブル */
.param-table {
  width: 100%; border-collapse: collapse; font-size: 13px;
  border-radius: 8px; overflow: hidden; border: 1px solid #E2E8F0;
}
.param-table th {
  padding: 8px 14px; text-align: left;
  font-size: 11px; font-weight: 700; color: #94A3B8;
  text-transform: uppercase; letter-spacing: 0.5px;
  border-bottom: 1px solid #E2E8F0; background: #F8FAFC;
}
.param-table td {
  padding: 11px 14px; border-bottom: 1px solid #F1F5F9;
  vertical-align: top; line-height: 1.5;
}
.param-table tr:last-child td { border-bottom: none; }

/* 列スタイル */
.param-name { font-family: 'Courier New', monospace; font-size: 12px; color: #7C3AED; font-weight: 700; white-space: nowrap; }
.param-type { font-family: 'Courier New', monospace; font-size: 11px; color: #64748B; }
.param-desc { font-size: 12px; color: #475569; }
/* 説明中のコード */
.param-desc code {
  font-family: 'Courier New', monospace;
  background: #EFF6FF; color: #1D4ED8;
  padding: 1px 5px; border-radius: 4px; font-size: 11px; border: 1px solid #BFDBFE;
}
```

テーブルヘッダー列：`引数名 | 型 | 説明`

データなし時：
```html
<div class="no-item-text">入力パラメータはありません</div>
```

---

**セクション③：出力**

テーブルヘッダー列：`型 | 説明`

戻り値なし（`None`・戻り値のない関数）の場合：
```html
<div class="no-item-text">戻り値はありません</div>
```

---

**セクション④：アルゴリズム（処理ステップ）**

```css
.step-list { list-style: none; }
.step-item {
  display: flex; gap: 12px; align-items: flex-start;
  padding: 10px 0; border-bottom: 1px solid #F8FAFC;
}
.step-item:last-child { border-bottom: none; }

.step-badge {
  width: 24px; height: 24px; border-radius: 50%;
  background: linear-gradient(135deg, #3B82F6, #6366F1);
  color: #fff; font-size: 11px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; margin-top: 1px;
}

.step-text { font-size: 13px; color: #374151; line-height: 1.7; flex: 1; }
.step-text code {
  font-family: 'Courier New', monospace;
  background: #EFF6FF; color: #1D4ED8;
  padding: 1px 6px; border-radius: 4px; font-size: 12px; border: 1px solid #BFDBFE;
}
```

データなし時：
```html
<div class="no-item-text">アルゴリズムの情報はありません</div>
```

---

**「該当なし」プレースホルダー共通スタイル：**

```css
.no-item-text {
  font-size: 13px; color: #CBD5E1; font-style: italic;
  padding: 10px 14px; background: #F8FAFC; border-radius: 8px;
  border: 1px dashed #E2E8F0; text-align: center;
}
```

---

#### 3-6. 右パネル（アップロードファイル一覧）

⚠️ **「一覧に戻る」ボタンは配置しないでください。**

```css
.right-panel { display: flex; flex-direction: column; gap: 16px; height: 100%; }

/* サイドカード共通 */
.side-card {
  background: #fff; border-radius: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 0 0 1px #E2E8F0;
  overflow: hidden;
}
.side-card-header {
  padding: 14px 18px; border-bottom: 1px solid #E2E8F0;
  font-size: 14px; font-weight: 700; color: #1E293B;
  display: flex; align-items: center; gap: 8px;
}
.side-card-body { padding: 12px 14px; }
```

**ファイル一覧：**

```css
/* フォルダパス表示 */
.file-folder {
  font-size: 11px; color: #94A3B8; margin-bottom: 8px;
  font-family: 'Courier New', monospace;
}

/* ファイルアイテム */
.file-item {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 12px; border-radius: 8px;
  background: #F8FAFC; border: 1px solid #E2E8F0;
  margin-bottom: 8px; cursor: pointer; transition: all 0.2s;
}
.file-item:last-child { margin-bottom: 0; }
.file-item:hover { background: #EFF6FF; border-color: #BFDBFE; }

/* 拡張子バッジ */
.file-ext {
  font-family: 'Courier New', monospace; font-size: 10px; font-weight: 700;
  background: #3B82F6; color: #fff; padding: 2px 5px; border-radius: 3px;
}

/* ファイル名 */
.file-name { font-size: 13px; color: #1E293B; font-weight: 500; }
```

カードヘッダー表示内容：`📁 アップロード一覧`
ファイルリストはバックエンドから取得したアップロードファイル情報を元に動的に生成してください。

---

#### 3-7. タブ切り替えの JavaScript ロジック

タブ切り替えおよび関数選択の基本的な動作：

```javascript
// 左パネルタブ切り替え
function switchLeftTab(tab) {
  const isFuncs   = tab === 'funcs';
  const isImports = tab === 'imports';

  // タブボタンのactive切り替え
  document.getElementById('tabBtnFuncs').classList.toggle('active', isFuncs);
  document.getElementById('tabBtnImports').classList.toggle('active', isImports);

  // コンテンツ表示切り替え
  document.getElementById('tab-funcs').style.display   = isFuncs   ? '' : 'none';
  document.getElementById('tab-imports').style.display = isImports ? '' : 'none';

  // インポートタブに戻った場合は中央パネルを空状態に戻す
  if (isImports) {
    showEmptyDetail();
  }
}

// 関数選択
function selectFunc(funcId) {
  // リストアイテムのactive更新（既存の実装に合わせて調整）
  document.querySelectorAll('.func-list-item').forEach(el => {
    el.classList.toggle('active', el.dataset.funcId === String(funcId));
  });

  // 中央パネルに対応する関数の詳細を表示
  showFuncDetail(funcId);
}

// 中央パネル: 空状態表示
function showEmptyDetail() {
  document.getElementById('detail-empty').style.display = '';
  document.getElementById('detail-func-header').style.display = 'none';
  document.getElementById('detail-panel-body').style.display = 'none';
}

// 中央パネル: 関数詳細表示
function showFuncDetail(funcId) {
  document.getElementById('detail-empty').style.display = 'none';
  document.getElementById('detail-func-header').style.display = '';
  document.getElementById('detail-panel-body').style.display = '';
  // シグネチャ・各セクションの内容更新は既存のデータ取得ロジックに合わせて実装
}
```

> **注意：** 上記は動作の参考例です。既存の状態管理（React state / Vue reactive など）を使用している場合は、そのパターンに合わせて実装してください。

---

## ■ 実装上の注意事項

### 必須事項
1. **既存のバックエンドロジック・APIコールは絶対に変更しない**
2. **既存のHTMLのid属性・name属性・data属性は変更しない**（JavaScriptや他処理が依存している可能性があるため）
3. **フォームのaction・method属性は変更しない**
4. **既存のJavaScriptイベントハンドラは変更しない**
5. デザイン適用後、各画面で既存の機能（フォーム送信・データ表示・画面遷移）が正常に動作することを確認してください

### CSS追加の方針
- 既存のスタイルを上書きする場合は、既存ファイルを確認した上で競合しないよう注意
- 既存のCSSクラス名は極力変更せず、スタイルの値のみを更新
- 競合が避けられない場合は、その旨を報告した上で対応方針を提示

### フレームワーク別対応
- **Tailwind CSS**：上記の値に対応するユーティリティクラスに読み替えてください。カスタム値は `tailwind.config.js` に追加してください
- **CSS Modules / styled-components**：各コンポーネントファイル内のスタイルを対応するコンポーネント仕様に沿って書き換えてください
- **Jinja2 / Django Templates**：グローバルCSSファイルを新規または更新し、テンプレートのクラス名を適宜追加・変更してください

---

## ■ 作業の推奨順序

1. プロジェクト構成の確認（事前確認事項を実行）
2. デザイン変数・共通スタイルの定義・更新
3. 共通コンポーネントの修正（ナビバー → ボタン → インプット → バッジ → カード）
4. ログイン画面の修正
5. タスク一覧画面の修正
6. **タスク詳細画面の修正（3カラムレイアウトへの全面移行）**
   - 3カラムグリッドの構築
   - 左パネル（インポートタブをデフォルト、関数タブを2番目に配置）
   - 中央パネル（空状態 + 関数詳細の切り替え、◀▶矢印なし、ページネーションなし）
   - 右パネル（ファイル一覧のみ、「一覧に戻る」ボタンなし）
7. 各画面のブラウザ表示確認

---

## ■ 変更禁止リスト

- すべてのAPIエンドポイントURL
- フォームのバリデーションロジック
- 認証・セッション管理のコード
- エラーハンドリングのロジック
- データフェッチ・状態管理のコード
- テスト用コード・設定ファイル
- `.env` ファイル・環境変数
- バックエンド側のすべてのファイル（`*.py`, `*.go`, `*.java` など）
- 既存HTMLのid / name / data属性
- フォームの action / method 属性
- 既存のJavaScriptイベントハンドラ

---

以上の仕様に基づき、リデザインを実施してください。
不明点や判断が必要な分岐点があれば、作業を止めて確認を求めてください。
