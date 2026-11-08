"""ヒアリングの回の準備に使う API。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import load_config
from ..planning import analyze_session, home_summary, sort_by_order, to_number
from ..storage import create_row, read_table

router = APIRouter(prefix="/api")


class CopyQuestions(BaseModel):
    """質問の複製の指示を受け取る。"""

    question_ids: list[str]
    segment_id: str = ""


@router.get("/home")
def get_home() -> dict:
    """ホーム画面の内容を返す。

    Returns:
        dict: 対象者ごとの状況と、次にやることの一覧。
    """
    return home_summary()


@router.get("/sessions/{session_id}/analysis")
def get_analysis(session_id: str) -> dict:
    """回の時間配分の集計、警告、引き継ぎの候補を返す。

    Args:
        session_id: 回のID。

    Returns:
        dict: planning.analyze_session の結果。
    """
    result = analyze_session(session_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/sessions/{session_id}/copy-questions")
def copy_questions(session_id: str, body: CopyQuestions) -> dict:
    """共通の質問や前回の質問を、この回の質問として複製する。

    回答メモと「聞いたかどうか」は引き継がない。

    Args:
        session_id: 複製先の回のID。
        body: 複製する質問のIDと、入れる区切り。

    Returns:
        dict: 複製した質問の一覧。
    """
    # 複製先の回があるか確かめる
    if not any(s["session_id"] == session_id for s in read_table("sessions")):
        raise HTTPException(status_code=404, detail="回が見つかりません。")

    # 区切りの中の最後の順番を調べ、その後ろに追加する
    questions = read_table("questions")
    same_segment = [q for q in questions if q["session_id"] == session_id and q["segment_id"] == body.segment_id]
    next_order = max((to_number(q["order"]) for q in same_segment), default=0) + 1

    # 元の質問を順番どおりに複製する
    by_id = {q["question_id"]: q for q in questions}
    user = load_config()["user_name"]
    created = []
    for source in sort_by_order([by_id[i] for i in body.question_ids if i in by_id]):
        values = {k: source[k] for k in ("label", "priority", "text", "check_point", "is_data_question",
                                         "est_min", "hypothesis_ids")}
        values.update({"session_id": session_id, "segment_id": body.segment_id,
                       "order": f"{next_order:g}", "asked": "未", "answer_memo": ""})
        created.append(create_row("questions", values, user))
        next_order += 1
    return {"created": created}
