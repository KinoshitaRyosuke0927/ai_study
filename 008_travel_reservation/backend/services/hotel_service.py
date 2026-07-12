from sqlalchemy.exc import IntegrityError

from common.messages import ErrorMessages, InfoMessages
from models import (
    HotelSummary, GetHotelsResponse,
    AdminAccommodationPlan, HotelDetail, GetHotelDetailResponse,
    CreateHotelRequest, CreateHotelResponse,
    UpdateHotelRequest, UpdateHotelResponse,
    AccommodationPlanRequest, CreatePlanResponse, UpdatePlanResponse, DeletePlanResponse,
)
from database import db_access_service


def get_hotels(owner_user_id: int) -> GetHotelsResponse:
    """
    施設オーナーのユーザIDから、そのオーナーが所有する施設の一覧を取得する

    Args
    -----------------
    - owner_user_id: int,               施設オーナーのユーザID

    Returns
    -----------------
    - response: GetHotelsResponse,      レスポンス

    """
    # オーナーのユーザIDから所有する施設の一覧をSELECT
    df = db_access_service.select_hotels_by_owner(owner_user_id)
    hotels = [HotelSummary(**row) for row in df.to_dict(orient="records")]

    # レスポンス返却
    return GetHotelsResponse(messages=[], hotels=hotels)


def get_hotel_detail(hotel_id: int) -> GetHotelDetailResponse:
    """
    施設IDから該当施設の詳細情報(宿泊プラン一覧を含む)を取得する

    Args
    -----------------
    - hotel_id: int,                        施設ID

    Returns
    -----------------
    - response: GetHotelDetailResponse,     レスポンス

    """
    # 施設IDから施設の基本情報をSELECT
    hotel_df = db_access_service.select_hotel(hotel_id)

    # 該当する施設が存在しない場合はエラーメッセージを返却
    if hotel_df.empty:
        return GetHotelDetailResponse(messages=[ErrorMessages.E_0005])

    # 施設IDから宿泊プラン一覧をSELECT
    plan_df = db_access_service.select_plans_by_hotel(hotel_id)
    plans = [AdminAccommodationPlan(**row) for row in plan_df.to_dict(orient="records")]

    hotel_record = hotel_df.to_dict(orient="records")[0]
    hotel = HotelDetail(**hotel_record, plans=plans)

    # レスポンス返却
    return GetHotelDetailResponse(messages=[], hotel=hotel)


def create_hotel(request: CreateHotelRequest) -> CreateHotelResponse:
    """
    新しい施設を1件追加する

    Args
    -----------------
    - request: CreateHotelRequest,       施設登録リクエスト

    Returns
    -----------------
    - response: CreateHotelResponse,     レスポンス

    """
    # 施設を新規追加し、採番されたhotel_idを取得
    hotel_id = db_access_service.insert_hotel(
        request.owner_user_id, request.hotel_name, request.address, request.introduction
    )

    # レスポンス返却
    return CreateHotelResponse(messages=[InfoMessages.I_0005], hotel_id=hotel_id)


def update_hotel(hotel_id: int, request: UpdateHotelRequest) -> UpdateHotelResponse:
    """
    施設の基本情報(名称・住所・紹介文)を更新する

    Args
    -----------------
    - hotel_id: int,                     更新対象の施設ID
    - request: UpdateHotelRequest,       施設情報更新リクエスト

    Returns
    -----------------
    - response: UpdateHotelResponse,     レスポンス

    """
    # 施設の基本情報を更新
    db_access_service.update_hotel(hotel_id, request.hotel_name, request.address, request.introduction)

    # レスポンス返却
    return UpdateHotelResponse(messages=[InfoMessages.I_0001])


def create_plan(hotel_id: int, request: AccommodationPlanRequest) -> CreatePlanResponse:
    """
    施設に新しい宿泊プランを1件追加する

    Args
    -----------------
    - hotel_id: int,                         プランを追加する施設ID
    - request: AccommodationPlanRequest,     宿泊プラン登録リクエスト

    Returns
    -----------------
    - response: CreatePlanResponse,          レスポンス

    """
    # 宿泊プランを新規追加し、採番されたplan_idを取得
    plan_id = db_access_service.insert_plan(
        hotel_id,
        request.plan_name,
        request.price,
        request.area,
        request.room_size,
        request.capacity,
        request.has_breakfast,
        request.has_lunch,
        request.has_dinner,
        request.introduction,
    )

    # レスポンス返却
    return CreatePlanResponse(messages=[InfoMessages.I_0002], plan_id=plan_id)


def update_plan(plan_id: int, request: AccommodationPlanRequest) -> UpdatePlanResponse:
    """
    既存の宿泊プランの内容を更新する

    Args
    -----------------
    - plan_id: int,                          更新対象の宿泊プランID
    - request: AccommodationPlanRequest,     宿泊プラン更新リクエスト

    Returns
    -----------------
    - response: UpdatePlanResponse,          レスポンス

    """
    # 宿泊プランの内容を更新
    db_access_service.update_plan(
        plan_id,
        request.plan_name,
        request.price,
        request.area,
        request.room_size,
        request.capacity,
        request.has_breakfast,
        request.has_lunch,
        request.has_dinner,
        request.introduction,
    )

    # レスポンス返却
    return UpdatePlanResponse(messages=[InfoMessages.I_0003])


def delete_plan(plan_id: int) -> DeletePlanResponse:
    """
    宿泊プランを削除する

    Args
    -----------------
    - plan_id: int,                     削除対象の宿泊プランID

    Returns
    -----------------
    - response: DeletePlanResponse,     レスポンス

    """
    try:
        # 宿泊プランを削除
        db_access_service.delete_plan(plan_id)
    except IntegrityError:
        # 予約が紐づいているプランはt_reservationとの外部キー制約により削除できないため、エラーメッセージを返却
        return DeletePlanResponse(messages=[ErrorMessages.E_0006])

    # レスポンス返却
    return DeletePlanResponse(messages=[InfoMessages.I_0004])
