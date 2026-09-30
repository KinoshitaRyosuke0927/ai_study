# AI学習ポータル コンテナイメージ(Azure App Service / Container Apps 想定)
# ビルド(016_ai_learning_portal/ で実行): docker build -t ai-learning-portal .

# ---------- フロントエンドのビルド ----------
FROM node:22-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------- 実行イメージ ----------
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app/backend

# 依存を先に入れてレイヤキャッシュを効かせる
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

# アプリ本体・講座データ・フロントエンドのビルド成果物
COPY backend/ ./
COPY content/ /app/content/
COPY --from=frontend /src/frontend/dist /app/frontend/dist

ENV APP_ENV=azure \
    APP_FRONTEND_DIST=/app/frontend/dist \
    PORT=8000
EXPOSE 8000

# 起動スクリプト(マイグレーションの適用 → アプリの起動。DB が停止中でも起動を続ける)
CMD ["sh", "./start.sh"]
