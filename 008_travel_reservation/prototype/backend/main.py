from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from models import *
from services import accommodation_plan_service, login_service
from database import db_local_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    # サーバ起動時にDBデータ(csv)を読み込む
    db_local_service.read_db_data()
    yield


app = FastAPI(lifespan=lifespan)

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
    return login_service.login(request.mail_address, request.password)


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
