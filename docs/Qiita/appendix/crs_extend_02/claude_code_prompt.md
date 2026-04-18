# DocAI UI/UXリデザイン実施プロンプト（Claude Code用）

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
   - ログイン画面
   - タスク一覧画面
   - タスク詳細画面
   上記3画面に対応するテンプレート・コンポーネントファイルをすべて列挙してください。

3. **共通コンポーネントの特定**
   - ナビゲーションバー（ヘッダー）
   - ステータスバッジ
   - ボタン
   - フォームインプット
   - カード
   上記が独立したコンポーネントとして実装されているか確認し、そのファイルパスを列挙してください。

構成を把握した上で、以下の仕様に従いリデザインを実施してください。

---

## ■ デザインシステム定義

### 1. カラーパレット

以下の色をプロジェクトの管理方式に合わせて定義してください。
CSS変数が使える場合は `:root` に定義し、Tailwindの場合は `tailwind.config.js` の `extend.colors` に追加してください。

```
/* 背景・サーフェス */
--color-bg:           #F8FAFC   /* ページ背景 */
--color-surface:      #FFFFFF   /* カード・パネル背景 */
--color-surface-sub:  #F1F5F9   /* サブ背景（テーブルヘッダー、入力フィールドデフォルト） */

/* ボーダー */
--color-border:       #E2E8F0   /* 通常ボーダー */
--color-border-sub:   #F1F5F9   /* 薄いボーダー（テーブル行区切り） */

/* テキスト */
--color-text-primary:   #1E293B  /* 見出し・重要テキスト */
--color-text-secondary: #374151  /* 通常テキスト */
--color-text-muted:     #64748B  /* 補助テキスト・ラベル */
--color-text-placeholder: #CBD5E1 /* プレースホルダー */

/* アクセントカラー（Blue/Indigo） */
--color-accent:          #3B82F6
--color-accent-dark:     #2563EB
--color-accent-gradient: linear-gradient(135deg, #3B82F6, #6366F1)
--color-accent-bg:       #EFF6FF  /* アクセント薄背景 */
--color-accent-border:   #BFDBFE  /* アクセント薄ボーダー */

/* ステータスカラー */
/* 翻訳中（Warning: Amber） */
--color-status-translating-bg:   #FEF3C7
--color-status-translating-text: #D97706
/* 翻訳済（Success: Emerald） */
--color-status-done-bg:   #D1FAE5
--color-status-done-text: #059669
/* 準備中（Purple） */
--color-status-preparing-bg:   #EDE9FE
--color-status-preparing-text: #7C3AED
/* 審査中（Blue） */
--color-status-reviewing-bg:   #DBEAFE
--color-status-reviewing-text: #2563EB

/* エラー */
--color-error-bg:   #FEF2F2
--color-error-text: #EF4444
```

### 2. タイポグラフィ

```
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
font-size: 12px; font-weight: 700; color: var(--color-text-muted);
text-transform: uppercase; letter-spacing: 0.5px;

/* コードスニペット */
font-family: 'Courier New', monospace; font-size: 12px;
```

### 3. 共通スペーシング・角丸

```
/* ページ最大幅 */
max-width: 1100px; margin: 0 auto; padding: 32px 24px;

/* カード角丸 */
border-radius: 16px;  /* 通常カード */
border-radius: 20px;  /* ログインカード */
border-radius: 10px;  /* インプット・ボタン・小カード */
border-radius: 8px;   /* アイコン系 */

/* カードシャドウ */
box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 0 0 1px #E2E8F0;

/* ログインカードシャドウ */
box-shadow: 0 20px 60px rgba(59,130,246,0.12), 0 4px 16px rgba(0,0,0,0.06);
```

---

## ■ コンポーネント仕様

### 【コンポーネント1】ナビゲーションバー

```
背景:          #FFFFFF
下ボーダー:    1px solid #E2E8F0
高さ:          60px
横パディング:  32px
配置:          fixed（top: 0）
z-index:       100
box-shadow:    0 1px 3px rgba(0,0,0,0.08)
```

