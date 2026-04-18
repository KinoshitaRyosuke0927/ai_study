# 翻訳結果表示エリア リデザイン プロンプト（Claude Code用）

## ■ 変更スコープ（重要）

**このプロンプトが変更するのは「翻訳結果の表示エリアのみ」です。**
以下は一切変更しないでください：
- ナビゲーションバー
- ページヘッダー（タスク名・ステータスバッジ・編集ボタン・削除ボタン）
- バックエンドのAPIコール・データ取得ロジック
- 認証・セッション管理
- その他の画面（ログイン・タスク一覧）

---

## ■ 現在の状態（変更前）

### 画面構成
```
┌─────────────────────────────────────────────────────────────┐
│  ← すーぱーねね〜ち   ● 翻訳済   [編集] [削除]            │
├──────────────────────────────────────────┬──────────────────┤
│                                          │ 📁 アップロード  │
│  ┌──────────────────────────────────┐  │    一覧          │
│  │ 定数・インポート                 │ ▲│                  │
│  │  インポートモジュール一覧         │  │  services/       │
│  │  pandas: テキスト…               │  │  task_detail_    │
│  │  azure.core…: テキスト…          │  │  service.py      │
│  │  ──────────────────────────────  │  │                  │
│  │ 関数                             │  │                  │
│  │  create_new_task(…) [コード]     │  │                  │
│  │  基礎目的                        │  │                  │
│  │  新たなタスクを作成し…           │  │                  │
│  │  入力                            │  │                  │
│  │  task_name [コード] : タスク名称  │  │                  │
│  │  出力                            │  │                  │
│  │  TaskDetailResponse [コード]     │  │                  │
│  │  アルゴリズム                    │  │                  │
│  │  …（以下スクロール）             │ ▼│                  │
│  └──────────────────────────────────┘  │                  │
└──────────────────────────────────────────┴──────────────────┘
```

### 現在の問題点
1. **単一スクロール** — 全関数・全インポートが1つの縦長カードに収まっており、大量スクロールが必要
2. **関数間の境界が不明確** — 関数ごとの区切りが視覚的に弱い
3. **ナビゲーション手段がない** — 特定の関数に素早くアクセスできない
4. **インポート一覧が密集** — 小さいテキストの羅列で視認性が低い
5. **セクション見出しが平坦** — 「基礎目的」「入力」「出力」「アルゴリズム」が単なる太字テキスト
6. **コードブロックのコントラストが低い** — 薄青枠スタイルで関数シグネチャが目立たない

---

## ■ 変更後の目標レイアウト

```
┌─────────────────────────────────────────────────────────────┐
│  ← すーぱーねね〜ち   ● 翻訳済   [編集] [削除]            │  ← 変更なし
├──────────────┬──────────────────────────┬───────────────────┤
│[インポート][関数]│                          │ 📁 アップロード  │
│──────────────│  ⚙️                        │    一覧          │
│ pandas       │  左の「関数」タブから      │                  │
│  説明テキスト│  確認したい関数を          │  services/       │
│              │  選択してください          │  task_detail_    │
│ ResourceNot  │          ↓ 関数選択後      │  service.py      │
│  説明テキスト│ ┌──────────────────────┐  │                  │
│              │ │def create_new_task(…)│  │                  │
│ azure_ai /   │ └──────────────────────┘  │                  │
│  説明テキスト│  🔵目 処理目的             │                  │
│              │  新たなタスクを作成し…    │                  │
│ …            │  🟣入 入力パラメータ       │                  │
│              │  [テーブル]               │                  │
│              │  🟢出 出力                │                  │
│              │  [テーブル]               │                  │
│              │  🟡手 アルゴリズム        │                  │
│              │  1 → 2 → 3…（バッジ）    │                  │
└──────────────┴──────────────────────────┴───────────────────┘
    左パネル         中央パネル（詳細）           右パネル
    230px固定        flex: 1（残り幅）            260px固定
```

---

## ■ 事前確認事項

作業を開始する前に以下を確認し、結果を報告してください。

1. **翻訳結果表示エリアのファイル特定**
   - 翻訳結果（markdownテキスト）を表示しているコンポーネント/テンプレートファイルを特定してください
   - そのファイルの該当箇所（クラス名・id・要素の種類）を示してください

