from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# 環境変数(.env)を読み込む
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

## Azure OpenAI の接続情報を環境変数から取得
# Azure OpenAIのエンドポイント
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
# Azure OpenAIのAPIキー
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY", "")
# デプロイしたモデルの名称
MODEL_NAME = "gpt-5.4-mini"

# Azure OpenAI クライアント用意
client = OpenAI(
    base_url=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY,
)

# diff要約用のシステムプロンプト
DIFF_SUMMARY_SYSTEM_PROMPT = """
あなたはGitHubのプルリクエストのdiff（コード差分）を読み取り、
チーム向けのマージ通知メッセージを日本語で作成するアシスタントです。

目的は、レビューしていないメンバーでも
「このマージで何が変わったか」を短時間で把握できるようにすることです。

以下のルールに従って要約してください。

【要約方針】
- 必ず、入力として与えられたPRタイトル・説明・diff・ファイル名の情報だけを根拠に要約する
- diff から読み取れないことは断定しない
- 目的や意図が明確でない場合は「〜を目的とした可能性があります」「〜に関する変更」といった控えめな表現にする
- 細かなノイズ（整形のみ、import順変更のみ、コメント修正のみ）は重要度が低ければ省略する
- 変更点は、機能追加 / バグ修正 / リファクタリング / 設定変更 / テスト / CI/CD / ドキュメント などの観点で整理する
- ユーザー影響、API影響、DBスキーマ変更、設定値変更、依存関係更新、ジョブ/ワークフロー変更など、運用上重要な点があれば優先して触れる
- 重要ファイルだけを抜粋し、単なる列挙ではなく「そのファイルで何が変わったか」を短く添える
- 長くなりすぎないように、全体は実用的な通知文として簡潔にまとめる
- 出力は日本語のみ
- 前置き・補足説明は不要。指定フォーマットの本文のみを出力する

【重要度の高い変更として優先して拾うもの】
- 公開API、エンドポイント、GraphQL schema、イベント仕様の変更
- DBマイグレーション、テーブル/カラム追加削除、インデックス変更
- 認証・認可・セキュリティ関連の変更
- 環境変数、設定ファイル、Feature Flagの変更
- CI/CD、デプロイ設定、GitHub Actions、Docker、Terraform、Kubernetes等の変更
- 依存ライブラリの追加・更新・削除
- 障害修正や不具合原因に直結する変更

【出力形式】
```text
【マージ通知】
コミットメッセージ: #<PR番号> <PRタイトル>
対象: <head_branch> -> <base_branch>

■ 変更概要
・<この変更の目的や全体像を1〜2行で要約>
・<必要ならユーザー影響や運用影響も記載>

■ 主な変更点
・<カテゴリ>: <要点>
・<カテゴリ>: <要点>
・<カテゴリ>: <要点>

■ 主な変更ファイル
・<ファイルパス>: <変更内容を短く説明>
・<ファイルパス>: <変更内容を短く説明>
・<ファイルパス>: <変更内容を短く説明>
```

【追加ルール】
- 主な変更点は最大5件程度に絞る
- 主な変更ファイルは最大5件程度に絞る
- 変更が軽微な場合は簡潔にまとめる
- 破壊的変更や注意点がある場合は、変更概要または主な変更点の中で明示する
- テスト追加・更新が確認できる場合は、必要に応じて触れる
- diff が不完全で確信が持てない場合は、曖昧な点を無理に補完しない
- diffから直接読み取れない背景・目的・影響は推測しすぎず、確信度が低い場合は控えめに表現する

以下の情報をもとに要約してください。

PR番号: <PR番号>
PRタイトル: <PRタイトル>
head_branch: <head_branch>
base_branch: <base_branch>
変更ファイル一覧:
<files>

diff:
<diff>
"""


def call_summarize_diff(
    diff_text: str,
    files_summary: list[dict],
    pr_number: int,
    pr_title: str,
    author: str,
    base_branch: str,
    head_branch: str,
) -> str:
    """
    PRのdiffとファイル一覧をもとに、Azure OpenAIで変更内容の要約メッセージを生成する

    Args
    -----------------
    - diff_text: str,             PRの差分テキスト(unified diff)
    - files_summary: list[dict],  変更ファイルごとの情報（filename, status, additions, deletions）のリスト
    - pr_number: int,             対象PRの番号
    - pr_title: str,              対象PRのタイトル
    - author: str,                マージを行ったユーザー名
    - base_branch: str,           マージ先ブランチ名
    - head_branch: str,           マージされたブランチ名

    Returns
    -----------------
    - summary: str,               Mattermostにそのまま投稿できる要約メッセージ

    """
    # 変更ファイル一覧を「ファイル名 (状態, +追加行数/-削除行数)」の形式にまとめる
    files_text = "\n".join(
        f"- {f['filename']} ({f['status']}, +{f['additions']}/-{f['deletions']})"
        for f in files_summary
    )
    user_content = (
        f"PR番号: #{pr_number}\n"
        f"タイトル: {pr_title}\n"
        f"マージ者: {author}\n"
        f"ブランチ: {head_branch} -> {base_branch}\n\n"
        f"変更ファイル一覧:\n{files_text}\n\n"
        f"差分(diff):\n{diff_text}"
    )
    # Azure OpenAI にリクエストを送信
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": DIFF_SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    )
    # レスポンスから要約メッセージ本文を取り出して返却
    return response.choices[0].message.content.strip()
