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
</style>

### Code Review Supporter Applicationの拡張2
Gensparkに依頼して画面デザインの改善案を提案してもらった。

<div class="image-section">

![alt text](/image/crs_extend_02/image_001.png)

</div>

暫くすると以下の問題点を教えてくれた。

<div class="image-section">

![alt text](/image/crs_extend_02/image_002.png)

</div>

なるほど。3つのデザイン案ができたと言うので見てみよう。

---

#### <a href="../appendix/crs_extend_02/design_a.html" download>デザイン案A</a>
<div class="image-section">

![alt text](/image/crs_extend_02/image_003.png)

</div>


**画面イメージ**

- ログイン画面
    <div class="image-section">

    ![alt text](/image/crs_extend_02/image_004.png)

    </div>

- タスク一覧画面
    <div class="image-section">

    ![alt text](/image/crs_extend_02/image_005.png)

    </div>

- タスク詳細画面
    <div class="image-section">

    ![alt text](/image/crs_extend_02/image_006.png)

    </div>

---

#### <a href="../appendix/crs_extend_02/design_b.html" download>デザイン案B</a>
<div class="image-section">

![alt text](/image/crs_extend_02/image_007.png)

</div>


**画面イメージ**

- ログイン画面
    <div class="image-section">

    ![alt text](/image/crs_extend_02/image_008.png)

    </div>

- タスク一覧画面
    <div class="image-section">

    ![alt text](/image/crs_extend_02/image_009.png)

    </div>

- タスク詳細画面
    <div class="image-section">

    ![alt text](/image/crs_extend_02/image_010.png)

    </div>

---

#### <a href="../appendix/crs_extend_02/design_c.html" download>デザイン案C</a>
<div class="image-section">

![alt text](/image/crs_extend_02/image_011.png)

</div>


**画面イメージ**

- ログイン画面
    <div class="image-section">

    ![alt text](/image/crs_extend_02/image_012.png)

    </div>

- タスク一覧画面
    <div class="image-section">

    ![alt text](/image/crs_extend_02/image_013.png)

    </div>

- タスク詳細画面
    <div class="image-section">

    ![alt text](/image/crs_extend_02/image_014.png)

    </div>

---

比較検討の結果、案Aがしっくりきたので採用。既存のコードを修正にかかる。
AI頼りな脳みそツルツル現代人には手動でコード修正などできないので、修正はClaude Codeに依頼。さらにプロンプト作成もGensparkに依頼する。

<div class="image-section">

![alt text](/image/crs_extend_02/image_015.png)

</div>

快く引き受けてくれた。しばらくすると<a href="../appendix/crs_extend_02/claude_code_prompt.md" download>プロンプト</a>が完成。

<div class="image-section">

![alt text](/image/crs_extend_02/image_016.png)

</div>

ご丁寧に使い方のコツまで教えてくれたのでその通りに実行。
暫くすると修正が完了。システムを起動してみる。

<div class="image-section">

![alt text](/image/crs_extend_02/image_017.png)

</div>

全体のデザインは指定通りになってはいるのだが、タスク詳細画面の翻訳結果が見にくい。
もう一度Gensparkに改善案を提案してもらう。

<div class="image-section">

![alt text](/image/crs_extend_02/image_018.png)

</div>

改善案の提案と共に指摘してくれた、既存のデザインが抱えている問題点はこちら。

<div class="image-section">

![alt text](/image/crs_extend_02/image_019.png)

</div>

なるほど。では3つのデザイン案を見てみよう。

---

#### <a href="../appendix/crs_extend_02/display_a.html" download>デザイン案A</a>

<div class="image-section">

![alt text](/image/crs_extend_02/image_020.png)

</div>

**画面イメージ**

- 全体
    <div class="image-section">

    ![alt text](/image/crs_extend_02/image_021.png)

    </div>
- 関数一覧
    <div class="image-section">

    ![alt text](/image/crs_extend_02/image_022.png)

    </div>

---

#### <a href="../appendix/crs_extend_02/display_b.html" download>デザイン案B</a>
<div class="image-section">

![alt text](/image/crs_extend_02/image_023.png)

</div>


**画面イメージ**

