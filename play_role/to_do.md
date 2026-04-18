あなたは熟練のPython / FastAPI エンジニアです。
このリポジトリに、発表練習アプリの「継続練習型の記憶機能」を実装してください。

# 目的
このアプリでは、ユーザーの発表履歴を蓄積し、
次回以降のAIコメント生成時に、過去の傾向を踏まえたフィードバックを返せるようにしたいです。

実現したいことは以下です。

- ユーザーの過去の発表履歴を保存する
- 各役割AIの評価結果を保存する
- 保存済みの履歴から、そのユーザーの継続的な傾向を要約する
- 次回のコメント生成時に、その要約をプロンプトへ渡す
- その結果、以下のようなコメントができるようにする

例:
- 「前回も導入が長いと指摘しましたが、今回もやや長めです」
- 「前回より結論提示が早くなっています」
- 「これまで繰り返し指摘されていた専門用語の説明不足は改善しています」

# 前提
- DBは使わない
- DB相当の保存は CSV で行う
- テキスト本文は必要に応じて別ファイル保存でもよい
- 既存の OpenAI を使った LLM 呼び出し処理がすでにある想定なので、それを参考にして実装すること
- OpenAI の API 呼び出し部分は、既存コードの流儀・構成・インターフェースを尊重すること
- 既存コードに comment / review / prompt builder 相当の処理があれば、そこへ自然に統合すること

# 実装したい機能の概要
以下の3層を追加したいです。

1. 発表ごとの履歴保存
2. 履歴からのユーザープロファイル生成
3. 次回コメント時のプロンプトへの反映

# 保存方式
CSV を用いて以下の情報を保持してください。

## 1. presentations.csv
1回の発表セッション単位の記録

保存したい情報の例:
- presentation_id
- user_id
- created_at
- title
- input_type
- transcript_path または transcript
- corrected_transcript_path または corrected_transcript
- duration_sec
- notes

transcript と corrected_transcript は、CSVに直接全文保存してもよいですが、
長文化しやすい場合はテキストファイルへ保存してCSVにはパスを持つ形でも可です。
実装しやすい方を選んでください。ただし README で方針を説明してください。

## 2. role_feedback.csv
各発表 × 各役割 の評価結果

保存したい情報の例:
- feedback_id
- presentation_id
- user_id
- role
- created_at
- summary
- good_points_json
- improvement_points_json
- role_specific_concern
- questions_json
- advice
- raw_response_json (必要なら)

配列系は JSON文字列 で1セルに持ってよいです。

## 3. user_profile.csv
各 user_id ごとの継続傾向の要約

保存したい情報の例:
- user_id
- updated_at
- strengths_json
- weaknesses_json
- recurring_issues_json
- improved_points_json
- last_advice_json
- summary

# 実装の基本方針
以下の順で実装してください。

1. CSV保存レイヤーを作る
2. 発表完了時に履歴保存できるようにする
3. 役割ごとの評価保存を行う
4. 直近履歴から user_profile を更新する処理を作る
5. 次回コメント生成時に user_profile をプロンプトへ組み込む
6. 既存UI/既存APIに自然に接続する

# 重要な要件
## 既存のOpenAI処理の再利用
このリポジトリ内に、すでに OpenAI API を使った既存処理があるはずです。
必ずそれを探して、次の観点で流用・統一してください。

- APIクライアントの生成方法
- モデル指定方法
- 環境変数の扱い
- プロンプトの構築方法
- エラーハンドリング
- レスポンスのパース方法

新しくバラバラな OpenAI 呼び出しを書かず、既存の流儀に合わせてください。

# 実装したい処理詳細

## A. 発表履歴保存
発表の分析・コメント生成が終わったら、以下を保存してください。

- presentation レコード
- role_feedback レコード群
- user_profile 更新結果

処理の流れとしては以下です。

1. 発表が入力される
2. 文字起こし済みテキストまたは校正済みテキストが得られる
3. 各役割AIのコメントが生成される
4. それらをCSVへ保存する
5. その後 user_profile を更新する

## B. user_profile 更新
まずは PoC として、以下のいずれかで実装してください。

### 優先案
ルールベース + 必要なら既存OpenAI処理を使った要約

推奨の2段階:
- 直近N件の role_feedback を集める
- まず簡易ルールベースで頻出改善点や頻出強みを抽出
- その結果を、必要なら OpenAI に要約させる
- user_profile.csv に保存する

### ルールベースの最低要件
直近3〜5件程度の feedback を見て、
- 繰り返し出ている improvement_points → recurring_issues
- 頻繁に褒められる good_points → strengths
- 頻繁に指摘される弱点 → weaknesses
- 前回改善されたと見なせる点 → improved_points
- 直近の advice → last_advice

として user_profile を更新してください。

