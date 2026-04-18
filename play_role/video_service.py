from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

import cv2
import numpy as np

# ---- 定数 ----
FRAME_INTERVAL_SEC: float = 0.5   # フレーム比較の間隔（秒）
MAD_THRESHOLD: float = 25.0       # 平均絶対差分の閾値（これ以上でスライド切替候補）
MERGE_GAP_SEC: float = 1.5        # 近接した切替候補をマージする間隔（秒）
THUMBNAIL_WIDTH: int = 640        # サムネイル保存時の横幅（px）

# scikit-image が利用可能な場合のみ SSIM を有効化
try:
    from skimage.metrics import structural_similarity as _ssim
    _SSIM_AVAILABLE: bool = True
    SSIM_THRESHOLD: float = 0.85  # SSIM がこれ未満でスライド切替候補
except ImportError:
    _SSIM_AVAILABLE = False


def extract_audio(video_path: str, output_dir: Path) -> str:
    """
    ffmpeg で動画から 16kHz モノラル WAV を抽出し、出力ファイルパスを返す。

    Raises
    ------
    FileNotFoundError
        ffmpeg が PATH に存在しない場合
    subprocess.CalledProcessError
        ffmpeg が終了コード非 0 で終了した場合
    """
    audio_path = str(output_dir / f"{uuid.uuid4().hex}.wav")
    subprocess.run(
        [
            "ffmpeg", "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            audio_path,
            "-y",
        ],
        check=True,
        capture_output=True,
    )
    return audio_path


def get_video_duration(video_path: str) -> float:
    """動画の総時間（秒）を返す。"""
    cap = cv2.VideoCapture(video_path)
    fps: float = cap.get(cv2.CAP_PROP_FPS) or 1.0
    frame_count: float = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    cap.release()
    return frame_count / fps


def detect_slide_changes(video_path: str) -> list[float]:
    """
    OpenCV でフレーム差分を計算してスライド切替タイムスタンプの一覧を返す。
    scikit-image が利用可能な場合は SSIM も併用して精度を向上させる。
    近接した候補は MERGE_GAP_SEC でマージする。
    """
    cap = cv2.VideoCapture(video_path)
    fps: float = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_step: int = max(1, int(fps * FRAME_INTERVAL_SEC))

    candidates: list[float] = []
    prev_gray: np.ndarray | None = None
    frame_idx: int = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_step == 0:
            gray = cv2.resize(
                cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY),
                (320, 240),
            )

            if prev_gray is not None:
                mad: float = float(
                    np.mean(np.abs(gray.astype(np.float32) - prev_gray.astype(np.float32)))
                )
                is_change: bool = mad > MAD_THRESHOLD

                # SSIM が使える場合、MAD が閾値未満でも SSIM で再確認
                if _SSIM_AVAILABLE and not is_change:
                    sim: float = float(_ssim(gray, prev_gray))  # type: ignore[name-defined]
                    is_change = sim < SSIM_THRESHOLD

                if is_change:
                    candidates.append(frame_idx / fps)

            prev_gray = gray

        frame_idx += 1

    cap.release()

    # 近接した候補をマージ（直前の採用候補から MERGE_GAP_SEC 以内は無視）
    merged: list[float] = []
    for t in sorted(candidates):
        if not merged or t - merged[-1] >= MERGE_GAP_SEC:
            merged.append(round(t, 2))

    return merged


def build_slide_intervals(
    change_times: list[float],
    total_duration: float,
) -> list[dict]:
    """切替タイムスタンプからスライド区間リストを作成する。"""
    boundaries = [0.0] + change_times + [round(total_duration, 2)]
    return [
        {
            "slide_index": i + 1,
            "start": round(boundaries[i], 2),
            "end": round(boundaries[i + 1], 2),
        }
        for i in range(len(boundaries) - 1)
    ]


def save_slide_thumbnails(
    video_path: str,
    slides: list[dict],
    output_dir: Path,
    job_id: str,
) -> list[str | None]:
    """
    各スライド区間の先頭フレームをサムネイル画像として保存し、
    `/outputs/<ファイル名>` 形式の URL リストを返す。
    """
    cap = cv2.VideoCapture(video_path)
    fps: float = cap.get(cv2.CAP_PROP_FPS) or 30.0
    urls: list[str | None] = []

    for slide in slides:
        frame_no = int(slide["start"] * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
        ret, frame = cap.read()
        if ret:
            h, w = frame.shape[:2]
            new_h = int(h * THUMBNAIL_WIDTH / w)
            thumb = cv2.resize(frame, (THUMBNAIL_WIDTH, new_h))
            fname = f"slide_{job_id}_{slide['slide_index']}.jpg"
            cv2.imwrite(str(output_dir / fname), thumb)
            urls.append(f"/outputs/{fname}")
        else:
            urls.append(None)

    cap.release()
    return urls


def map_speech_to_slides(
    segments: list[dict],
    slides: list[dict],
) -> list[dict]:
    """
    Whisper セグメントをスライド区間に紐づけてスライドごとの発話内容を返す。
    セグメントの start が区間 [start, end) に含まれる場合にそのスライドに属するとみなす。
    """
    result: list[dict] = []
    for slide in slides:
        texts = [
            seg["text"].strip()
            for seg in segments
            if slide["start"] <= seg["start"] < slide["end"]
        ]
        result.append({
            "slide_index": slide["slide_index"],
            "start": slide["start"],
            "end": slide["end"],
            "duration_sec": round(slide["end"] - slide["start"], 2),
            "spoken_text": " ".join(texts),
            "thumbnail_url": slide.get("thumbnail_url"),
        })
    return result
