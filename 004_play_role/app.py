from __future__ import annotations  # 古い Python バージョンでも型ヒントを文字列として扱えるようにする

import csv      # レビュアーデータのCSV保存・読み込みに使用
import json     # プロファイルAPIのレスポンス整形に使用
import os        # ファイルの存在確認や削除などOS操作に使用
import shutil    # ファイルのコピー操作に使用
import tempfile  # 一時ファイルの作成に使用
import uuid      # 動画解析ジョブ ID 生成に使用
from pathlib import Path  # パス操作をOSに依存せず行うために使用

from dotenv import load_dotenv  # .env ファイルから環境変数を読み込むために使用
import threading  # Whisper モデルの遅延ロードでスレッドセーフにするために使用
import whisper  # OpenAI Whisper による音声認識ライブラリ
from pydantic import BaseModel  # リクエストボディのバリデーションモデルに使用
from fastapi import FastAPI, File, HTTPException, Request, UploadFile  # FastAPI 本体と各種ユーティリティ

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")  # .env ファイルから環境変数を読み込む

from azure_ai_service import brushup_text, play_role  # 文字起こし推敲／役割別コメント生成関数
from prompt import ROLE_DICT  # 役割プロンプト辞書（キーが有効な役割名と一致）
from history_store import (    # レビュアー別フィードバック履歴・プロファイルのCSV管理
    save_feedback,
    build_reviewer_profile,
    get_reviewer_profile,
    get_feedback_by_reviewer,
    delete_reviewer_history,
    reset_all_memories,
)
from fastapi.responses import HTMLResponse       # HTML レスポンスを返すためのクラス
from fastapi.staticfiles import StaticFiles      # CSS や JS などの静的ファイルを配信するためのクラス
from fastapi.templating import Jinja2Templates   # Jinja2 テンプレートエンジンを使って HTML を生成するクラス
from video_service import (                      # 動画処理サービス
    extract_audio,
    get_video_duration,
    detect_slide_changes,
    build_slide_intervals,
    save_slide_thumbnails,
    map_speech_to_slides,
)

BASE_DIR = Path(__file__).resolve().parent  # このファイルが置かれているディレクトリを絶対パスで取得
UPLOAD_DIR = BASE_DIR / "uploads"           # アップロードされた音声ファイルを一時保存するディレクトリのパス
OUTPUTS_DIR = BASE_DIR / "outputs"          # スライドサムネイルを保存するディレクトリのパス
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)

VALID_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov"}
REVIEWERS_CSV = BASE_DIR / "reviewers.csv"  # レビュアーデータの永続化ファイル


def load_reviewers() -> list[dict]:
    """CSVからレビュアー一覧を読み込む。ファイルがなければ空リストを返す。"""
    if not REVIEWERS_CSV.exists():
        return []
    with open(REVIEWERS_CSV, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def save_reviewers(reviewers: list[dict]) -> None:
    """レビュアー一覧をCSVに保存する。"""
    with open(REVIEWERS_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['id', 'name', 'role'])
        writer.writeheader()
        writer.writerows(reviewers)


_whisper_model = None          # Whisper モデルの実体（初回リクエスト時にロード）
_whisper_model_lock = threading.Lock()  # 同時ロードを防ぐロック


def get_model() -> whisper.Whisper:
    """Whisper モデルを遅延ロードして返す。サーバー起動直後でもブラウザからアクセス可能にするため、
    モジュール import 時ではなく初回リクエスト時にロードする。"""
    global _whisper_model
    if _whisper_model is None:
        with _whisper_model_lock:
            if _whisper_model is None:  # ダブルチェックロッキング
                print("##### Whisper モデルロード開始 (small) #####")
                _whisper_model = whisper.load_model("small")  # 最小構成のため small モデルを使用（初回はダウンロード発生）
                print("##### Whisper モデルロード完了 #####")
    return _whisper_model


app = FastAPI(title="Whisper Minimal App")  # FastAPI アプリケーションのインスタンスを作成
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")  # サムネイル配信
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))  # テンプレートファイルの検索先ディレクトリを設定


@app.get("/", response_class=HTMLResponse)  # GET / にアクセスしたとき HTML を返すルートを定義
def index(request: Request):
    # index.html テンプレートをレンダリングして返す（request オブジェクトをテンプレートへ渡す）
    return templates.TemplateResponse("index.html", {"request": request})


import time

