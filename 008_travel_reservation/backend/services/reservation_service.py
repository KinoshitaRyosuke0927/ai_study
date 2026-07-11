from datetime import date, timedelta

import pandas as pd

from common.constants import RESERVATION_STATUS
from common.error_messages import ErrorMessages
from models import (
    Reservation, GetReservationsResponse,
    AvailabilityDay, GetPlanAvailabilityResponse,
    CreateReservationRequest, CreateReservationResponse,
)
from database import db_access_service

# 空室状況を表示する日数(当日から何日分の空室状況を返すか)
AVAILABILITY_RANGE_DAYS = 60


def get_reservations(user_id: int) -> GetReservationsResponse:
    """
    ユーザIDから該当ユーザの予約一覧情報を取得する

    Args
    -----------------
    - user_id: int,                     ユーザID

    Returns
    -----------------
    - response: GetReservationsResponse,    レスポンス

    """
    # ユーザIDから該当する予約情報(宿泊プラン・ホテル情報を含む)をSELECT
    df = db_access_service.select_reservations(user_id)

    reservations = []
    for record in df.to_dict(orient="records"):
        # 予約日を表示用の文字列に変換
        record["date_of_stay"] = record["date_of_stay"].strftime("%Y-%m-%d")
        # 予約状況のコード値を日本語に変換
        record["status"] = RESERVATION_STATUS.get(record["status"], record["status"])
        reservations.append(Reservation(**record))

    # レスポンス返却
    return GetReservationsResponse(messages=[], reservations=reservations)


def get_plan_availability(plan_id: int) -> GetPlanAvailabilityResponse:
    """
    プランIDから、当日以降AVAILABILITY_RANGE_DAYS日分の空室状況を取得する

    Args
    -----------------
    - plan_id: int,                             宿泊プランID

    Returns
    -----------------
    - response: GetPlanAvailabilityResponse,    レスポンス

    """
    # プランの1日あたりの最大部屋数を取得
    capacity = db_access_service.select_plan_capacity(plan_id)

    # 該当するプランが存在しない場合はエラーメッセージを返却
    if capacity is None:
        return GetPlanAvailabilityResponse(messages=[ErrorMessages.E_0002])

    # 日付ごとの有効な予約件数(キャンセルを除く)を取得
    reserved_counts = db_access_service.select_reservation_counts(plan_id)

    # 当日からAVAILABILITY_RANGE_DAYS日分について、予約件数が最大部屋数未満かどうかで空室状況を判定
    today = date.today()
    availability = []
    for offset in range(AVAILABILITY_RANGE_DAYS):
        target_date = today + timedelta(days=offset)
        reserved_count = int(reserved_counts.get(pd.Timestamp(target_date), 0))
        availability.append(
            AvailabilityDay(date_of_stay=target_date.strftime("%Y-%m-%d"), is_available=reserved_count < capacity)
        )

    # レスポンス返却
    return GetPlanAvailabilityResponse(messages=[], capacity=capacity, availability=availability)


def create_reservation(request: CreateReservationRequest) -> CreateReservationResponse:
    """
    指定された宿泊プラン・宿泊日で予約を登録する

    Args
    -----------------
    - request: CreateReservationRequest,        予約登録リクエスト

    Returns
    -----------------
    - response: CreateReservationResponse,      レスポンス

    """
    # プランの1日あたりの最大部屋数を取得
    capacity = db_access_service.select_plan_capacity(request.plan_id)

    # 該当するプランが存在しない場合はエラーメッセージを返却
    if capacity is None:
        return CreateReservationResponse(messages=[ErrorMessages.E_0002])

    # 指定日の予約件数が最大部屋数に達している場合はエラーメッセージを返却
    reserved_counts = db_access_service.select_reservation_counts(request.plan_id)
    target_date = pd.Timestamp(request.date_of_stay)
    reserved_count = int(reserved_counts.get(target_date, 0))
    if reserved_count >= capacity:
        return CreateReservationResponse(messages=[ErrorMessages.E_0003])

    # 予約を登録
    db_access_service.insert_reservation(request.user_id, request.plan_id, target_date)

    # レスポンス返却
    return CreateReservationResponse(messages=[])
