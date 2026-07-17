import json
import os
from openai import OpenAI

from prompt import PROMPT_TEXT, ROLE_DICT
from history_store import build_profile_context

############################################################
## 接続情報
############################################################
# Azure OpenAIのエンドポイント
AZURE_OPENAI_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
# Azure OpenAIのAPIキー
AZURE_OPENAI_KEY = os.environ["AZURE_OPENAI_KEY"]
# デプロイしたモデルの名称
MODEL_NAME = "gpt-5.4-mini"

# Azure OpenAI クライアント用意
client = OpenAI(
    base_url=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY
)


def brushup_text(transcript: str) -> str:
    """
    文字起こしされたテキストをAIを用いて推敲する関数

    Args
    -----------------
    - transcript: str,                      文字起こしされた音声データ

    Returns
    -----------------
    - result_text: str,                     推敲された文字起こしデータ

    """
    ## 文章推敲処理
    # 文字起こしデータに対してプロンプトを付与
    cast_message = PROMPT_TEXT.format(transcript=transcript)
    # モデルにデータ送信
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": cast_message}]
    )
    # モデルからのレスポンスを取得
    result_text = response.choices[0].message.content.strip()

    return result_text


def play_role(
    role_type: str,
    reviewer_name: str,
    transcript: str,
    user_profile: dict | None = None,
) -> dict:
    """
    指定された役割に応じて発表内容を批評する関数

    Args
    -----------------
    - role_type: str,                       演じる役割
    - reviewer_name: str,                   レビュアーの名前（人格として振る舞わせる）
    - transcript: str,                      発表内容
    - user_profile: dict | None,            ユーザーの過去傾向プロファイル（あればプロンプトに注入）

    Returns
    -----------------
    - result_dict: dict,                    批評結果 (JSON パース済み)

    """
    ## 文章批評処理
    # 名前プレフィックス → ユーザープロファイル文脈 → 役割プロンプト の順で組み立てる
    name_prefix     = f"あなたの名前は「{reviewer_name}」です。レビュー内での自己紹介や署名は不要ですが、この名前の人格として振る舞ってください。\n\n"
    profile_context = build_profile_context(user_profile) if user_profile else ""
    base_prompt     = ROLE_DICT[role_type].format(transcript=transcript)
    cast_message    = name_prefix + profile_context + base_prompt
    # モデルにデータ送信（JSON モードを指定）
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": cast_message}],
        response_format={"type": "json_object"},
    )
    # モデルからのレスポンスを取得して JSON パース
    result_text = response.choices[0].message.content.strip()
    result_dict = json.loads(result_text)

    return result_dict
