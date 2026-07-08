from typing import Optional

from pydantic import BaseModel


# ログインリクエスト
class LoginRequest(BaseModel):
    mail_address: str
    password: str

# ログインレスポンス
# ※ログインに失敗した場合にも返却するためuser_id, user_nameは指定せずに返却できるようにしている
class LoginResponse(BaseModel):
    messages: list[dict[str, str]]
    user_id: Optional[int]=None
    user_name: Optional[str]=""

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
