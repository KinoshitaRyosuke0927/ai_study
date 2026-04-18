import os
import ffmpeg


def extract_keyframes(video_path: str, output_dir: str, threshold: float = 0.3) -> list[str]:
    """
    FFmpegのsceneフィルタを使って画面変化が大きいフレームのみ抽出する。

    引数:
        video_path: 入力動画ファイルパス
        output_dir: フレーム画像の出力ディレクトリ
        threshold: シーン変化の閾値 (0.0-1.0)

    戻り値:
        抽出されたフレーム画像のパスリスト（時系列順）
    """
    os.makedirs(output_dir, exist_ok=True)
    output_pattern = os.path.join(output_dir, "frame_%04d.jpg")

    def _run_extraction(thresh: float) -> list[str]:
        try:
            (
                ffmpeg
                .input(video_path)
                .filter("select", f"gt(scene,{thresh})")
                .filter("scale", "1280", "-1")
                .output(
                    output_pattern,
                    vsync="vfr",
                    format="image2",
                    **{"q:v": "2"},
                )
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
        except ffmpeg.Error:
            return []

        frames = sorted([
            os.path.join(output_dir, f)
            for f in os.listdir(output_dir)
            if f.startswith("frame_") and f.endswith(".jpg")
        ])
        return frames

    frames = _run_extraction(threshold)

    # フレームが0枚の場合は threshold を 0.1 に下げて再試行
    if not frames:
        frames = _run_extraction(0.1)

    # 最大30枚に制限（コスト管理）
    max_frames = int(os.getenv("MAX_FRAMES", "30"))
    if len(frames) > max_frames:
        step = len(frames) / max_frames
        frames = [frames[int(i * step)] for i in range(max_frames)]

    return frames


def get_video_metadata(video_path: str) -> dict:
    """
    ffprobeを使って動画のメタデータ（時間、解像度、FPS）を取得する。
    """
    try:
        probe = ffmpeg.probe(video_path)
        video_stream = next(
            (s for s in probe["streams"] if s["codec_type"] == "video"),
            None,
        )
        if video_stream is None:
            return {}

        duration = float(probe["format"].get("duration", 0))
        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))

        fps_str = video_stream.get("r_frame_rate", "0/1")
        num, den = fps_str.split("/")
        fps = float(num) / float(den) if float(den) != 0 else 0.0

        return {
            "duration": duration,
            "width": width,
            "height": height,
            "fps": fps,
        }
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# PHASE 2 拡張予定（現在は未実装）
# ---------------------------------------------------------------------------
# def extract_audio_transcript(video_path: str) -> str:
#     """Whisper音声認識で動画の音声をテキスト化する"""
#     import whisper
#     model = whisper.load_model("base")
#     result = model.transcribe(video_path)
#     return result["text"]
#
# def detect_cursor_positions(frame_paths: list[str]) -> list[tuple[int, int]]:
#     """OpenCVでカーソル位置を検出する"""
#     import cv2
#     positions = []
#     for path in frame_paths:
#         img = cv2.imread(path)
#         # カーソル検出ロジック
#         positions.append((0, 0))
#     return positions
