from common.constants import AREA_CODE
from models import AccommodationPlan, AccommodationPlanDetail, SearchPlanResponse, GetPlanDetailResponse
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


def get_detail(plan_id: int) -> GetPlanDetailResponse:
    """
    プランIDから該当する宿泊プランの詳細情報を取得する

    Args
    -----------------
    - plan_id: int,                         宿泊プランID

    Returns
    -----------------
    - response: GetPlanDetailResponse,      レスポンス

    """
    # プランIDから該当する宿泊プラン詳細をSELECT
    df = db_access_service.select_plan_detail(plan_id)

    # 該当するプランが存在しない場合はエラーメッセージを返却
    if df.empty:
        return GetPlanDetailResponse(
            messages=[{
                "message_id": "E001",
                "message_type": "error",
                "message": "該当する宿泊プランが見つかりませんでした。",
            }]
        )

    # 取得したデータのエリアコードを実際の地域名称に変換
    record = df.to_dict(orient="records")[0]
    record["area"] = AREA_CODE.get(record["area"], record["area"])

    # 取得したデータをAccommodationPlanDetailに変換
    plan = AccommodationPlanDetail(**record)

    # レスポンス返却
    return GetPlanDetailResponse(messages=[], plan=plan)