表現ゆれがあるので、可能なら簡単な正規化辞書を導入してください。
例:
- 「結論が遅い」「結論提示が遅い」「最初に結論がない」→「結論提示が遅い」
- 「導入が長い」「前置きが長い」→「導入が長い」

この辞書は最小限でよいです。
定数として分離してください。

## C. 次回コメント生成への反映
各役割AIへコメント生成を依頼する際、
その user_id の user_profile を読み込んで、プロンプトに反映してください。

実現したいプロンプトの意図:
- 過去の強み
- 過去の弱み
- 繰り返し指摘されている点
- 前回の主なアドバイス

を踏まえて、今回の内容を評価させる

出力では、可能なら次の観点が出るようにしてください。
- 前回より改善した点
- まだ繰り返されている課題
- 今回新たに見つかった課題

ただし、役割AIの既存プロンプト構成があるはずなので、
それを尊重しながら無理のない形で profile 文脈を追加してください。

# 実装対象の想定ファイル
厳密一致でなくてよいですが、責務を分けてください。
以下のような構成を参考にしてください。

app/
  services/
    storage/
      csv_store.py
      presentation_store.py
      feedback_store.py
      profile_store.py
    profile_service.py
    review_service.py
    comment_service.py
    prompt_service.py
  models/
    schemas.py
data/
  presentations.csv
  role_feedback.csv
  user_profile.csv

既存構成に近づけて構いません。
既存の service / util / repository / prompt builder があるなら、それに寄せてください。

# 追加してほしい処理の詳細

## 1. presentation 保存処理
少なくとも以下の関数または同等機能を追加してください。

- save_presentation(...)
- get_presentations_by_user(user_id, limit=None)

## 2. feedback 保存処理
少なくとも以下の関数または同等機能を追加してください。

- save_role_feedback(...)
- get_feedback_by_user(user_id, limit=None)
- get_feedback_by_presentation(presentation_id)

## 3. profile 保存処理
少なくとも以下の関数または同等機能を追加してください。

- get_user_profile(user_id)
- upsert_user_profile(...)
- build_user_profile(user_id, recent_feedbacks)

## 4. コメント生成前の profile 読み込み
コメント生成処理の入口で user_id を受け取れるようにし、
user_profile が存在する場合はプロンプトへ渡してください。

## 5. プロンプト拡張
既存の役割プロンプトに、以下に相当する文脈を自然に追加してください。

例:
- このユーザーの過去の強み: ...
- このユーザーの過去の弱み: ...
- 繰り返し指摘されている点: ...
- 前回の主なアドバイス: ...

今回の評価では、
- 前回より改善した点
- まだ繰り返されている課題
- 今回新たに見つかった課題
にも注目してください。

ただし、役割本来の視点は失わないでください。

# API / UIへの接続
既存のAPIや画面があるはずなので、以下をできる範囲で追加してください。

## 可能なら追加したいもの
- user_id を入力または指定できるようにする
- 過去の user_profile を取得・表示できる簡易APIまたは画面
- 直近の発表履歴一覧を確認できる簡易表示

ただし、最優先は保存とプロンプト反映です。
UIは最小限で構いません。

# 実装時の注意
- CSVファイルが存在しない場合は自動生成すること
- ヘッダ行を正しく扱うこと
- 文字コードは UTF-8 を前提にすること
- 例外時のエラーハンドリングを入れること
- 同時書き込み耐性はPoCレベルでよいが、最低限壊れにくい実装にすること
- JSON文字列のシリアライズ/デシリアライズを適切に行うこと
- 型ヒントをできるだけ付けること
- 定数や閾値は定数化すること

# READMEに追記してほしい内容
以下を README に追加・更新してください。

- CSVベースで履歴を保持していること
- 保存されるファイルの説明
- presentations.csv / role_feedback.csv / user_profile.csv の役割
- 本文をCSV直保存しているのか、別ファイル保存しているのか
- 今後DBへ移行する場合の拡張ポイント
- 現状の制約
  - CSVなので同時更新に弱い
  - データ件数が増えると遅くなる
  - 正規化や集計が簡易実装である

# 実装後にやってほしいこと
実装完了後は、以下を報告してください。

1. 変更・追加したファイル一覧
2. 各ファイルの役割
3. どの既存OpenAI処理を参考・流用したか
4. user_profile がどう更新されるかの概要
5. 実際のデータ保存例
6. 起動手順
7. 今後の改善余地を3〜5個

# 実装ポリシー
- まずは動くPoCを優先してください
- 既存コードの流儀に合わせてください
- OpenAI呼び出しは必ず既存実装を尊重してください
- 無駄に大きな設計変更はしないでください
- 必要な仮定を置いた場合は明記してください
- コードは省略せず、実際にファイルへ反映してください