2. **markdownデータの取得方法確認**
   - markdownテキストはどの変数/propsに格納されているか
   - 文字列としてそのまま保持されているか、すでにHTMLにパース済みか

3. **markdownの構造確認**
   - 実際のmarkdownデータの冒頭100行程度を確認し、以下の見出し構造が存在するか確認してください：
     ```
     ## 定数・インポート
     ### インポートモジュール一覧
     ## 関数
     ### [関数名]
     #### 基礎目的 または 処理目的
     #### 入力 または 入力パラメータ
     #### 出力
     #### アルゴリズム
     ```

4. **現在の表示コンテナの特定**
   - 翻訳結果を囲む最外側のHTML要素（クラス名・id）を教えてください
   - その要素の親要素も含めたレイアウト上の位置を確認してください

---

## ■ 実装仕様

### STEP 1：レイアウトの変更

現在の「翻訳結果を表示する単一カード」を、以下の3カラム構造に置き換えてください。

**現在の構造（概略）：**
```html
<!-- 変更前：翻訳結果が入った大きなカード -->
<div class="[翻訳結果コンテナのクラス]">
  <!-- markdownがレンダリングされたHTML -->
</div>
```

**変更後の構造：**
```html
<!-- 変更後：3カラムパネル -->
<div class="docai-result-panel">

  <!-- ① 左パネル（インポート/関数タブ） -->
  <div class="docai-left-panel">
    <div class="docai-tab-header">
      <button class="docai-tab-btn docai-tab-active"
              id="docaiTabImports"
              onclick="docaiSwitchTab('imports')">インポート</button>
      <button class="docai-tab-btn"
              id="docaiTabFuncs"
              onclick="docaiSwitchTab('funcs')">関数</button>
    </div>

    <!-- インポート一覧（デフォルト表示） -->
    <div id="docaiImportList" class="docai-list-body">
      <!-- JavaScriptで動的生成 -->
    </div>

    <!-- 関数一覧（初期は非表示） -->
    <div id="docaiFuncList" class="docai-list-body" style="display:none;">
      <!-- JavaScriptで動的生成 -->
    </div>
  </div>

  <!-- ② 中央パネル（関数詳細） -->
  <div class="docai-center-panel">
    <!-- 未選択時の空状態 -->
    <div id="docaiEmptyState" class="docai-empty-state">
      <div class="docai-empty-icon">⚙️</div>
      <div class="docai-empty-text">
        左の「関数」タブから<br>確認したい関数を選択してください
      </div>
    </div>

    <!-- 関数選択後の詳細（初期は非表示） -->
    <div id="docaiFuncDetail" style="display:none; height:100%; display:flex; flex-direction:column;">
      <!-- シグネチャヘッダー -->
      <div class="docai-sig-header">
        <div id="docaiFuncSig" class="docai-func-sig"></div>
      </div>
      <!-- 詳細ボディ -->
      <div class="docai-detail-body">
        <!-- 処理目的 -->
        <div class="docai-section">
          <div class="docai-section-title">
            <span class="docai-icon docai-icon-purpose">目</span>処理目的
          </div>
          <div id="docaiPurpose" class="docai-purpose-text"></div>
        </div>
        <!-- 入力パラメータ -->
        <div class="docai-section">
          <div class="docai-section-title">
            <span class="docai-icon docai-icon-input">入</span>入力パラメータ
          </div>
          <div id="docaiInput"></div>
        </div>
        <!-- 出力 -->
        <div class="docai-section">
          <div class="docai-section-title">
            <span class="docai-icon docai-icon-output">出</span>出力
          </div>
          <div id="docaiOutput"></div>
        </div>
        <!-- アルゴリズム -->
        <div class="docai-section">
          <div class="docai-section-title">
            <span class="docai-icon docai-icon-algo">手</span>アルゴリズム
          </div>
          <ol id="docaiAlgo" class="docai-step-list"></ol>
        </div>
      </div>
    </div>
  </div>

</div>
```

> **⚠️ id・クラス名の衝突防止：**
> 上記の新規要素にはすべて `docai-` プレフィックスを付けています。
> 既存のid・クラスとの衝突がないことを確認した上で使用してください。
> 衝突が見つかった場合はプレフィックスを変更してください。

---

### STEP 2：CSSの追加

既存のスタイルシートの**末尾**に以下を追記してください（上書き・削除は不要）。

