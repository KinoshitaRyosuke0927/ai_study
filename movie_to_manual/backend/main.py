import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from routers import manual as manual_router

app = FastAPI(
    title="Movie to Manual API",
    description="画面録画動画から操作マニュアルを自動生成するAPI",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(manual_router.router, prefix="/api")


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


@app.on_event("startup")
def startup_event():
    """起動時にアップロード・出力ディレクトリを自動作成する"""
    upload_dir = os.getenv("UPLOAD_DIR", "uploads")
    output_dir = os.getenv("OUTPUT_DIR", "outputs")
    os.makedirs(upload_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)
    print(f"[startup] アップロードディレクトリ: {upload_dir}")
    print(f"[startup] 出力ディレクトリ: {output_dir}")
