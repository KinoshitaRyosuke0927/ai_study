import copy
import json
import os
from pathlib import Path
from typing import Dict, Any

from dotenv import load_dotenv
from openai import OpenAI

# プロジェクトルート（002_graph_gui の親ディレクトリ）の .env を読み込む
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

from azure_constant import (
    FEW_SHOT_PROMPT_DETAIL,
    FEW_SHOT_PROMPT_TEXT,
    FLOWCHART_PROMPT_TEXT,
    PROMPT_TEXT,
    SAMPLE_CODE,
    SAMPLE_RESPONSE,
)

## 接続に必要なモデルの情報
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


def generate_flowchart_label(code_text: str, flowchart: Dict[str, Any]) -> Dict[str, Any]:
    """
    入力されたコードとフローチャートに対して日本語のラベルを生成する関数

    Args
    -----------------
    - code_text: str,                       フローチャートの元となるコード
    - flowchart: Dict[str, Any],            ラベルを付与するフローチャート

    Returns
    -----------------
    - update_flowchart: Dict[str, Any],     ラベルが付与されたフローチャート

    """
    # 辞書をJSON形式の文字列に変換
    flowchart_json = json.dumps(flowchart, ensure_ascii=False, indent=2)
    # プロンプト作成
    cast_message = "```" + flowchart_json + "```" + FLOWCHART_PROMPT_TEXT + "```" + code_text + "```"
    # 入力データを履歴に追加
    chat_history = copy.deepcopy(CHAT_TEMPLATE)
    chat_history.append({"role": "user", "content": cast_message})
    # モデルにデータ送信
    print("############### データ送信中 ###############")
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=chat_history
    )
    print("############### 解析完了 ###############")
    # モデルからのレスポンスを取得
    update_flowchart = response.choices[0].message.content.strip()
    # JSONのコードブロックを除去
    update_flowchart = update_flowchart.replace("```json", "").replace("```", "").strip()
    # JSON文字列を辞書に変換
    update_flowchart = json.loads(update_flowchart)

    return update_flowchart
