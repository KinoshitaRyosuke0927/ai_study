# AIたちが一晩でUIを作り直してくれた話——Genspark × Claude Code でCRSを全面刷新

## はじめに

[前回の記事](./crs_extend_01.md)では、AIS（AIシステム開発事業部）の取り組みとして生まれた **CRS（Code Reading Supporter）** に、プロジェクト全体理解・一気通貫レビュー・テスト自動生成などの機能を追加した様子をお伝えしました。

今回は「機能」ではなく **「見た目」** の話です。

CRSは業務で使うプロダクトではなく、メンバーが自分たちで時間を作り、「何を作るか」から議論して設計・実装してきた学習教材です。機能が動くことへの達成感が先に来るので、見た目はどうしても後回しになりがちです。

でも改めて画面を眺めると——茶色系の背景、薄いグレーのテキスト、どこがクリックできるか分からないテーブル。機能は動いているのに、見た目がついてきていない。せっかく作るなら、最後まで仕上げたい。

そこで今回は **Genspark にデザイン改善案を出してもらい、Claude Code に実装してもらう** という完全AI外注体制で画面の全面刷新に挑戦しました。結論から言うと、ダラダラと配信を見ている間にほぼすべての作業がAIによって完了していました。

---

## 1. まず全体のデザインを刷新する

### AIに問題を分析させる

まず現状のアプリの画面キャプチャ（ログイン・タスク一覧・タスク詳細）をGensparkに貼り付けて、「UI/UX的な観点からデザイン改善案を提案してほしい」とお願いしてみました。

<div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

![Gensparkへのデザイン改善依頼](/docs/Qiita/image/crs_extend_02/image_001.png)
*Gensparkに現状の画面キャプチャを渡して、デザイン改善案の提案を依頼している様子*

</div>

しばらくすると、現在のデザインが抱えている問題点をまとめてくれました。

<div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

![Gensparkが整理した既存デザインの問題点](/docs/Qiita/image/crs_extend_02/image_002.png)
*Gensparkが分析した既存デザインの7つの問題点。カラーコントラスト・情報階層の不明瞭さ・アクセシビリティなど、指摘はかなり的を射ている*

</div>

カラーコントラスト不足・ステータスの識別困難・情報階層の不明瞭さ・アクセシビリティへの配慮なし……言われてみれば確かに全部当たっています。「3つのデザイン案を作りました」とのことで、それぞれ確認してみましょう。

---

### 3つのデザイン案を比較する

#### <a href="../appendix/crs_extend_02/design_a.html" download>デザイン案A</a>

<div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

![デザイン案AのHTML全体像](/docs/Qiita/image/crs_extend_02/image_003.png)
*デザイン案A。落ち着いたカラーパレットとカード型レイアウトを採用した案*

</div>

**画面イメージ**

- ログイン画面
    <div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

    ![案Aのログイン画面](/docs/Qiita/image/crs_extend_02/image_004.png)
    *案Aのログイン画面。シンプルで落ち着いた印象*

    </div>

- タスク一覧画面
    <div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

    ![案Aのタスク一覧画面](/docs/Qiita/image/crs_extend_02/image_005.png)
    *案Aのタスク一覧画面。テーブル行のクリック可能な領域が視覚的に分かりやすくなっている*

    </div>

- タスク詳細画面
    <div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

    ![案Aのタスク詳細画面](/docs/Qiita/image/crs_extend_02/image_006.png)
    *案Aのタスク詳細画面。翻訳結果エリアとサイドバーのコントラストが改善されている*

    </div>

---

#### <a href="../appendix/crs_extend_02/design_b.html" download>デザイン案B</a>

<div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

![デザイン案BのHTML全体像](/docs/Qiita/image/crs_extend_02/image_007.png)
*デザイン案B。ダークアクセントカラーを使ったビジネスライクな案*

</div>

**画面イメージ**

- ログイン画面
    <div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

    ![案Bのログイン画面](/docs/Qiita/image/crs_extend_02/image_008.png)

    </div>