@app.post("/transcribe")  # POST /transcribe にアクセスしたとき音声文字起こしを行うルートを定義
async def transcribe(audio: UploadFile = File(...)):  # リクエストボディから音声ファイルを受け取る
    if not audio.filename:
        # ファイル名が空の場合は 400 Bad Request エラーを返す
        raise HTTPException(status_code=400, detail="音声ファイルがありません。")

    suffix = Path(audio.filename).suffix or ".webm"  # 元ファイルの拡張子を取得（なければ .webm を使用）
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=UPLOAD_DIR) as temp_file:
        # アップロードされたファイルを一時ファイルへストリーミングコピー
        shutil.copyfileobj(audio.file, temp_file)
        temp_path = temp_file.name  # 処理後に参照するために一時ファイルのパスを保持

    try:
        print("##### 文字起こし開始 #####")
        _start = time.time()
        result = get_model().transcribe(temp_path, language="ja", fp16=False)  # Whisper で日本語として文字起こし（GPU なしなので fp16=False）
        raw_text = result.get("text", "").strip()  # 認識結果のテキストを前後の空白を除いて取得
        print("##### 文字起こし終了 : " + str(time.time() - _start) + " #####")
        # print("##### 校正前テキスト #####")
        # print(raw_text)
        print("##### テキスト校正開始 #####")
        _start = time.time()
        refined_text = brushup_text(raw_text)  # Azure OpenAI で文章を推敲
        print("##### テキスト校正終了 : " + str(time.time() - _start) + " #####")
        # print("##### 校正後テキスト #####")
        # print(refined_text)
        return {"text": refined_text}  # 推敲済みテキストを返す
    except Exception as exc:
        # 文字起こし中に例外が発生した場合は 500 エラーとして返す
        raise HTTPException(status_code=500, detail=f"文字起こしに失敗しました: {exc}") from exc
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)  # 成功・失敗にかかわらず一時ファイルを削除してストレージを解放


class ReviewRequest(BaseModel):
    reviewer_id: str  # レビュアーID（CSVから役割・名前を引く）
    transcript: str   # 評価対象の発表テキスト


class AddReviewerRequest(BaseModel):
    name: str   # レビュアーの名前
    role: str   # 役割キー（ROLE_DICT のキー）


class RenameReviewerRequest(BaseModel):
    name: str   # 新しい名前


@app.get("/reviewers")  # レビュアー一覧を返す
def get_reviewers():
    return load_reviewers()


@app.post("/reviewers")  # レビュアーを新規追加してCSVに保存
def add_reviewer(req: AddReviewerRequest):
    if req.role not in ROLE_DICT:
        raise HTTPException(status_code=400, detail="無効な役割が指定されました。")
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="名前が空です。")
    reviewers = load_reviewers()
    new_reviewer = {"id": uuid.uuid4().hex[:8], "name": req.name.strip(), "role": req.role}
    reviewers.append(new_reviewer)
    save_reviewers(reviewers)
    return new_reviewer


@app.delete("/memories")  # 全レビュアーの記憶をリセット（レビュアー自体は削除しない）
def reset_memories():
    reset_all_memories()
    return {"ok": True}


@app.delete("/reviewers/{reviewer_id}")  # レビュアーをCSVから削除し、関連する記憶も削除
def delete_reviewer(reviewer_id: str):
    reviewers = load_reviewers()
    save_reviewers([r for r in reviewers if r["id"] != reviewer_id])
    delete_reviewer_history(reviewer_id)  # フィードバック履歴・プロファイルを一括削除
    return {"ok": True}


@app.patch("/reviewers/{reviewer_id}")  # レビュアーの名前を変更してCSVに保存
def rename_reviewer(reviewer_id: str, req: RenameReviewerRequest):
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="名前が空です。")
    reviewers = load_reviewers()
    for r in reviewers:
        if r["id"] == reviewer_id:
            r["name"] = req.name.strip()
            break
    else:
        raise HTTPException(status_code=404, detail="レビュアーが見つかりません。")
    save_reviewers(reviewers)
    return {"ok": True}


