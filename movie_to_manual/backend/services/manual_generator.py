import base64
import os

from jinja2 import Environment, FileSystemLoader

from models.schemas import ManualStructure


def generate_html_manual(
    manual: ManualStructure,
    frame_paths: list[str],
    output_dir: str,
    manual_id: str,
) -> str:
    """
    ManualStructureからHTMLマニュアルを生成して保存する。

    引数:
        manual: マニュアル構造体
        frame_paths: 抽出済みフレーム画像パスリスト
        output_dir: 出力先ディレクトリ
        manual_id: マニュアルのユニークID

    戻り値:
        生成されたHTMLファイルのパス
    """
    manual_output_dir = os.path.join(output_dir, manual_id)
    os.makedirs(manual_output_dir, exist_ok=True)

    # フレームをBase64エンコード（screenshot_filename → base64データ）
    frame_map: dict[str, str] = {}
    for frame_path in frame_paths:
        filename = os.path.basename(frame_path)
        try:
            with open(frame_path, "rb") as f:
                frame_map[filename] = base64.b64encode(f.read()).decode("utf-8")
        except Exception:
            frame_map[filename] = ""

    # Jinja2テンプレートのロード
    templates_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
    env = Environment(loader=FileSystemLoader(templates_dir), autoescape=True)
    template = env.get_template("manual_template.html")

    html_content = template.render(
        manual=manual,
        frame_map=frame_map,
    )

    output_path = os.path.join(manual_output_dir, "manual.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return output_path


# ---------------------------------------------------------------------------
# PHASE 2 拡張予定（現在は未実装）
# ---------------------------------------------------------------------------
# def merge_duplicate_steps(manual: ManualStructure) -> ManualStructure:
#     """sentence-transformersを使って意味的に重複するステップをマージする"""
#     from sentence_transformers import SentenceTransformer, util
#     model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
#     # 類似度が0.9以上のステップを統合
#     pass
