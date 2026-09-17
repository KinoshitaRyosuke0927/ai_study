FROM python:3.12-slim

# ffmpeg: 動画からの音声抽出（video_service.py）に必須
# libgl1 / libglib2.0-0: OpenCV(cv2)によるスライド切替検出に必須
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 依存パッケージのインストール（キャッシュを効かせるため先にrequirements.txtだけコピー）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 非rootユーザーを作成し、以降の処理は非rootユーザーで実行
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

# Whisperモデル（small）をビルド時に事前ダウンロードしてイメージに焼き込む。
# appuser のホームディレクトリのキャッシュ（~/.cache/whisper）に保存され、
# 実行時も同じユーザーのため再ダウンロードが発生しない
# （焼き込まないとスケールtoゼロからのコールドスタートのたびにダウンロードが走り、起動が非常に遅くなる）
RUN python -c "import whisper; whisper.load_model('small')"

# アプリ本体を配置
# reviewers.csv・data/ は初期状態として同梱するが、実行中の変更はコンテナのローカルファイルに書き込まれるため
# スケールtoゼロでの再起動時にリセットされる（永続化はしない方針）
COPY --chown=appuser:appuser app.py azure_ai_service.py history_store.py prompt.py video_service.py reviewers.csv ./
COPY --chown=appuser:appuser static/ ./static/
COPY --chown=appuser:appuser templates/ ./templates/
COPY --chown=appuser:appuser docs/ ./docs/
COPY --chown=appuser:appuser data/ ./data/

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