```css
/* =============================================
   DocAI 翻訳結果パネル リデザイン
   ============================================= */

/* 3カラムグリッド */
.docai-result-panel {
  display: grid;
  grid-template-columns: 230px 1fr;
  gap: 16px;
  height: calc(100vh - 180px); /* ナビバー + ページヘッダー分を除いた高さ */
  min-height: 500px;
  overflow: hidden;
}

/* ===== 左パネル ===== */
.docai-left-panel {
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 0 0 1px #E2E8F0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  height: 100%;
}

/* タブヘッダー */
.docai-tab-header {
  padding: 12px 12px 10px;
  border-bottom: 1px solid #E2E8F0;
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

/* タブボタン */
.docai-tab-btn {
  flex: 1;
  padding: 7px 4px;
  border: none;
  background: #F1F5F9;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 700;
  color: #64748B;
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;
}
.docai-tab-btn.docai-tab-active {
  background: linear-gradient(135deg, #3B82F6, #6366F1);
  color: #fff;
}
.docai-tab-btn:not(.docai-tab-active):hover {
  background: #E2E8F0;
}

/* リスト共通ボディ */
.docai-list-body {
  overflow-y: auto;
  padding: 8px;
  flex: 1;
  min-height: 0;
}

/* インポートアイテム */
.docai-import-item {
  padding: 10px 12px;
  border-radius: 8px;
  margin-bottom: 6px;
  background: #F8FAFC;
  border: 1px solid #E2E8F0;
  transition: border-color 0.15s;
}
.docai-import-item:hover {
  border-color: #BFDBFE;
}
.docai-import-name {
  font-family: 'Courier New', monospace;
  font-size: 11px;
  font-weight: 700;
  color: #1D4ED8;
  margin-bottom: 4px;
  word-break: break-all;
}
.docai-import-desc {
  font-size: 11px;
  color: #64748B;
  line-height: 1.5;
}

/* 関数リストアイテム */
.docai-func-item {
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
  margin-bottom: 3px;
  border: 1.5px solid transparent;
}
.docai-func-item:hover {
  background: #F0F7FF;
}
.docai-func-item.docai-func-active {
  background: #EFF6FF;
  border-color: #BFDBFE;
}
.docai-func-item-name {
  font-family: 'Courier New', monospace;
  font-size: 12px;
  font-weight: 700;
  color: #2563EB;
  margin-bottom: 3px;
}
.docai-func-item.docai-func-active .docai-func-item-name {
  color: #1D4ED8;
}
.docai-func-item-purpose {
  font-size: 11px;
  color: #94A3B8;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.docai-func-item.docai-func-active .docai-func-item-purpose {
  color: #64748B;
}

/* ===== 中央パネル ===== */
.docai-center-panel {
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 0 0 1px #E2E8F0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  height: 100%;
}

/* 空状態 */
.docai-empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: #94A3B8;
  padding: 40px;
}
.docai-empty-icon {
  font-size: 40px;
  opacity: 0.5;
}
.docai-empty-text {
  font-size: 14px;
  font-weight: 500;
  text-align: center;
  line-height: 1.6;
}

/* 関数シグネチャヘッダー */
.docai-sig-header {
  padding: 16px 20px;
  border-bottom: 1px solid #E2E8F0;
  background: #FAFBFC;
  flex-shrink: 0;
}
.docai-func-sig {
  font-family: 'Courier New', monospace;
  font-size: 13px;
  background: #1E293B;
  color: #E2E8F0;
  padding: 10px 16px;
  border-radius: 8px;
  line-height: 1.6;
  word-break: break-all;
}
.docai-func-sig .docai-fn  { color: #7DD3FC; font-weight: 700; }
.docai-func-sig .docai-arg { color: #FDE68A; }
.docai-func-sig .docai-ret { color: #86EFAC; }

/* 詳細ボディ */
.docai-detail-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}

/* セクション */
.docai-section {
  margin-bottom: 20px;
}
.docai-section:last-child {
  margin-bottom: 0;
}
.docai-section-title {
  font-size: 11px;
  font-weight: 700;
  color: #94A3B8;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid #F1F5F9;
  display: flex;
  align-items: center;
  gap: 6px;
}

/* セクションアイコン */
.docai-icon {
  width: 18px;
  height: 18px;
  border-radius: 4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 700;
  flex-shrink: 0;
}
.docai-icon-purpose { background: #DBEAFE; color: #2563EB; }
.docai-icon-input   { background: #EDE9FE; color: #7C3AED; }
.docai-icon-output  { background: #D1FAE5; color: #059669; }
.docai-icon-algo    { background: #FEF3C7; color: #D97706; }

/* 処理目的テキスト */
.docai-purpose-text {
  font-size: 14px;
  color: #374151;
  line-height: 1.8;
  background: #F8FAFC;
  border-left: 3px solid #3B82F6;
  padding: 12px 16px;
  border-radius: 0 8px 8px 0;
}

/* 「該当なし」プレースホルダー */
.docai-no-item {
  font-size: 13px;
  color: #CBD5E1;
  font-style: italic;
  padding: 10px 14px;
  background: #F8FAFC;
  border-radius: 8px;
  border: 1px dashed #E2E8F0;
  text-align: center;
}

/* パラメータテーブル */
.docai-param-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #E2E8F0;
}
.docai-param-table th {
  padding: 8px 14px;
  text-align: left;
  font-size: 11px;
  font-weight: 700;
  color: #94A3B8;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 1px solid #E2E8F0;
  background: #F8FAFC;
}
.docai-param-table td {
  padding: 10px 14px;
  border-bottom: 1px solid #F1F5F9;
  vertical-align: top;
  line-height: 1.5;
  font-size: 13px;
  color: #374151;
}
.docai-param-table tr:last-child td {
  border-bottom: none;
}
.docai-param-name {
  font-family: 'Courier New', monospace;
  font-size: 12px;
  color: #7C3AED;
  font-weight: 700;
  white-space: nowrap;
}
.docai-param-type {
  font-family: 'Courier New', monospace;
  font-size: 11px;
  color: #64748B;
}

/* アルゴリズムステップ */
.docai-step-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.docai-step-item {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 10px 0;
  border-bottom: 1px solid #F8FAFC;
}
.docai-step-item:last-child {
  border-bottom: none;
}
.docai-step-badge {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: linear-gradient(135deg, #3B82F6, #6366F1);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 1px;
}
.docai-step-text {
  font-size: 13px;
  color: #374151;
  line-height: 1.7;
  flex: 1;
}
/* ステップ内インラインコード */
.docai-step-text code,
.docai-param-table td code {
  font-family: 'Courier New', monospace;
  background: #EFF6FF;
  color: #1D4ED8;
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 11px;
  border: 1px solid #BFDBFE;
}
```

