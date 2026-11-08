"""横断表示、評価表、提案用の出力の API。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import analysis
from ..config import load_config
from ..markdown_export import save_export
from ..storage import create_row, read_table, update_row

router = APIRouter(prefix="/api")


class EvaluationCell(BaseModel):
    """評価表の1つのセルの値を受け取る。"""

    issue_id: str
    criterion: str
    rating: str = ""
    comment: str = ""


@router.get("/overview")
def get_overview() -> dict:
    """横断表示の内容を返す。

    Returns:
        dict: analysis.overview の結果。
    """
    return analysis.overview()


@router.get("/evaluations/matrix")
def get_matrix() -> dict:
    """評価表の内容を返す。

    Returns:
        dict: analysis.evaluation_matrix の結果。
    """
    return analysis.evaluation_matrix()


@router.post("/evaluations/cell")
def post_cell(body: EvaluationCell) -> dict:
    """評価表の1つのセルを保存する（なければ追加、あれば更新）。

    Args:
        body: 課題、観点、評価、理由。

    Returns:
        dict: 保存した行。
    """
    # 評価の値を確かめる
    if body.rating not in ("", *analysis.RATING_SCORE):
        raise HTTPException(status_code=400, detail="評価は ◎、○、△、× のいずれかにしてください。")

    # 同じ課題と観点の行があれば更新し、なければ追加する
    user = load_config()["user_name"]
    values = {"rating": body.rating, "comment": body.comment}
    current = next((e for e in read_table("evaluations")
                    if e["issue_id"] == body.issue_id and e["criterion"] == body.criterion), None)
    if current:
        return update_row("evaluations", current["evaluation_id"], values, user)
    return create_row("evaluations", {"issue_id": body.issue_id, "criterion": body.criterion, **values}, user)


@router.get("/export-proposal")
def get_proposal(anonymize: bool = True, save: bool = False) -> dict:
    """提案用の整理を Markdown で作る。

    Args:
        anonymize: True なら、対象者の名前を伏せる。
        save: True なら exports フォルダにも保存する。

    Returns:
        dict: markdown（内容）と saved（保存したファイル名）。
    """
    text = analysis.render_proposal(anonymize)
    saved = save_export("proposal" + ("_anonymized" if anonymize else ""), text) if save else ""
    return {"markdown": text, "saved": saved}
