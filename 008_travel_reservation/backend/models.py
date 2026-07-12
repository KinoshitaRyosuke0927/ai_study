from typing import Optional

from pydantic import BaseModel


# ログインリクエスト
class LoginRequest(BaseModel):
    mail_address: str
    password: str
    # 施設管理者向けログインモードからのリクエストかどうか(Trueの場合owner_flagがONのユーザのみログイン可能)
    is_admin: bool = False

# ログインレスポンス
# ※ログインに失敗した場合にも返却するためuser_id, user_nameは指定せずに返却できるようにしている
class LoginResponse(BaseModel):
    messages: list[dict[str, str]]
    user_id: Optional[int]=None
    user_name: Optional[str]=""
    # 施設管理者権限(owner_flag)を持つユーザかどうか
    is_owner: bool=False

# 宿泊プラン
class AccommodationPlan(BaseModel):
    hotel_id: int
    hotel_name: str
    plan_id: int
    plan_name: str
    price: int

# プラン検索リクエスト
class SearchPlanRequest(BaseModel):
    key_word: str

# プラン検索レスポンス
class SearchPlanResponse(BaseModel):
    messages: list[dict[str, str]]
    plans: list[AccommodationPlan]

# 宿泊プラン詳細
class AccommodationPlanDetail(BaseModel):
    hotel_id: int
    hotel_name: str
    hotel_address: str
    hotel_introduction: str
    plan_id: int
    plan_name: str
    price: int
    area: str
    room_size: int
    has_breakfast: bool
    has_lunch: bool
    has_dinner: bool
    introduction: str

# プラン詳細取得レスポンス
# ※該当プランが存在しない場合にも返却するためplanは指定せずに返却できるようにしている
class GetPlanDetailResponse(BaseModel):
    messages: list[dict[str, str]]
    plan: Optional[AccommodationPlanDetail]=None

# 予約情報(宿泊プラン詳細に予約日・予約状況を加えたもの)
class Reservation(BaseModel):
    hotel_id: int
    hotel_name: str
    plan_id: int
    plan_name: str
    price: int
    date_of_stay: str
    status: str

# 予約一覧取得レスポンス
class GetReservationsResponse(BaseModel):
    messages: list[dict[str, str]]
    reservations: list[Reservation]

# 空室状況(1日分)
class AvailabilityDay(BaseModel):
    date_of_stay: str
    is_available: bool

# プランの空室状況取得レスポンス
# ※該当プランが存在しない場合にも返却するためcapacity・availabilityは空で返却できるようにしている
class GetPlanAvailabilityResponse(BaseModel):
    messages: list[dict[str, str]]
    capacity: int=0
    availability: list[AvailabilityDay]=[]

# 予約登録リクエスト
class CreateReservationRequest(BaseModel):
    user_id: int
    plan_id: int
    date_of_stay: str

# 予約登録レスポンス
class CreateReservationResponse(BaseModel):
    messages: list[dict[str, str]]

# 施設(ホテル)一覧の1件分
class HotelSummary(BaseModel):
    hotel_id: int
    hotel_name: str
    address: str

# 施設一覧取得レスポンス
class GetHotelsResponse(BaseModel):
    messages: list[dict[str, str]]
    hotels: list[HotelSummary]

# 管理画面向け宿泊プラン(1件分)
class AdminAccommodationPlan(BaseModel):
    plan_id: int
    plan_name: str
    price: int
    area: str
    room_size: int
    capacity: int
    has_breakfast: bool
    has_lunch: bool
    has_dinner: bool
    introduction: str

# 施設詳細情報(施設の基本情報+宿泊プラン一覧)
class HotelDetail(BaseModel):
    hotel_id: int
    hotel_name: str
    address: str
    introduction: str
    plans: list[AdminAccommodationPlan]

# 施設詳細取得レスポンス
# ※該当施設が存在しない場合にも返却するためhotelは指定せずに返却できるようにしている
class GetHotelDetailResponse(BaseModel):
    messages: list[dict[str, str]]
    hotel: Optional[HotelDetail]=None

# 施設情報更新リクエスト
class UpdateHotelRequest(BaseModel):
    hotel_name: str
    address: str
    introduction: str

# 施設情報更新レスポンス
class UpdateHotelResponse(BaseModel):
    messages: list[dict[str, str]]

# 施設登録リクエスト
class CreateHotelRequest(BaseModel):
    owner_user_id: int
    hotel_name: str
    address: str
    introduction: str

# 施設登録レスポンス
# ※登録に失敗した場合にも返却するためhotel_idは指定せずに返却できるようにしている
class CreateHotelResponse(BaseModel):
    messages: list[dict[str, str]]
    hotel_id: Optional[int]=None

# 宿泊プラン登録・更新リクエスト(共通項目)
class AccommodationPlanRequest(BaseModel):
    plan_name: str
    price: int
    area: str
    room_size: int
    capacity: int
    has_breakfast: bool
    has_lunch: bool
    has_dinner: bool
    introduction: str

# 宿泊プラン登録レスポンス
# ※登録に失敗した場合にも返却するためplan_idは指定せずに返却できるようにしている
class CreatePlanResponse(BaseModel):
    messages: list[dict[str, str]]
    plan_id: Optional[int]=None

# 宿泊プラン更新レスポンス
class UpdatePlanResponse(BaseModel):
    messages: list[dict[str, str]]

# 宿泊プラン削除レスポンス
class DeletePlanResponse(BaseModel):
    messages: list[dict[str, str]]