> **`height: calc(100vh - 180px)` の調整：**
> ナビバー・ページヘッダーの実際の高さに合わせて値を調整してください。
> 実装後にレイアウトが崩れる場合は、ブラウザの DevTools でヘッダー部分の高さを計測し適宜変更してください。

---

### STEP 3：JavaScriptの追加（markdownパーサー + UI制御）

#### 【重要】markdownデータの取得方法について

既存コードでmarkdownテキストを取得している変数・処理を確認し、以下の `MARKDOWN_TEXT` 部分を実際の変数に置き換えてください。

- React/Vue の場合：props または state から markdownテキストを取得
- Jinja2/Django の場合：テンプレート変数として埋め込まれた文字列を取得
- 取得方法が不明な場合は、現在の表示要素の `innerHTML` または `textContent` からパースしてください

```javascript
/* =============================================
   DocAI 翻訳結果パネル — パーサー & UI制御
   ============================================= */
(function() {
  'use strict';

  /* --------------------------------------------------
     設定：実際の実装に合わせて変更してください
     -------------------------------------------------- */

  /**
   * markdownテキストを返す関数。
   * 実際の実装に応じて以下のいずれかに変更してください：
   *
   * [Jinja2/Django の場合]
   *   return `{{ translation_result | safe }}`;
   *
   * [React の場合]
   *   // コンポーネント外からアクセスできる変数を使用
   *   return window.__DOCAI_MARKDOWN__ || '';
   *
   * [既存の表示要素のテキストを流用する場合]
   *   const el = document.querySelector('.[既存の表示エリアのクラス名]');
   *   return el ? el.textContent : '';
   */
  function getMarkdownText() {
    // ↓ この行を実際の取得方法に変更してください
    return window.__DOCAI_MARKDOWN__ || '';
  }

  /* --------------------------------------------------
     markdownパーサー
     -------------------------------------------------- */

  /**
   * markdownテキストを構造化データに変換する
   * @param {string} md
   * @returns {{ imports: Array<{name:string, desc:string}>, functions: Array<FuncData> }}
   *
   * FuncData = {
   *   name: string,          // 関数名
   *   signature: string,     // 関数シグネチャ（コードブロック内容）
   *   purpose: string,       // 処理目的テキスト
   *   inputs: Array<{name:string, type:string, desc:string}>,
   *   outputs: Array<{type:string, desc:string}>,
   *   steps: string[]        // アルゴリズムステップ
   * }
   */
  function parseMarkdown(md) {
    const lines = md.split('\n');
    const result = { imports: [], functions: [] };

    let i = 0;
    let currentFunc = null;
    let currentSection = null;
    let buffer = [];

    // バッファを文字列化するヘルパー
    function flushBuffer() {
      return buffer.splice(0).join('\n').trim();
    }

    while (i < lines.length) {
      const line = lines[i];
      const trimmed = line.trim();

      /* ── ## 定数・インポート ── */
      if (/^##\s+(定数[・・])?インポート/.test(trimmed)) {
        currentSection = 'imports';
        i++; continue;
      }

      /* ── ## 関数 ── */
      if (/^##\s+関数/.test(trimmed) && !currentSection?.startsWith('func-')) {
        currentSection = 'functions';
        i++; continue;
      }

      /* ── ### [関数名] ── */
      if (/^###\s+/.test(trimmed) && currentSection === 'functions') {
        // 前の関数をコミット
        if (currentFunc) {
          finalizeFunc(currentFunc, currentSection, buffer);
          result.functions.push(currentFunc);
        }
        const funcName = trimmed.replace(/^###\s+/, '').replace(/`/g, '').trim();
        currentFunc = { name: funcName, signature: '', purpose: '', inputs: [], outputs: [], steps: [] };
        currentSection = 'func-name';
        buffer = [];
        i++; continue;
      }

      /* ── #### 基礎目的 / 処理目的 ── */
      if (/^####\s+(基礎目的|処理目的)/.test(trimmed) && currentFunc) {
        finalizeFunc(currentFunc, currentSection, buffer);
        currentSection = 'func-purpose';
        buffer = [];
        i++; continue;
      }

      /* ── #### 入力 / 入力パラメータ ── */
      if (/^####\s+(入力|入力パラメータ)/.test(trimmed) && currentFunc) {
        finalizeFunc(currentFunc, currentSection, buffer);
        currentSection = 'func-input';
        buffer = [];
        i++; continue;
      }

      /* ── #### 出力 ── */
      if (/^####\s+出力/.test(trimmed) && currentFunc) {
        finalizeFunc(currentFunc, currentSection, buffer);
        currentSection = 'func-output';
        buffer = [];
        i++; continue;
      }

      /* ── #### アルゴリズム ── */
      if (/^####\s+アルゴリズム/.test(trimmed) && currentFunc) {
        finalizeFunc(currentFunc, currentSection, buffer);
        currentSection = 'func-algo';
        buffer = [];
        i++; continue;
      }

      /* ── コードブロック（関数シグネチャ）── */
      if (trimmed.startsWith('```') && currentFunc && currentSection === 'func-name') {
        i++;
        const codeLines = [];
        while (i < lines.length && !lines[i].trim().startsWith('```')) {
          codeLines.push(lines[i]);
          i++;
        }
        currentFunc.signature = codeLines.join('\n').trim();
        i++; continue;
      }

      /* ── インポートセクションの各行 ── */
      if (currentSection === 'imports' && trimmed && !trimmed.startsWith('#')) {
        // 「- `name`: desc」 または 「`name`: desc」 または 「**name**: desc」形式
        const importMatch = trimmed.match(/^[-*]?\s*[`\*]{1,2}([^`*:]+)[`\*]{1,2}\s*[:/]\s*(.*)/) ||
                            trimmed.match(/^[-*]?\s*([^\s:：]+)\s*[:：]\s*(.*)/);
        if (importMatch) {
          result.imports.push({
            name: importMatch[1].trim(),
            desc: importMatch[2].trim()
          });
        }
        i++; continue;
      }

      /* ── その他のセクションのバッファ蓄積 ── */
      if (currentSection && currentSection.startsWith('func-')) {
        buffer.push(line);
      }

      i++;
    }

    // 最後の関数をコミット
    if (currentFunc) {
      finalizeFunc(currentFunc, currentSection, buffer);
      result.functions.push(currentFunc);
    }

    return result;
  }

  /**
   * バッファの内容を対象セクションに反映する
   */
  function finalizeFunc(func, section, buffer) {
    const text = buffer.join('\n').trim();
    if (!text) return;

    if (section === 'func-purpose') {
      func.purpose = text.replace(/^[-*]\s*/gm, '').trim();

    } else if (section === 'func-input') {
      // 「- `name` (type): desc」「`name`: desc」形式をパース
      text.split('\n').forEach(line => {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#')) return;

        const match =
          // パターン1: `name` (type): desc
          trimmed.match(/[`\*]{1,2}([^`*]+)[`\*]{1,2}\s*[\(（]([^\)）]+)[\)）]\s*[:：]\s*(.*)/) ||
          // パターン2: `name`: desc (type情報なし)
          trimmed.match(/[`\*]{1,2}([^`*]+)[`\*]{1,2}\s*[:：]\s*(.*)/) ||
          // パターン3: - name: desc
          trimmed.match(/^[-*]\s*([^\s:：]+)\s*[:：]\s*(.*)/);

        if (match) {
          if (match.length === 4) {
            func.inputs.push({ name: match[1].trim(), type: match[2].trim(), desc: match[3].trim() });
          } else {
            func.inputs.push({ name: match[1].trim(), type: '', desc: match[2].trim() });
          }
        }
      });

    } else if (section === 'func-output') {
      text.split('\n').forEach(line => {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#')) return;
        const match =
          trimmed.match(/[`\*]{1,2}([^`*]+)[`\*]{1,2}\s*[:：]\s*(.*)/) ||
          trimmed.match(/^[-*]\s*([^\s:]+)\s*[:：]\s*(.*)/);
        if (match) {
          func.outputs.push({ type: match[1].trim(), desc: match[2].trim() });
        } else if (trimmed.replace(/^[-*]\s*/, '')) {
          func.outputs.push({ type: '', desc: trimmed.replace(/^[-*]\s*/, '') });
        }
      });

    } else if (section === 'func-algo') {
      text.split('\n').forEach(line => {
        const trimmed = line.replace(/^[\d]+[.、．]\s*/, '').replace(/^[-*]\s*/, '').trim();
        if (trimmed && !trimmed.startsWith('#')) {
          func.steps.push(trimmed);
        }
      });
    }
  }

  /* --------------------------------------------------
     HTML生成ヘルパー
     -------------------------------------------------- */

  /** インラインコードをspanタグに変換 */
  function escapeAndCode(text) {
    const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return escaped.replace(/`([^`]+)`/g, '<code>$1</code>');
  }

  /** 関数シグネチャのシンタックスカラーリング */
  function colorSig(sig) {
    return sig
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/def\s+(\w+)/, 'def <span class="docai-fn">$1</span>')
      .replace(/->?\s*([A-Za-z_][\w\[\], ]+)$/, '→ <span class="docai-ret">$1</span>')
      .replace(/(\w+)\s*:/g, '<span class="docai-arg">$1</span>:');
  }

  /* --------------------------------------------------
     UI構築
     -------------------------------------------------- */

  let parsedData = null;

  /** インポート一覧をDOMに描画 */
  function renderImports(imports) {
    const container = document.getElementById('docaiImportList');
    if (!container) return;
    if (!imports || imports.length === 0) {
      container.innerHTML = '<div class="docai-no-item">インポート情報はありません</div>';
      return;
    }
    container.innerHTML = imports.map(item => `
      <div class="docai-import-item">
        <div class="docai-import-name">${escapeAndCode('`' + item.name + '`').replace(/^<code>|<\/code>$/g, '').replace(/`/g, '')}</div>
        <div class="docai-import-desc">${escapeAndCode(item.desc)}</div>
      </div>
    `).join('');
  }

  /** 関数一覧をDOMに描画 */
  function renderFuncList(functions) {
    const container = document.getElementById('docaiFuncList');
    if (!container) return;
    if (!functions || functions.length === 0) {
      container.innerHTML = '<div class="docai-no-item">関数情報はありません</div>';
      return;
    }
    container.innerHTML = functions.map((fn, idx) => `
      <div class="docai-func-item" data-idx="${idx}" onclick="docaiSelectFunc(${idx})">
        <div class="docai-func-item-name">${fn.name.replace(/&/g,'&amp;').replace(/</g,'&lt;')}</div>
        <div class="docai-func-item-purpose">${(fn.purpose || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').substring(0, 40)}</div>
      </div>
    `).join('');
  }

  /** パラメータテーブルを生成 */
  function buildParamTable(rows, cols) {
    if (!rows || rows.length === 0) {
      return '<div class="docai-no-item">' +
        (cols.length === 3 ? '入力パラメータはありません' : '出力情報はありません') +
        '</div>';
    }
    const thead = `<tr>${cols.map(c => `<th>${c}</th>`).join('')}</tr>`;
    const tbody = rows.map(row => {
      if (cols.length === 3) {
        return `<tr>
          <td><span class="docai-param-name">${escapeAndCode(row.name)}</span></td>
          <td><span class="docai-param-type">${escapeAndCode(row.type || '—')}</span></td>
          <td>${escapeAndCode(row.desc)}</td>
        </tr>`;
      } else {
        return `<tr>
          <td><span class="docai-param-name">${escapeAndCode(row.type || '—')}</span></td>
          <td>${escapeAndCode(row.desc)}</td>
        </tr>`;
      }
    }).join('');
    return `<table class="docai-param-table"><thead>${thead}</thead><tbody>${tbody}</tbody></table>`;
  }

  /** アルゴリズムステップリストを生成 */
  function buildStepList(steps) {
    if (!steps || steps.length === 0) {
      return '<div class="docai-no-item">アルゴリズムの情報はありません</div>';
    }
    return steps.map((step, i) => `
      <li class="docai-step-item">
        <span class="docai-step-badge">${i + 1}</span>
        <span class="docai-step-text">${escapeAndCode(step)}</span>
      </li>
    `).join('');
  }

  /* --------------------------------------------------
     グローバル関数（onclick から呼び出す）
     -------------------------------------------------- */

  /** タブ切り替え */
  window.docaiSwitchTab = function(tab) {
    const isFuncs   = tab === 'funcs';
    const isImports = tab === 'imports';

    document.getElementById('docaiTabFuncs').classList.toggle('docai-tab-active', isFuncs);
    document.getElementById('docaiTabImports').classList.toggle('docai-tab-active', isImports);
    document.getElementById('docaiFuncList').style.display   = isFuncs   ? '' : 'none';
    document.getElementById('docaiImportList').style.display = isImports ? '' : 'none';

    // インポートタブに切り替えたら中央パネルを空状態に戻す
    if (isImports) {
      document.getElementById('docaiEmptyState').style.display  = '';
      document.getElementById('docaiFuncDetail').style.display  = 'none';
    }
  };

  /** 関数選択 */
  window.docaiSelectFunc = function(idx) {
    if (!parsedData) return;
    const fn = parsedData.functions[idx];
    if (!fn) return;

    // リストのactive更新
    document.querySelectorAll('.docai-func-item').forEach((el, i) => {
      el.classList.toggle('docai-func-active', i === idx);
    });

    // シグネチャ
    const sig = fn.signature || fn.name;
    document.getElementById('docaiFuncSig').innerHTML = colorSig(sig);

    // 処理目的
    const purposeEl = document.getElementById('docaiPurpose');
    purposeEl.className = fn.purpose ? 'docai-purpose-text' : 'docai-no-item';
    purposeEl.innerHTML = fn.purpose
      ? escapeAndCode(fn.purpose)
      : '処理目的の情報はありません';

    // 入力パラメータ
    document.getElementById('docaiInput').innerHTML =
      buildParamTable(fn.inputs, ['引数名', '型', '説明']);

    // 出力
    // 戻り値なし判定：シグネチャに戻り値がなく、outputs も空の場合
    const hasReturn = fn.outputs && fn.outputs.length > 0;
    const sigHasReturn = /->/.test(fn.signature || '');
    if (!hasReturn && !sigHasReturn) {
      document.getElementById('docaiOutput').innerHTML =
        '<div class="docai-no-item">戻り値はありません</div>';
    } else {
      document.getElementById('docaiOutput').innerHTML =
        buildParamTable(fn.outputs, ['型', '説明']);
    }

    // アルゴリズム
    const algoEl = document.getElementById('docaiAlgo');
    algoEl.innerHTML = buildStepList(fn.steps);

    // 空状態 → 詳細表示
    document.getElementById('docaiEmptyState').style.display = 'none';
    document.getElementById('docaiFuncDetail').style.display = '';
  };

  /* --------------------------------------------------
     初期化（DOMContentLoaded 後に実行）
     -------------------------------------------------- */

  function init() {
    const md = getMarkdownText();
    if (!md) {
      console.warn('[DocAI] markdownテキストが取得できませんでした。getMarkdownText() の実装を確認してください。');
      return;
    }
    parsedData = parseMarkdown(md);
    renderImports(parsedData.imports);
    renderFuncList(parsedData.functions);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
```

---

### STEP 4：markdownデータの受け渡し設定

#### フレームワーク別の対応

**Jinja2 / Django Templates の場合：**
```html
<!-- テンプレート内のscriptタグで変数を渡す -->
<script>
  window.__DOCAI_MARKDOWN__ = {{ translation_markdown | tojson | safe }};
</script>
```

**React の場合：**
```jsx
// コンポーネント内で useEffect を使用
useEffect(() => {
  window.__DOCAI_MARKDOWN__ = translationResult; // propsまたはstateの変数名に変更
  // 初期化関数を呼び出す（スクリプトが後から読み込まれる場合）
  if (window.docaiSelectFunc) {
    // パーサーの再実行が必要な場合は再マウント処理
  }
}, [translationResult]);
```

**既存の表示要素のテキストを流用する場合（最もシンプルな方法）：**
```javascript
// getMarkdownText() 内を以下に変更
function getMarkdownText() {
  // 既存の翻訳結果表示エリアのセレクタに変更してください
  const el = document.querySelector('.[既存の表示エリアのクラス名]');
  return el ? (el.dataset.markdown || el.textContent) : '';
}
```

> **推奨：** 既存コードでmarkdownテキストが変数として保持されている場合は、
> その変数を `window.__DOCAI_MARKDOWN__` に代入する1行を追加するのが最もシンプルです。
> 既存の表示ロジックを変更する必要はありません。

---

## ■ パーサーの動作確認方法

実装後にブラウザの DevTools コンソールで以下を実行し、パース結果を確認してください。

```javascript
// パース結果の確認
const md = window.__DOCAI_MARKDOWN__;
// 簡易確認：インポート数と関数数
console.log('取得されたmarkdown文字数:', md?.length || 0);
// パース後のデータ確認（グローバルに公開されている場合）
// parsedData の中身を確認してください
```

パース結果が正しくない場合（インポートや関数が0件になる場合）は、
実際のmarkdownの先頭200行程度を共有してください。見出し構造に合わせてパーサーの正規表現を調整します。

---

## ■ 作業完了の確認チェックリスト

- [ ] 翻訳結果表示エリアが3カラム構造（左パネル・中央パネル）に変わっている
- [ ] 左パネルの「インポート」タブがデフォルトでアクティブ（青いグラデーション）になっている
- [ ] 「インポート」タブにインポートモジュールの一覧が表示されている
- [ ] 「関数」タブに関数名の一覧が表示されている
- [ ] 関数をクリックすると中央パネルに詳細が表示される
- [ ] 中央パネルに「処理目的」「入力パラメータ」「出力」「アルゴリズム」が常時表示される
- [ ] データがない場合は「〜はありません」のプレースホルダーが表示される
- [ ] ページヘッダー（タスク名・ステータスバッジ・編集・削除ボタン）は変更されていない
- [ ] 右サイドバーのアップロード一覧は変更されていない
- [ ] 既存のAPIコール・データ取得ロジックは変更されていない

---

## ■ 変更禁止リスト（このプロンプトのスコープ外）

- ナビゲーションバー（全要素）
- ページヘッダー（タスク名・ステータスバッジ・編集アイコン・削除アイコン）
- 右サイドバー（アップロード一覧カード）
- APIエンドポイントURL・データ取得ロジック
- 認証・セッション管理コード
- ログイン画面・タスク一覧画面
- バックエンドファイル（`*.py` 等）
- `.env`・環境変数
- 既存HTMLの id / name / data属性