@app.post("/review")  # POST /review で指定レビュアーの AI にコメントを生成させるルートを定義
async def review(req: ReviewRequest):
    reviewers = load_reviewers()
    reviewer = next((r for r in reviewers if r["id"] == req.reviewer_id), None)
    if reviewer is None:
        raise HTTPException(status_code=404, detail="レビュアーが見つかりません。")
    if not req.transcript.strip():
        raise HTTPException(status_code=400, detail="発表内容が空です。")
    try:
        # このレビュアー自身の過去コメント傾向をプロンプトに反映（初回は None）
        profile = get_reviewer_profile(req.reviewer_id)

        print(f"##### コメント開始 [{reviewer['name']}] #####")
        _start = time.time()
        comment = play_role(reviewer["role"], reviewer["name"], req.transcript, user_profile=profile)
        print(f"##### コメント終了 [{reviewer['name']}] : {time.time() - _start:.1f}s #####")

        # フィードバック保存・プロファイル更新は失敗してもレスポンスを返す
        try:
            save_feedback(
                reviewer_id=req.reviewer_id,
                reviewer_name=reviewer["name"],
                role=reviewer["role"],
                feedback=comment,
                transcript=req.transcript,
            )
            build_reviewer_profile(req.reviewer_id)
        except Exception as hist_exc:
            print(f"##### 履歴保存エラー（無視して続行）: {hist_exc} #####")

        return comment
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"コメント生成に失敗しました: {exc}") from exc


@app.get("/profile/{reviewer_id}")  # レビュアーの記憶サマリーを返す
def get_profile(reviewer_id: str):
    profile = get_reviewer_profile(reviewer_id)
    if profile is None:
        return {}
    result = dict(profile)
    for field in ("strengths_json", "weaknesses_json", "recurring_issues_json",
                  "improved_points_json", "last_advice_json"):
        key = field.replace("_json", "")
        try:
            result[key] = json.loads(profile.get(field, "[]"))
        except Exception:
            result[key] = []
    return result


@app.get("/history/{reviewer_id}")  # レビュアーの直近フィードバック履歴を返す
def get_history(reviewer_id: str):
    return {"feedbacks": get_feedback_by_reviewer(reviewer_id, limit=20)}


@app.post("/analyze")  # POST /analyze で動画を解析してスライド情報と AI コメントを返すルート
async def analyze(video: UploadFile = File(...)):
    if not video.filename:
        raise HTTPException(status_code=400, detail="動画ファイルがありません。")

    suffix = Path(video.filename).suffix.lower()
    if suffix not in VALID_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"対応していない形式です。対応形式: {', '.join(VALID_VIDEO_EXTENSIONS)}",
        )

    job_id = uuid.uuid4().hex[:8]
    video_path: str | None = None
    audio_path: str | None = None

    # 動画を一時ファイルに保存
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=UPLOAD_DIR) as tmp:
        shutil.copyfileobj(video.file, tmp)
        video_path = tmp.name

    try:
        print(f"##### 動画解析開始 [job={job_id}] #####")

        # 1. 音声抽出
        audio_path = extract_audio(video_path, UPLOAD_DIR)

        # 2. Whisper 文字起こし（セグメント付き）
        result = get_model().transcribe(audio_path, language="ja", fp16=False)
        raw_text: str = result.get("text", "").strip()
        segments = [
            {"start": float(s["start"]), "end": float(s["end"]), "text": s["text"]}
            for s in result.get("segments", [])
        ]

        # 3. 全文テキスト推敲（文字起こし直後に校正）
        # print("##### 校正前テキスト（動画）#####")
        # print(raw_text)
        refined_text = brushup_text(raw_text)
        # print("##### 校正後テキスト（動画）#####")
        # print(refined_text)

        # 4. スライド切替検出
        total_duration = get_video_duration(video_path)
        change_times = detect_slide_changes(video_path)
        slides = build_slide_intervals(change_times, total_duration)

        # 5. サムネイル保存
        thumbnail_urls = save_slide_thumbnails(video_path, slides, OUTPUTS_DIR, job_id)
        for i, url in enumerate(thumbnail_urls):
            slides[i]["thumbnail_url"] = url

        # 6. セグメントとスライドを紐づけ
        slide_speech = map_speech_to_slides(segments, slides)

        print(f"##### 動画解析完了 [job={job_id}] スライド数={len(slides)} #####")

        return {
            "full_text": refined_text,
            "segments": segments,
            "slide_speech": slide_speech,
        }

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail="ffmpeg が見つかりません。ffmpeg をインストールして PATH に追加してください。",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"動画解析に失敗しました: {exc}") from exc
    finally:
        if video_path and os.path.exists(video_path):
            os.remove(video_path)
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
