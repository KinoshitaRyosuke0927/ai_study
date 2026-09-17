# -*- coding: utf-8 -*-
"""データサイエンス基礎ドリル - コース定義（プロトタイプ版）

- ターゲット: プログラミング未経験の社会人
- 形式: 隙間時間で進めるドリル形式（1ドリル 3〜5分）
- 規模: 完成時 1講座 10時間未満（目標 約8.5時間）

新しくレッスン／ドリルを追加するときは、このファイルの LESSONS に
要素を足すだけで、フロントエンドと API に自動反映されます。
"""

COURSE = {
    "id": "ds-kiso-1",
    "title": "データサイエンス基礎ドリル",
    "subtitle": "Python × データ入門",
    "target": "プログラミング未経験の社会人（隙間時間で1日数ドリル）",
    "total_minutes": 510,  # 完成時 約8.5時間（10時間未満）
    "version": "0.1.0（プロトタイプ）",
}

# NOTE: ドリルに expected を書いても、GET /api/lessons/{id} には
# 返らない（解答が漏れないようにしている）。採点時のみ返る。
LESSONS = [
    # ================= 第1章 Pythonの基礎（実装済み） =================
    {
        "id": "l1-1",
        "chapter": 1,
        "chapter_title": "Pythonの基礎",
        "order": 1,
        "title": "変数と出力",
        "minutes": 15,
        "status": "open",
        "summary": "Pythonで最初に覚える2つのこと「変数」と「出力（print）」をドリルで練習します。",
        "explanation": [
            "Pythonは値に「名前」を付けて、それを自由に使うプログラミング言語です。この「名前」が変数です。",
            "`age = 28` と書くと、`age` という箱に数字の 28 が入ります。",
            "`print(...)` は ()の中身を画面（コンソール）に表示するための命令です。",
        ],
        "keypoints": [
            "変数を作る: `名前 = 値`（例: `age = 28`）",
            "画面に出す: `print(変数名)`",
            "文字列は `\"\"`（ダブルクォーテーション）で囲む。数字はそのまま書く",
        ],
        "example": 'name = "たろう"\nage = 28\nprint(name)\nprint(age)',
        "example_output": "たろう\n28",
        "drills": [
            {
                "id": "d1-1-1",
                "type": "code_gap",
                "title": "引き算の結果を出力しよう",
                "question": "print() の中身を埋めて、「17 から 9 を引いた結果」を画面に出力してください。",
                "starter": "print(____)",
                "hint": "print( 答えの数字 ) と書くと、計算した結果がそのまま表示されます。",
                "expected": ["8"],
            },
            {
                "id": "d1-1-2",
                "type": "code_gap",
                "title": "文字列を出力しよう",
                "question": "「おはようございます」という文字列を print() で出力してください。文字は「二重引用符」で囲みます。",
                "starter": 'print("____")',
                "hint": 'print("おはようございます") のように、文章を " と " の間に置きます。',
                "expected": ["おはようございます"],
            },
            {
                "id": "d1-1-3",
                "type": "quiz",
                "title": "「文字列 + 文字列」の結果",
                "question": "次のコードを実行したとき、画面に表示されるのはどれでしょう？\nprint(\"3\" + \"5\")",
                "choices": ["8", "「35」（\"3\"と\"5\"がくっつく）", "エラーになる", "何も表示されない"],
                "answer_index": 1,
                "feedback": "文字列同士の + は「連結」（くっつける）を意味します。「3」+「5」は「35」になります。数字どうしを足したいときは 3 + 5 のように引用符を付けずに書きましょう。",
            },
        ],
    },
    {
        "id": "l1-2",
        "chapter": 1,
        "chapter_title": "Pythonの基礎",
        "order": 2,
        "title": "条件分岐",
        "minutes": 15,
        "status": "open",
        "summary": "「もし〜なら」を書けるようにします。プログラムが判断するための仕組みです。",
        "explanation": [
            "`if 条件:` と書くと、条件が成り立つときだけ、次のブロック（インデント＝字下げした行）が実行されます。",
            "「80点以上なら A」「60点以上なら B」「それ以外は C」のように複数の分岐を作るのが `elif` と `else` です。",
            "比較は `==`（等しい）・`>`・`<`・`>=`・`<=` を使います。代入の `=` とは別物なので注意しましょう。",
        ],
        "keypoints": [
            "基本形: `if 条件:` → 次の行から字下げして処理を書く",
            "追加の分岐: `elif` / どれにも当てはまらないとき: `else`",
            "等しいか調べるのは `==`（`=` は代入）",
            "割り算の余りは `%`（例: 7 % 2 → 1）",
        ],
        "example": 'score = 82\nif score >= 80:\n    print("A")\nelif score >= 60:\n    print("B")\nelse:\n    print("C")',
        "example_output": "A",
        "drills": [
            {
                "id": "d1-2-1",
                "type": "code_gap",
                "title": "80点以上なら「A」を表示",
                "question": "空欄に比較演算子を入れて、score = 82 のとき「A」と表示されるようにしてください。",
                "starter": 'score = 82\nif score ____ 80:\n    print("A")\nelif score >= 60:\n    print("B")\nelse:\n    print("C")',
                "hint": "「80 以上」は「大なりイコール」の `>=` を使います。",
                "expected": ["A"],
            },
            {
                "id": "d1-2-2",
                "type": "code_gap",
                "title": "偶奇で分岐しよう",
                "question": "number = 7 のとき「奇数」と表示されるように、空欄の比較演算子を埋めてください。",
                "starter": 'number = 7\nif number % 2 ____ 0:\n    print("偶数")\nelse:\n    print("奇数")',
                "hint": "7 を 2 で割った余りは 1。余りが 0 と「等しくない」ときは奇数側（else）に進みます。",
                "expected": ["奇数"],
            },
            {
                "id": "d1-2-3",
                "type": "quiz",
                "title": "elif の意味を確認",
                "question": "次のコードで、x = 55 のとき表示されるのはどれでしょう？\nif x >= 80:\n    print(\"A\")\nelif x >= 60:\n    print(\"B\")\nelse:\n    print(\"C\")",
                "choices": ["A", "B", "C", "エラーになる"],
                "answer_index": 2,
                "feedback": "55 は 80 にも 60 にも達していないため、else で「C」になります。if / elif は上から順に判定し、最初に当てはまったブロック「だけ」が実行されるのがポイントです。",
            },
        ],
    },
    {
        "id": "l1-3",
        "chapter": 1,
        "chapter_title": "Pythonの基礎",
        "order": 3,
        "title": "ループとリスト",
        "minutes": 15,
        "status": "open",
        "summary": "「繰り返し」を自動化します。同じ作業を何度も書かずに済む、実務で一番使う道具です。",
        "explanation": [
            "`for i in range(1, 6):` は、i に 1, 2, 3, 4, 5 を順に入れながら、下のブロックを繰り返します。",
            "リスト `[120, 350, 80]` は「値の並び」。`for p in prices:` で1つずつ取り出せます。",
            "合計は `total = total + p` のように「足し込んでいく」書き方が基本です。",
        ],
        "keypoints": [
            "繰り返し: `for 変数 in range(開始, 終了):`（終了は含まない）",
            "リスト: `[値, 値, ...]`。`for 変数 in リスト:` で1つずつ処理",
            "足し込み: `total = total + p`（慣れたら `total += p`）",
        ],
        "example": 'for i in range(1, 4):\n    print(i, "回目")',
        "example_output": "1 回目\n2 回目\n3 回目",
        "drills": [
            {
                "id": "d1-3-1",
                "type": "code_gap",
                "title": "連番を出力しよう",
                "question": "range(1, 6) で i を回し、print(i) で「1 から 5」を順に出力してください。",
                "starter": "for i in range(1, 6):\n    print(____)",
                "hint": "print(i) と書くと、i に入っている数字がそのまま表示されます。",
                "expected": ["1", "2", "3", "4", "5"],
            },
            {
                "id": "d1-3-2",
                "type": "code_gap",
                "title": "合計を計算しよう",
                "question": "prices = [120, 350, 80] の合計（550）を計算して表示してください。空欄の演算子を補います。",
                "starter": "prices = [120, 350, 80]\ntotal = 0\nfor p in prices:\n    total = total ____ p\nprint(total)",
                "hint": "「今まで足したもの」total に、1つずつ p を足し込んでいきます。足し算の記号は + です。",
                "expected": ["550"],
            },
            {
                "id": "d1-3-3",
                "type": "quiz",
                "title": "range の動き",
                "question": "for i in range(1, 4): は、i にどんな値が入りますか？",
                "choices": ["1, 2, 3", "1, 2, 3, 4", "0, 1, 2, 3", "4, 3, 2, 1"],
                "answer_index": 0,
                "feedback": "range(開始, 終了) は「終了の一歩手前」までです。range(1, 4) なら 1, 2, 3 になります。",
            },
        ],
    },
    {
        "id": "l1-4",
        "chapter": 1,
        "chapter_title": "Pythonの基礎",
        "order": 4,
        "title": "総仕上げドリル",
        "minutes": 15,
        "status": "open",
        "summary": "第1章で学んだ「出力・条件・ループ」をまとめて復習します。全部解けたらレッスンに○が付きます。",
        "explanation": [
            "ここまでで学んだ3つのテーマを、順番に思い出しながら解いてみましょう。",
            "分からないときは「ヒント」を見ながらでかまいません。まずは実行して、動きを確かめるのが上達のコツです。",
        ],
        "keypoints": [
            "組み合わせて使える: ループで回して → 条件で判定 → print で出力",
            "計算式の注意: `//` は小数を切り捨てる割り算、`%` は余り",
        ],
        "example": 'total = 0\nfor i in range(1, 4):\n    total = total + i\nprint(total)',
        "example_output": "6",
        "drills": [
            {
                "id": "d1-4-1",
                "type": "code_gap",
                "title": "1 から 10 の合計",
                "question": "1 から 10 までの合計（55）を計算して print() で出力してください。空欄は変数名です。",
                "starter": "total = 0\nfor i in range(1, 11):\n    total = total + i\nprint(____)",
                "hint": "計算が終わったとき合計が入っているのは total です。print(total) と書きます。",
                "expected": ["55"],
            },
            {
                "id": "d1-4-2",
                "type": "code_gap",
                "title": "60点以上なら合格",
                "question": "score = 72 のとき「合格」と表示されるように、空欄の比較演算子を埋めてください。",
                "starter": 'score = 72\nif score ____ 60:\n    print("合格")\nelse:\n    print("不合格")',
                "hint": "72 は 60 以上なので「合格」側へ。以上は `>=` です。",
                "expected": ["合格"],
            },
            {
                "id": "d1-4-3",
                "type": "quiz",
                "title": "四則演算の確認",
                "question": "print(10 // 3) の結果はどれでしょうか？（// は整数どうしの割り算です）",
                "choices": ["3", "3.33…", "1", "エラーになる"],
                "answer_index": 0,
                "feedback": "// は小数点以下を切り捨てる割り算で、10 // 3 は 3 です。余りが欲しいときは 10 % 3 で 1 が得られます。",
            },
            {
                "id": "d1-4-4",
                "type": "quiz",
                "title": "ここまでの復習",
                "question": "変数 name = \"花子\" を作って print(name) で表示すると、画面には何が出ますか？",
                "choices": ["花子", "\"花子\"（引用符も含む）", "name（変数名）", "エラーになる"],
                "answer_index": 0,
                "feedback": "print(変数) は、その変数の「中身」を表示します。引用符はコードの中で文字列を表すための道具なので、表示には含まれません。",
            },
        ],
    },
]