- タスク一覧画面
    <div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

    ![案Bのタスク一覧画面](/docs/Qiita/image/crs_extend_02/image_009.png)

    </div>

- タスク詳細画面
    <div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

    ![案Bのタスク詳細画面](/docs/Qiita/image/crs_extend_02/image_010.png)

    </div>

---

#### <a href="../appendix/crs_extend_02/design_c.html" download>デザイン案C</a>

<div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

![デザイン案CのHTML全体像](/docs/Qiita/image/crs_extend_02/image_011.png)
*デザイン案C。モダンなグラデーションを取り入れた案*

</div>

**画面イメージ**

- ログイン画面
    <div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

    ![案Cのログイン画面](/docs/Qiita/image/crs_extend_02/image_012.png)

    </div>

- タスク一覧画面
    <div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

    ![案Cのタスク一覧画面](/docs/Qiita/image/crs_extend_02/image_013.png)

    </div>

- タスク詳細画面
    <div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

    ![案Cのタスク詳細画面](/docs/Qiita/image/crs_extend_02/image_014.png)

    </div>

---

### プロンプトの作成もAIに任せてClaude Codeで実装

案Aが一番しっくりきたので採用。あとは実装するだけ——ですが、手動でCSSを書き直す気力はないのでClaude Codeに依頼します。その依頼プロンプトの作成も、そのままGensparkに丸投げします。

<div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

![Gensparkへのプロンプト作成依頼](/docs/Qiita/image/crs_extend_02/image_015.png)
*GensparkにClaude Code向けの実装プロンプト作成を依頼している様子*

</div>

快く引き受けてくれました。しばらくすると<a href="../appendix/crs_extend_02/claude_code_prompt.md" download>プロンプト</a>が完成。ご丁寧に使い方のコツまで添えてくれたのでその通りに実行します。

<div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

![Gensparkが生成したプロンプトと使い方のコツ](/docs/Qiita/image/crs_extend_02/image_016.png)
*生成されたプロンプトに加え、効果的な使い方のコツまで添えてくれた*

</div>

しばらくするとClaude Codeによる修正が完了。起動して確認してみます。

<div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

![第1回修正後のタスク詳細画面](/docs/Qiita/image/crs_extend_02/image_017.png)
*Claude Codeによるデザイン適用後のタスク詳細画面。全体のデザインは指定通りに変わったが、翻訳結果の表示エリアがまだ読みにくい*

</div>

全体のトーンは見違えるほど改善されました。ただ、タスク詳細画面で翻訳結果を表示している部分だけがまだ読みにくい。ここはもう一手間かけます。

---

## 2. タスク詳細の表示レイアウトを改善する

### 問題点をあらためて整理してもらう

もう一度Gensparkにタスク詳細画面だけを見てもらい、改善案を提案してもらいます。

<div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

![2回目のデザイン改善依頼](/docs/Qiita/image/crs_extend_02/image_018.png)
*タスク詳細画面のみをターゲットに、2回目のデザイン改善提案を依頼*

</div>

今度も問題点を整理したうえで、3つの改善案を出してくれました。

<div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

![2回目の問題点分析](/docs/Qiita/image/crs_extend_02/image_019.png)
*2回目に指摘された問題点。翻訳結果エリアのレイアウト・情報の区切り方・視認性に関する課題が列挙されている*

</div>

---

#### <a href="../appendix/crs_extend_02/display_a.html" download>デザイン案A</a>

<div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

![表示改善案AのHTML全体像](/docs/Qiita/image/crs_extend_02/image_020.png)
*表示改善の案A。翻訳結果を上下2エリアに分割したレイアウト*

</div>

**画面イメージ**

- 全体
    <div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

    ![表示改善案Aの全体表示](/docs/Qiita/image/crs_extend_02/image_021.png)

    </div>
- 関数一覧
    <div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

    ![表示改善案Aの関数一覧部分](/docs/Qiita/image/crs_extend_02/image_022.png)

    </div>

---

