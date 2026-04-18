import json
import os
import time

import google.generativeai as genai

from models.schemas import ManualStep, ManualStructure

SYSTEM_PROMPT = """
あなたはソフトウェア操作マニュアルの専門ライターです。
提供された画面録画動画を分析し、初めてこのソフトを使うユーザーが
迷わず操作できる、明確で具体的な操作マニュアルを作成してください。

【文体ルール】
- 敬体（〜してください、〜します）で統一すること
- 1ステップ = 1アクションの原則を守ること
- UI要素は【】で囲む（例：【ファイル】メニュー、【保存】ボタン）
- 操作場所は具体的に記述（例：「画面左上のナビゲーションバー内」）

【必須記述事項】
- 各ステップで操作後に何が起きるか（expected_result）を必ず記述
- 前提条件（どの画面から始まるか）を明記

【出力形式】
必ず以下のJSON形式で出力すること。他の文字列は含めないこと：
{
  "title": "マニュアルタイトル",
  "overview": "この操作の概要（2〜3文）",
  "target_application": "アプリケーション名",
  "prerequisites": ["前提条件1", "前提条件2"],
  "steps": [
    {
      "step_number": 1,
      "title": "ステップのタイトル",
      "action_type": "click|input|scroll|navigate|other",
      "target_element": "操作対象のUI要素と場所",
      "description": "詳細な操作説明（敬体）",
      "expected_result": "操作後の画面変化",
      "screenshot_filename": ""
    }
  ]
}
"""

MOCK_MANUAL = ManualStructure(
    title="サンプル操作マニュアル（モックモード）",
    overview="これはGEMINI_API_KEYが未設定の場合のモックデータです。実際のAPIキーを.envファイルに設定することで、動画から本物のマニュアルが生成されます。",
    target_application="サンプルアプリケーション",
    prerequisites=["アプリケーションがインストール済みであること", "インターネット接続が確認できること"],
    steps=[
        ManualStep(
            step_number=1,
            title="アプリケーションを起動する",
            action_type="navigate",
            target_element="デスクトップのショートカットアイコン",
            description="デスクトップ上にあるアプリケーションのショートカットアイコンをダブルクリックしてください。",
            expected_result="アプリケーションのメイン画面が表示されます。",
            screenshot_filename="",
        ),
        ManualStep(
            step_number=2,
            title="新規プロジェクトを作成する",
            action_type="click",
            target_element="画面左上の【新規作成】ボタン",
            description="画面左上にある【新規作成】ボタンをクリックしてください。",
            expected_result="新規プロジェクト作成ダイアログが表示されます。",
            screenshot_filename="",
        ),
        ManualStep(
            step_number=3,
            title="プロジェクト名を入力する",
            action_type="input",
            target_element="ダイアログ内の【プロジェクト名】入力フィールド",
            description="表示されたダイアログの【プロジェクト名】フィールドに任意の名前を入力してください。",
            expected_result="入力した名前がフィールドに表示されます。",
            screenshot_filename="",
        ),
    ],
)


def analyze_video_with_gemini(
    video_path: str,
    frame_paths: list[str],
) -> ManualStructure:
    """
    Gemini 2.5 Pro APIを使って動画とフレームを解析し、
    ManualStructure形式の構造化データを返す。

    引数:
        video_path: 解析する動画ファイルパス
        frame_paths: 抽出済みフレーム画像パスリスト

    戻り値:
        ManualStructure オブジェクト
    """
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key or api_key == "your_gemini_api_key_here":
        print("[gemini_analyzer] GEMINI_API_KEY が未設定です。モックデータを返します。")
        return MOCK_MANUAL

    genai.configure(api_key=api_key)

    # 動画ファイルをGemini File APIでアップロード
    print(f"[gemini_analyzer] 動画をアップロード中: {video_path}")
    uploaded_file = genai.upload_file(path=video_path)

    # ファイルのstateがACTIVEになるまでポーリング（最大60秒）
    timeout = 60
    start = time.time()
    while uploaded_file.state.name != "ACTIVE":
        if time.time() - start > timeout:
            raise TimeoutError("Gemini File API: ファイルのアクティベートがタイムアウトしました（60秒）")
        time.sleep(2)
        uploaded_file = genai.get_file(uploaded_file.name)
        print(f"[gemini_analyzer] ファイル状態: {uploaded_file.state.name}")

    print("[gemini_analyzer] ファイルがACTIVEになりました。AI解析を開始します...")

    model = genai.GenerativeModel(
        model_name="gemini-2.5-pro-preview-06-05",
        system_instruction=SYSTEM_PROMPT,
    )

    response = model.generate_content(
        [uploaded_file, "上記の動画を分析してマニュアルを作成してください。"],
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
        ),
    )

    raw_json = response.text.strip()
    data = json.loads(raw_json)
    manual = ManualStructure(**data)

    # フレーム画像をステップに割り当て（等分割マッピング）
    manual = _assign_screenshots(manual, frame_paths)

    # アップロードしたファイルを削除
    try:
        genai.delete_file(uploaded_file.name)
    except Exception:
        pass

    return manual


def _assign_screenshots(manual: ManualStructure, frame_paths: list[str]) -> ManualStructure:
    """ステップ数とフレーム数を等分割してscreenshot_filenameをマッピングする"""
    steps = manual.steps
    if not frame_paths or not steps:
        return manual

    updated_steps = []
    for i, step in enumerate(steps):
        frame_index = min(int(i * len(frame_paths) / len(steps)), len(frame_paths) - 1)
        frame_path = frame_paths[frame_index]
        updated_step = step.model_copy(
            update={"screenshot_filename": os.path.basename(frame_path)}
        )
        updated_steps.append(updated_step)

    return manual.model_copy(update={"steps": updated_steps})


# ---------------------------------------------------------------------------
# PHASE 2 拡張予定（現在は未実装）
# ---------------------------------------------------------------------------
# def analyze_with_gpt4o_two_stage(video_path: str, frame_paths: list[str]) -> ManualStructure:
#     """OpenAI GPT-4oによる2段階解析（第1段階: 動画要約、第2段階: マニュアル生成）"""
#     from openai import OpenAI
#     client = OpenAI()
#     # Stage 1: フレームから動作の要約を生成
#     # Stage 2: 要約をもとにマニュアルを生成
#     pass