- 全体
    <div class="image-section">

    ![alt text](/image/crs_extend_02/image_024.png)

    </div>

- インポート欄
    <div class="image-section">

    ![alt text](/image/crs_extend_02/image_025.png)

    </div>

---

#### <a href="../appendix/crs_extend_02/display_c.html" download>デザイン案C</a>
<div class="image-section">

![alt text](/image/crs_extend_02/image_026.png)

</div>


**画面イメージ**

- 全体
    <div class="image-section">

    ![alt text](/image/crs_extend_02/image_027.png)

    </div>

---

比較検討の結果、サイドバーのように表示している案Bのアイデアがしっくりきたので採用。
3エリア構成は維持したまま、細かい部分の修正を追加で指示。

<div class="image-section">

![alt text](/image/crs_extend_02/image_028.png)

</div>

暫くすると修正を加味した<a href="../appendix/crs_extend_02/display_b2.html" download>HTML</a>が出力された。

<div class="image-section">

![alt text](/image/crs_extend_02/image_029.png)

</div>

申し分ない。改めてClaude Code向けのプロンプトを作成依頼。

<div class="image-section">

![alt text](/image/crs_extend_02/image_030.png)

</div>

暫くして<a href="../appendix/crs_extend_02/claude_code_prompt_v2.md" download>プロンプト</a>が出来上がったのだが、これが問題。
中身を見るとさっき施した大規模なデザインの修正が無かったことにされている。原因は少し前にチャットに流れていたこの部分。

<div class="image-section">

![alt text](/image/crs_extend_02/image_031.png)

</div>

やり取りが圧縮されたことで、さっきまでの記憶を失っていた。
~~[配信](https://www.youtube.com/watch?v=BM7GGxJzXuI)を視聴しながら~~他の作業と並行して操作していたので、よく内容を確認せず進めてしまったのがまずかったらしい。
詳細な指示を追加して再度依頼。

<div class="image-section">

![alt text](/image/crs_extend_02/image_032.png)

</div>

添付した画像の記憶も消えているようなので、再添付。
こちらが指示せずとも、待ち時間を無駄にしないようにできる作業を進めている点にも注目。

<div class="image-section">

![alt text](/image/crs_extend_02/image_033.png)

=== 中略 ===

![alt text](/image/crs_extend_02/image_034.png)

</div>

<a href="../appendix/crs_extend_02/prompt_display_only.md" download>プロンプト</a>の作成が完了。改めてClaude Codeに依頼してコードの修正を行う。
暫くするとコードの修正が完了。アプリケーションを起動して確認する。

- ログイン画面
    <div class="image-section">

    ![alt text](/image/crs_extend_02/image_035.png)

    </div>
- タスク一覧画面
    <div class="image-section">

    ![alt text](/image/crs_extend_02/image_036.png)

    </div>
- タスク詳細画面
  - インポート
    <div class="image-section">

    ![alt text](/image/crs_extend_02/image_037.png)

    </div>


  - 関数
    <div class="image-section">

    ![alt text](/image/crs_extend_02/image_038.png)

    </div>

善哉。
ついでに未実装の機能を実装して、他の画面や要素のスタイルも今回新たに作成した合わせて修正を依頼。
ダラダラと[配信](https://www.youtube.com/watch?v=E2D_YFRHFG8&t=3582s)を見ている間に、ほぼすべての作業をGensparkとClaude Codeがやってくれました。

#### Cパート
非常に優秀で最強に思えるClaude Codeにも弱点はあるらしく、トースト部分の修正に手古摺っているようだった。

<div class="image-section">

![alt text](/image/crs_extend_02/image_039.png)

</div>

正常系の操作時に表示される右上トーストだが、元々は下部に残存表示時間を示すプログレスバーが存在した。
だが何度指示してもプログレスバーとトーストの色を他と併せたスタイルに変更できず、諦めて常時表示に変更した。
この変更はCopilotのClaude Sonnet 4.6に依頼して、原因の調査と修正を行って事なきを得た。
AIにも得手不得手があるらしい。実装作業完全AI化への道はまだ遠いぺこ。

『GensparkとClaude Codeが一晩で やってくれました』～Claude Sonnet 4.6を添えて～
