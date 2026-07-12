from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from models import *
from services import accommodation_plan_service, hotel_service, login_service, reservation_service


app = FastAPI()

# サーバへのアクセスを許可するオリジンを設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    """
    ヘルスチェックエンドポイント
    """
    return {"status": "ok"}


@app.post("/login", response_model=LoginResponse)
def login(request: LoginRequest):
    """
    ログイン画面の処理を行う
    """
    # ログイン状況を返却
    return login_service.login(request.mail_address, request.password, request.is_admin)


@app.post("/search-plan", response_model=SearchPlanResponse)
def search_plan(request: SearchPlanRequest):
    """
    宿泊プランの検索処理を行う
    """
    # 宿泊プランの検索結果を返却
    return accommodation_plan_service.search(request.key_word)


@app.get("/plan-detail/{plan_id}", response_model=GetPlanDetailResponse)
def get_plan_detail(plan_id: int):
    """
    宿泊プラン詳細情報の取得処理を行う
    """
    # 宿泊プランの詳細情報を返却
    return accommodation_plan_service.get_detail(plan_id)


@app.get("/reservations/{user_id}", response_model=GetReservationsResponse)
def get_reservations(user_id: int):
    """
    ユーザの予約一覧情報の取得処理を行う
    """
    # 該当ユーザの予約一覧情報を返却
    return reservation_service.get_reservations(user_id)


@app.get("/plan-availability/{plan_id}", response_model=GetPlanAvailabilityResponse)
def get_plan_availability(plan_id: int):
    """
    宿泊プランの空室状況の取得処理を行う
    """
    # 宿泊プランの空室状況を返却
    return reservation_service.get_plan_availability(plan_id)


@app.post("/reservations", response_model=CreateReservationResponse)
def create_reservation(request: CreateReservationRequest):
    """
    宿泊プランの予約登録処理を行う
    """
    # 予約登録結果を返却
    return reservation_service.create_reservation(request)


@app.get("/admin/hotels/owner/{owner_user_id}", response_model=GetHotelsResponse)
def get_hotels(owner_user_id: int):
    """
    施設管理者(オーナー)が所有する施設一覧の取得処理を行う
    """
    # オーナーが所有する施設の一覧を返却
    return hotel_service.get_hotels(owner_user_id)


@app.post("/admin/hotels", response_model=CreateHotelResponse)
def create_hotel(request: CreateHotelRequest):
    """
    施設の新規登録処理を行う
    """
    # 施設の登録結果を返却
    return hotel_service.create_hotel(request)


@app.get("/admin/hotels/{hotel_id}", response_model=GetHotelDetailResponse)
def get_hotel_detail(hotel_id: int):
    """
    施設詳細情報(宿泊プラン一覧を含む)の取得処理を行う
    """
    # 施設の詳細情報を返却
    return hotel_service.get_hotel_detail(hotel_id)


@app.put("/admin/hotels/{hotel_id}", response_model=UpdateHotelResponse)
def update_hotel(hotel_id: int, request: UpdateHotelRequest):
    """
    施設の基本情報(名称・住所・紹介文)の更新処理を行う
    """
    # 施設情報の更新結果を返却
    return hotel_service.update_hotel(hotel_id, request)


@app.post("/admin/hotels/{hotel_id}/plans", response_model=CreatePlanResponse)
def create_plan(hotel_id: int, request: AccommodationPlanRequest):
    """
    宿泊プランの新規登録処理を行う
    """
    # 宿泊プランの登録結果を返却
    return hotel_service.create_plan(hotel_id, request)


@app.put("/admin/plans/{plan_id}", response_model=UpdatePlanResponse)
def update_plan(plan_id: int, request: AccommodationPlanRequest):
    """
    宿泊プランの更新処理を行う
    """
    # 宿泊プランの更新結果を返却
    return hotel_service.update_plan(plan_id, request)


@app.delete("/admin/plans/{plan_id}", response_model=DeletePlanResponse)
def delete_plan(plan_id: int):
    """
    宿泊プランの削除処理を行う
    """
    # 宿泊プランの削除結果を返却
    return hotel_service.delete_plan(plan_id)
