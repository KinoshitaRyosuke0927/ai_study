"""つながりマップ（課題カードの画面のマップ表示）の API。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import load_config
from ..storage import StorageError, modify_table, now_text

router = APIRouter(prefix="/api")

# 位置を保存できるカードの種類（ID の先頭に付ける）
NODE_KINDS = ("issue", "solution", "source")


class Position(BaseModel):
    """1枚のカードの位置。"""

    node: str
    x: float
    y: float


class Positions(BaseModel):
    """まとめて保存するカードの位置。"""

    positions: list[Position]


@router.post("/map/positions")
def save_positions(body: Positions) -> dict:
    """カードの位置をまとめて保存する（テーマの囲みを動かしたときなど、複数のカードが動くため）。

    すでに位置があるカードは書き換え、ないカードは行を追加する。書き込みは1回にする。

    Args:
        body: カードの位置の一覧。

    Returns:
        dict: saved（保存した件数）。
    """
    # カードの種類を確かめる
    for p in body.positions:
        if p.node.split(":", 1)[0] not in NODE_KINDS or ":" not in p.node:
            raise HTTPException(status_code=400, detail=f"カードの指定が正しくありません：{p.node}")

    user = load_config()["user_name"]
    stamp = now_text()

    def apply(rows: list[dict]) -> tuple[list[dict], int]:
        """位置を行に反映する。

        Args:
            rows: 今の行の一覧。

        Returns:
            tuple: (新しい行の一覧, 保存した件数)。
        """
        # 既存の行を、カードのIDで引けるようにする
        index = {r["node"]: r for r in rows}
        for p in body.positions:
            # 位置は整数にして保存する（CSV を見やすくするため）
            values = {"x": str(round(p.x)), "y": str(round(p.y)), "updated_by": user, "updated_at": stamp}
            if p.node in index:
                index[p.node].update(values)
            else:
                row = {"node": p.node, **values}
                rows.append(row)
                index[p.node] = row
        return rows, len(body.positions)

    try:
        return {"saved": modify_table("map_positions", apply)}
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
