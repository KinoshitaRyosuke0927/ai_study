from models import AccommodationPlan, SearchPlanResponse
from database import db_access_service


def search(key_word: str) -> SearchPlanResponse:
    """
    キーワードから該当する宿泊プランを検索する

    Args
    -----------------
    - key_word: str,                    検索欄に入力されたキーワード

    Returns
    -----------------
    - response: SearchPlanResponse,     レスポンス

    """
    # キーワードから該当する宿泊プランをSELECT
    df = db_access_service.select_plan(key_word)
    # 取得したデータを1行ずつAccommodationPlanに変換
    plans = [AccommodationPlan(**row) for row in df.to_dict(orient="records")]

    # レスポンス返却
    return SearchPlanResponse(messages=[], plans=plans)