#### <a href="../appendix/crs_extend_02/display_b.html" download>デザイン案B</a>

<div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

![表示改善案BのHTML全体像](/docs/Qiita/image/crs_extend_02/image_023.png)
*表示改善の案B。左にインポート一覧・右に翻訳結果をサイドバー形式で並べたレイアウト*

</div>

**画面イメージ**

- 全体
    <div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

    ![表示改善案Bの全体表示](/docs/Qiita/image/crs_extend_02/image_024.png)

    </div>

- インポート欄
    <div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

    ![表示改善案Bのインポート欄](/docs/Qiita/image/crs_extend_02/image_025.png)

    </div>

---

#### <a href="../appendix/crs_extend_02/display_c.html" download>デザイン案C</a>

<div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

![表示改善案CのHTML全体像](/docs/Qiita/image/crs_extend_02/image_026.png)
*表示改善の案C。タブ切り替え形式で各セクションを切り替えるレイアウト*

</div>

**画面イメージ**

- 全体
    <div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

    ![表示改善案Cの全体表示](/docs/Qiita/image/crs_extend_02/image_027.png)

    </div>

---

### 案Bをベースに詰めていく

サイドバー形式で情報を並べる **案B** のレイアウトが一番しっくりきたので採用。3エリア構成は維持したまま、フォントサイズ・余白・区切り線など細かい部分の調整を追加で依頼します。

<div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

![案Bへの追加調整依頼](/docs/Qiita/image/crs_extend_02/image_028.png)
*案Bをベースに、細かいデザイン調整を追加で指示している様子*

</div>

しばらくすると調整を加味した<a href="../appendix/crs_extend_02/display_b2.html" download>HTML</a>が出力されました。

<div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

![最終調整済みHTMLのプレビュー](/docs/Qiita/image/crs_extend_02/image_029.png)
*Gensparkが出力した最終調整済みHTMLのプレビュー。申し分ない仕上がり*

</div>

申し分ない。改めてClaude Code向けのプロンプトを作成してもらいます。

<div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

![2回目のプロンプト作成依頼](/docs/Qiita/image/crs_extend_02/image_030.png)
*表示改善分の実装を依頼するClaude Code向けプロンプトの作成を依頼*

</div>

---

### AIが記憶を失うと何が起きるか

しばらくして<a href="../appendix/crs_extend_02/claude_code_prompt_v2.md" download>プロンプト</a>が届いたのですが——中身を確認すると、さっき施した大規模なデザイン修正が無かったことにされていました。

原因はこれです。

<div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

![Gensparkの文脈圧縮通知](/docs/Qiita/image/crs_extend_02/image_031.png)
*「パフォーマンス向上のため、以前のチャット履歴は圧縮されました。」——やり取りが圧縮されたことで直前の変更内容を忘れていた*

</div>

会話が長くなったことでチャット履歴が圧縮され、直前の変更内容がまるごと消えていたようです。他の作業と並行して操作していたため、出力内容をよく確認せずに進めてしまったのが原因でした。

詳細な指示と画像を改めて渡して再依頼します。ここで面白いのは、Gensparkが画像を再分析しながら、待ち時間を無駄にしないようにできる作業を自主的に先回りして進めている点です。

<div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

![文脈を補完した再依頼](/docs/Qiita/image/crs_extend_02/image_032.png)
*文脈圧縮で失われた情報を補完しながら、詳細な指示を追加して再依頼*

</div>

<div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

![Gensparkが並行して作業を進めている様子](/docs/Qiita/image/crs_extend_02/image_033.png)

=== 中略 ===

![プロンプト作成完了](/docs/Qiita/image/crs_extend_02/image_034.png)
*Gensparkが画像再分析と並行して先回り作業を進め、最終的にプロンプトを完成させた様子*

</div>

<a href="../appendix/crs_extend_02/prompt_display_only.md" download>プロンプト</a>の作成が完了。改めてClaude Codeに依頼してコードを修正します。

---

### 完成した画面

コードの修正が完了したのでアプリを起動して確認します。

