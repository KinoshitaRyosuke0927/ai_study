# Frontier コンテナイメージ(Azure Container Apps 想定)
FROM python:3.11-slim

# ロケール / Python 実行時の推奨設定
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 依存を先に入れてレイヤキャッシュを効かせる
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリ本体
COPY . .

# Container Apps 側で PORT が渡される場合に追従(既定 8000)
ENV PORT=8000
EXPOSE 8000

# uvicorn 起動(単一インスタンス前提: APScheduler をアプリ内で動かす)
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