**左側：ブランドエリア**
- ブランドアイコン（32×32px, border-radius: 8px）
  - background: linear-gradient(135deg, #3B82F6, #8B5CF6)
  - 文字「D」（color: #fff, font-size: 14px, font-weight: 800）
- ブランド名「DocAI」（font-size: 20px, font-weight: 700, color: #3B82F6, letter-spacing: -0.5px）
- ページ名（font-size: 15px, color: #64748B, font-weight: 500）
  - ログイン画面では「ログイン」
  - タスク一覧画面では「タスク一覧」
  - タスク詳細画面では「タスク詳細」

**右側：ユーザーエリア（ログイン後のみ表示）**
- ユーザーバッジ（padding: 6px 12px, border-radius: 24px, background: #F1F5F9）
  - ユーザーアバター（28×28px, 円形, background: linear-gradient(135deg, #3B82F6, #8B5CF6)）
    - ユーザー名の頭文字1文字（color: #fff）
  - ユーザー名（font-size: 14px, color: #374151, font-weight: 500）
  - ホバー時: background: #E2E8F0
- ログアウトボタン（32×32px, border-radius: 8px）
  - アイコンのみ（電源アイコンなど）
  - デフォルト: color: #94A3B8, background: transparent
  - ホバー時: background: #FEF2F2, color: #EF4444

---

### 【コンポーネント2】プライマリボタン

```
background:    linear-gradient(135deg, #3B82F6, #6366F1)
color:         #FFFFFF
border:        none
border-radius: 10px
padding:       12px 24px（通常）/ 14px（全幅ログインボタン）
font-size:     14px（通常）/ 15px（ログインボタン）
font-weight:   600
box-shadow:    0 4px 12px rgba(59,130,246,0.25)
transition:    all 0.2s

ホバー時:
  transform:    translateY(-1px)
  box-shadow:   0 6px 20px rgba(59,130,246,0.4)
```

### 【コンポーネント3】セカンダリボタン（「一覧に戻る」など）

```
background:    #FFFFFF
border:        1.5px solid #E2E8F0
border-radius: 10px
padding:       12px 20px
font-size:     14px
font-weight:   600
color:         #374151
transition:    all 0.2s

ホバー時:
  background: #F8FAFC
  border-color: #CBD5E1
```

### 【コンポーネント4】フォームインプット

```
background:    #F8FAFC
border:        1.5px solid #E2E8F0
border-radius: 10px
padding:       12px 16px
font-size:     14px
color:         #1E293B
outline:       none
transition:    all 0.2s

フォーカス時:
  border-color: #3B82F6
  background:   #FFFFFF
  box-shadow:   0 0 0 3px rgba(59,130,246,0.1)

プレースホルダー:
  color: #CBD5E1
```

### 【コンポーネント5】ステータスバッジ

共通スタイル：
```
display:       inline-flex
align-items:   center
gap:           5px
padding:       4px 10px
border-radius: 20px
font-size:     12px
font-weight:   600
```

バッジ左側のドット（疑似要素 or 子要素）：
```
width: 6px; height: 6px; border-radius: 50%;
```

各ステータスごとのスタイル：

| ステータス | 表示文字 | background | color | ドット色 | ドットアニメーション |
|-----------|---------|------------|-------|---------|------------------|
| 翻訳中 | 翻訳中 | #FEF3C7 | #D97706 | #D97706 | pulse（点滅） |
| 翻訳済 | 翻訳済 | #D1FAE5 | #059669 | #059669 | なし |
| 準備中 | 準備中 | #EDE9FE | #7C3AED | #7C3AED | pulse（点滅） |
| 審査中 | 審査中 | #DBEAFE | #2563EB | #2563EB | なし |

pulseアニメーション：
```css
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.3; }
}
animation: pulse 1.5s infinite;
```

### 【コンポーネント6】カード

```
background:    #FFFFFF
border-radius: 16px
box-shadow:    0 1px 3px rgba(0,0,0,0.08), 0 0 0 1px #E2E8F0
overflow:      hidden
```

カードヘッダー（カード内上部）：
```
padding:        20px 24px
border-bottom:  1px solid #E2E8F0
display:        flex
align-items:    center
gap:            10px
```
- アイコン（絵文字 or SVGアイコン）
- タイトル（font-size: 15px, font-weight: 700, color: #1E293B）

カードボディ：
```
padding: 24px
```

---

## ■ 画面別実装仕様

### 【画面1】ログイン画面

**背景：**
```
min-height: calc(100vh - 60px)
display: flex; align-items: center; justify-content: center
background: linear-gradient(135deg, #EFF6FF 0%, #F5F3FF 100%)
padding: 40px 16px
```

**ログインカード（中央配置）：**
```
background:    #FFFFFF
border-radius: 20px
padding:       48px 40px
max-width:     420px; width: 100%
box-shadow:    0 20px 60px rgba(59,130,246,0.12), 0 4px 16px rgba(0,0,0,0.06)
```

**カード内ヘッダー（テキスト中央揃え）：**
- アプリアイコン
  - 56×56px, border-radius: 14px
  - background: linear-gradient(135deg, #3B82F6, #8B5CF6)
  - 文字「D」（color: #fff, font-size: 22px, font-weight: 900）
  - margin: 0 auto 16px
- タイトル「DocAI へようこそ」（font-size: 24px, font-weight: 700, color: #1E293B, margin-bottom: 4px）
- サブタイトル「Pythonコードを自然言語に翻訳するAIツール」（font-size: 14px, color: #94A3B8）
- ヘッダー全体の margin-bottom: 36px

**フォーム：**
- ラベル + インプットの form-group（margin-bottom: 20px）
  - ラベル（font-size: 13px, font-weight: 600, color: #374151, margin-bottom: 6px）
  - インプット（コンポーネント4の仕様通り）
- メールアドレスフィールド
- パスワードフィールド
- ログインボタン（コンポーネント2の全幅版、margin-top: 8px）

---

### 【画面2】タスク一覧画面

**ページ全体：**
```
background: #F8FAFC
padding-top: 60px（ナビバー分）
```

**コンテンツエリア：**
```
max-width: 1100px; margin: 0 auto; padding: 32px 24px
```

**新規タスク作成カード：**
- カードコンポーネント6の仕様（border-radius: 16px, shadow）
- padding: 28px 32px
- margin-bottom: 32px

カード内：
- タイトル「新しいレビューを開始」（font-size: 16px, font-weight: 700, color: #1E293B, margin-bottom: 4px）
- ヒントテキスト「タスク名を入力して、レビューを開始してください」（font-size: 13px, color: #94A3B8, margin-bottom: 16px）
- 入力行（display: flex, gap: 12px）
  - タスク名入力フィールド（flex: 1, コンポーネント4の仕様）
  - 「▶ レビューを開始する」ボタン（コンポーネント2の仕様、white-space: nowrap）

**セクションタイトル「過去のレビュー」：**
```
font-size: 18px; font-weight: 700; color: #1E293B
margin-bottom: 16px
display: flex; align-items: center; gap: 8px

左端の縦線装飾（疑似要素）:
  content: ''
  width: 4px; height: 20px
  background: linear-gradient(180deg, #3B82F6, #8B5CF6)
  border-radius: 2px
```

**タスク一覧テーブルカード：**
- background: #fff, border-radius: 16px, overflow: hidden
- box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 0 0 1px #E2E8F0

テーブルスタイル：
```
width: 100%; border-collapse: collapse

thead:
  background: #F8FAFC

th:
  padding: 14px 20px
  text-align: left
  font-size: 12px; font-weight: 700; color: #64748B
  text-transform: uppercase; letter-spacing: 0.5px
  border-bottom: 1px solid #E2E8F0

td:
  padding: 16px 20px
  font-size: 14px
  border-bottom: 1px solid #F1F5F9

tbody tr（最終行）:
  border-bottom: none

tbody tr:
  cursor: pointer
  transition: background 0.15s
  ホバー時: background: #F8FAFC
```

テーブル列定義：

| 列名（th表示） | 内容 | スタイル |
|--------------|------|---------|
| タスク名 ↕ | タスク名テキスト | font-weight: 500, color: #1E293B |
| ステータス ↕ | ステータスバッジコンポーネント | — |
| 最終更新日時 ↕ | 日付文字列 | color: #94A3B8, font-size: 13px |

---

### 【画面3】タスク詳細画面

**ページヘッダー（コンテンツエリア上部）：**
```
display: flex; align-items: center; gap: 16px; margin-bottom: 24px
```
- 戻るボタン（「←」, font-size: 20px, color: #94A3B8, cursor: pointer, ホバー時: color: #374151）
- タスク名（font-size: 22px, font-weight: 700, color: #1E293B）
- ステータスバッジ（コンポーネント5の仕様、font-size: 11px）

**2カラムレイアウト：**
```
display: grid
grid-template-columns: 1fr 340px
gap: 24px
```

**左カラム「コード解析結果」カード：**
- コンポーネント6の仕様
- カードヘッダー：📋アイコン + 「コード解析結果」タイトル
- カードボディ（padding: 24px, max-height: 600px, overflow-y: auto）

カードボディ内構造：

**セクション: 定数・インポート**
```
.analysis-section-title:
  font-size: 13px; font-weight: 700; color: #64748B
  text-transform: uppercase; letter-spacing: 0.5px
  margin-bottom: 12px; padding-bottom: 8px
  border-bottom: 1px solid #F1F5F9
```

各インポート・定数ごとに以下を繰り返す：
```
.token-chip（コード名表示）:
  display: inline-block
  background: #EFF6FF; color: #1D4ED8
  border: 1px solid #BFDBFE
  padding: 3px 10px; border-radius: 6px
  font-size: 12px; font-family: monospace; font-weight: 600
  margin-bottom: 8px

.token-desc（説明テキスト）:
  font-size: 13px; color: #475569; line-height: 1.7; margin-bottom: 16px
  strong タグ: color: #1E293B
```

**セクション: 関数**
各関数ごとに `.func-card` で囲む：
```
.func-card:
  background: #F8FAFC; border-radius: 12px; padding: 16px
  border: 1px solid #E2E8F0; margin-bottom: 16px

.func-signature（シグネチャ表示）:
  font-family: monospace; font-size: 12px
  background: #1E293B; color: #7DD3FC
  padding: 8px 12px; border-radius: 8px; margin-bottom: 12px

.func-label:
  font-size: 12px; font-weight: 700; color: #64748B; margin-bottom: 4px

.func-text:
  font-size: 13px; color: #475569; line-height: 1.6
```

**右カラム（縦積み）：**
- 「アップロードファイル」カード
  - コンポーネント6の仕様
  - カードヘッダー：📁アイコン + 「アップロードファイル」タイトル
  - カードボディ（padding: 16px）
    - ファイルアイテム（各ファイルごとに）：
      ```
      display: flex; align-items: center; gap: 10px
      padding: 12px 16px; border-radius: 10px
      background: #F8FAFC; border: 1px solid #E2E8F0
      margin-bottom: 8px; cursor: pointer; transition: all 0.2s
      ホバー時: background: #EFF6FF, border-color: #BFDBFE

      ファイルアイコン: font-size: 18px（🐍など拡張子に応じた絵文字）
      ファイル名: font-size: 13px, font-weight: 500, color: #1E293B
      ```
- 「← 一覧に戻る」ボタン（コンポーネント3の仕様、margin-top: 16px）

---

## ■ 実装上の注意事項

### 必須事項
1. **既存のバックエンドロジック・APIコールは絶対に変更しない**
2. **既存のHTMLのid属性・name属性・data属性は変更しない**（JavaScriptや他処理が依存している可能性があるため）
3. **フォームのaction・method属性は変更しない**
4. **既存のJavaScriptイベントハンドラは変更しない**
5. デザイン適用後、各画面で既存の機能（フォーム送信・データ表示・画面遷移）が正常に動作することを確認してください

### CSSの追加方法
- 既存のスタイルを上書きする場合は、既存のスタイルシートを確認した上で、競合しないよう注意してください
- 既存のCSSクラス名は極力変更せず、スタイルの値のみを更新してください
- もし既存のCSSクラスとの競合が避けられない場合は、その旨を報告した上で対応方針を提示してください

### フレームワーク別の対応
- **Tailwind CSS** を使用している場合：上記の値に対応するユーティリティクラスに読み替えてください。カスタム値は `tailwind.config.js` に追加してください
- **CSS Modules / styled-components** を使用している場合：各コンポーネントファイル内のスタイルを対応するコンポーネント仕様に沿って書き換えてください
- **Jinja2 / Django Templates** を使用している場合：グローバルCSSファイルを新規または更新し、テンプレートのクラス名を適宜追加・変更してください

### Google Fonts の追加
以下をHTMLの `<head>` に追加してください（まだ読み込まれていない場合）：
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;600;700;800&display=swap" rel="stylesheet">
```

---

## ■ 作業の進め方（推奨順序）

1. プロジェクト構成の確認（上記「事前確認事項」を実行）
2. デザイン変数・共通スタイルの定義・更新
3. 共通コンポーネントの修正（ナビバー → ボタン → インプット → バッジ → カード の順）
4. ログイン画面の修正
5. タスク一覧画面の修正
6. タスク詳細画面の修正
7. 各画面のブラウザ表示確認（レイアウト崩れ・スタイル競合がないか）

---

## ■ 変更しないでほしい要素（明示的な除外リスト）

- すべてのAPIエンドポイントURL
- フォームのバリデーションロジック
- 認証・セッション管理のコード
- エラーハンドリングのロジック
- データフェッチ・状態管理のコード
- テスト用コード・設定ファイル
- `.env` ファイル・環境変数
- バックエンド側のすべてのファイル（`*.py`, `*.go`, `*.java` など）

---

以上の仕様に基づき、リデザインを実施してください。
不明点や判断が必要な分岐点があれば、作業を止めて確認を求めてください。
