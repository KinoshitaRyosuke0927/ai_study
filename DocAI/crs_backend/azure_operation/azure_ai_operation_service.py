import copy

from openai import AzureOpenAI

from azure_operation.azure_constant import (
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    FAILURE_TEXT,
    FEW_SHOT_PROMPT_DETAIL,
    FEW_SHOT_PROMPT_TEXT,
    PROMPT_TEXT,
    SAMPLE_CODE,
    SAMPLE_RESPONSE,
    SECURE_PROMPT,
)

## 接続に必要なモデルの情報
# デプロイしたモデルのAPIバージョン
API_VERSION = "2024-12-01-preview"
# デプロイしたモデルの名称
MODEL_NAME = "gpt-5-chat"

# Azure OpenAI クライアント用意
client = AzureOpenAI(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY,
    api_version=API_VERSION
)
# チャット履歴を保持するリスト
CHAT_TEMPLATE = [
    {"role": "system", "content": "You are a talented IT engineer."}
]


def translate_code(code_text: str) -> str:
    """
    入力されたコードに対して処理内容を解析してMarkdownテキストを生成する関数

    Args
    -----------------
    - code_text: str,                       アップロードされたコード

    Returns
    -----------------
    - translated_code_text: str,            解析したコード内容(標準MD形式)

    """
    ## ファイルの中身が存在しない場合
    if len(code_text) == 0:
        return FAILURE_TEXT

    # ## セキュリティ上問題のある記述がある場合は報告
    # # プロンプト付与
    # cast_message = SECURE_PROMPT + "```markdown" + code_text + "```"
    # # 入力データを履歴に追加
    # chat_history = copy.deepcopy(CHAT_TEMPLATE)
    # chat_history.append({"role": "user", "content": cast_message})
    # # モデルにデータ送信
    # response = client.chat.completions.create(
    #     model=MODEL_NAME,
    #     messages=chat_history
    # )
    # # モデルからのレスポンスを取得
    # secured_text = response.choices[0].message.content.strip()
    # # セキュリティ上問題のある記述が検知された場合はエラーメッセージを返却
    # if secured_text == "1":
    #     return FAILURE_TEXT

    ## コード変換処理
    # 事前学習メッセージ用意
    few_shot_message = SAMPLE_CODE + FEW_SHOT_PROMPT_TEXT + SAMPLE_RESPONSE + FEW_SHOT_PROMPT_DETAIL
    # コードに対してプロンプトを付与
    cast_message = "```" + code_text + "```" + PROMPT_TEXT
    # 入力データを履歴に追加
    chat_history = copy.deepcopy(CHAT_TEMPLATE)
    chat_history.append({"role": "user", "content": few_shot_message})
    chat_history.append({"role": "user", "content": cast_message})
    # モデルにデータ送信
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=chat_history
    )
    # モデルからのレスポンスを取得
    translated_code_text = response.choices[0].message.content.strip()
    # レスポンスからマークダウンのコードブロックを除去
    translated_code_text = translated_code_text.replace("```markdown", "").replace("```", "")

    return translated_code_text