- ログイン画面
    <div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

    ![最終版ログイン画面](/docs/Qiita/image/crs_extend_02/image_035.png)
    *最終版のログイン画面。「DocAI へようこそ」の文言と青系の清潔なデザインに刷新された*

    </div>
- タスク一覧画面
    <div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

    ![最終版タスク一覧画面](/docs/Qiita/image/crs_extend_02/image_036.png)
    *最終版のタスク一覧画面。クリック可能な行が視覚的に明確になった*

    </div>
- タスク詳細画面
  - インポート
    <div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

    ![最終版タスク詳細画面（インポートセクション）](/docs/Qiita/image/crs_extend_02/image_037.png)
    *最終版のタスク詳細画面（インポートセクション）。3エリア構成でサイドバー形式に整理された*

    </div>

  - 関数
    <div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

    ![最終版タスク詳細画面（関数セクション）](/docs/Qiita/image/crs_extend_02/image_038.png)
    *最終版のタスク詳細画面（関数セクション）。関数ごとの翻訳結果が読みやすくレイアウトされている*

    </div>

善哉。ついでに未実装の機能を実装して、他の画面や要素のスタイルも今回のデザインに合わせて修正を依頼。ダラダラと[配信](https://www.youtube.com/watch?v=E2D_YFRHFG8&t=3582s)を見ている間に、ほぼすべての作業をGensparkとClaude Codeが完了していました。

---

## 3. Claude Codeが苦手だったこと

あらゆる実装をこなす印象のClaude Codeですが、今回一点だけ手古摺っていた箇所がありました。右上に表示されるトースト通知のスタイル修正です。

<div style="background: #e9f7ff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; display: inline-block; width: fit-content;">

![トースト通知が表示されているタスク詳細画面](/docs/Qiita/image/crs_extend_02/image_039.png)
*タスク詳細画面右上のトースト通知「最新のタスク情報を反映しました。」。下部に残存表示時間を示すプログレスバーが付いていたが、スタイル修正が難航した*

</div>

元々はトーストの下部に残存表示時間を示すプログレスバーが存在していました。これを他のUIのカラーに合わせて変更しようとしたのですが、何度指示しても意図したスタイルにならず、最終的にプログレスバーは常時表示に変更することで折り合いをつけました。

この修正はCopilotのClaude Sonnet 4.6に依頼し直して、原因の調査と修正を行うことで解決。同じClaudeでも、Claude Codeとは微妙に挙動が違うのが面白い点です。AIにも得手不得手があり、ツールを使い分けることが大切だと改めて実感しました。

---

## まとめ

今回のUI刷新で分かったことをまとめます。

**うまくいったこと**

- Genspark への現状画面の共有 → 問題点の分析 → デザイン案の生成 → プロンプト作成 → Claude Code での実装という流れが、ほぼ人手なしで回せた
- 「AIが作ったデザイン案を人間が選ぶ」という分業が、意思決定の速さと品質を両立させた
- Gensparkが頼んでもいない「プロンプトの使い方のコツ」や「待ち時間中の先回り作業」をやってくれるなど、思っていたより気が利いた

**気をつけたいこと・学んだこと**

- 長い会話では文脈圧縮が発生し、AIが直前の変更内容を忘れることがある。重要な変更内容は要点としてまとめて保持しておくか、新しいチャットとして切り出す方が安全
- 複数のAIをつなぐ場合（Genspark → Claude Code）、引き継ぎ情報を明示的に整備することが重要
- Claude Codeでうまくいかない場合は、別のAIに切り替えると解決することがある。「このAIでダメなら諦め」ではなく、使い分けを意識したい

---

CRSは、日々の業務とは別に自分たちで時間を確保し、テーマを議論して、設計して、手を動かす取り組みの中から生まれたアプリケーションです。完成度よりもプロセスを大事にしながら、少しずつ積み上げています。今後もAISの取り組みをこうして発信していくので、引き続きよろしくお願いします！

最後まで読んでいただきありがとうございました！
