FROM python:3.12-slim

# LibreOffice（PPTX→PDF変換）・Poppler（PDF→画像変換）・日本語フォントをインストール
# 日本語フォントを入れないとスライド内の日本語テキストが画像化時に文字化け（tofu）するため必須
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libreoffice-impress \
        libreoffice-core \
        poppler-utils \
        fonts-noto-cjk \
        fontconfig \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 依存パッケージのインストール（キャッシュを効かせるため先にrequirements.txtだけコピー）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリ本体とデータ（観点シードCSV・過去レビューログ）を配置
COPY app/ ./app/
COPY data/ ./data/

# 非rootユーザーで実行
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
