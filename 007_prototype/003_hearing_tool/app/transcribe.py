"""音声の分割と、Azure の gpt-transcribe による文字起こしを行う。

流れ：
    1. 音声を無音の位置で約6分ごとに分ける（ffmpeg）
    2. 分けたものを1つずつ gpt-transcribe に送る（呼び出しの間を21秒以上空ける）
    3. 結果を文ごとの発言として utterances.csv に保存する

分けた音声と各回の結果は data/transcribe_work に残し、途中で失敗しても続きから再開できる。
ffmpeg は imageio-ffmpeg に同梱のものを優先し、なければ PATH の ffmpeg を使う。
"""

import json
import math
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .config import TOOL_ROOT, load_config
from .storage import backup, create_rows, data_dir, delete_rows, read_table

# 1つに分ける長さの目安（秒）と、無音を探す範囲（秒）
CHUNK_SEC = 365.0
SEARCH_WINDOW_SEC = 60.0

# 呼び出しの間隔（秒）。デプロイの上限が1分に3回のため
MIN_CALL_INTERVAL_SEC = 21.0

# 1回の呼び出しにかかる時間の目安（秒）。18分の音声を3分割して約81秒だった実測から
EST_SEC_PER_CALL = 30.0

# 料金の目安（ドル/分）。Azure の公式単価は未確認で、類似モデルの価格からの概算
USD_PER_MIN_LOW = 0.0045
USD_PER_MIN_HIGH = 0.006
JPY_PER_USD = 150

# Azure の API のバージョン（/openai/v1 の経路は 404 になるため、従来型の経路を使う）
API_VERSION = "2025-04-01-preview"

# 文字起こしの対象にする音声や動画の拡張子
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac", ".mp4", ".mov", ".webm"}

# 実行中の処理の状態（回のIDごと）
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


class TranscribeError(Exception):
    """文字起こしの準備や実行に失敗したことを表す。"""


# -------------------------------------------------------------------- ffmpeg


def ffmpeg_path() -> str | None:
    """使える ffmpeg の場所を返す。

    Returns:
        str | None: ffmpeg の実行ファイルのパス。見つからなければ None。
    """
    # imageio-ffmpeg に同梱のものを優先する（利用者がインストールしなくて済む）
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    # なければ PATH の ffmpeg を使う
    return shutil.which("ffmpeg")


def _run_ffmpeg(args: list[str]) -> str:
    """ffmpeg を実行し、ログ（標準エラー）を返す。

    Args:
        args: ffmpeg に渡す引数。

    Returns:
        str: ffmpeg のログ。
    """
    exe = ffmpeg_path()
    if not exe:
        raise TranscribeError("ffmpeg が見つかりません。requirements.txt のパッケージを入れ直してください。")
    result = subprocess.run(
        [exe, "-hide_banner", *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return result.stderr


def get_duration(path: Path) -> float:
    """音声の長さを返す。

    ffprobe は imageio-ffmpeg に含まれないため、ffmpeg のログから読み取る。

    Args:
        path: 音声ファイル。

    Returns:
        float: 長さ（秒）。
    """
    log = _run_ffmpeg(["-i", str(path)])
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", log)
    if not match:
        raise TranscribeError(f"音声の長さを読み取れませんでした：{path.name}")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def detect_silences(path: Path) -> list[tuple[float, float]]:
    """無音の区間を探す。

    Args:
        path: 音声ファイル。

    Returns:
        list[tuple[float, float]]: (開始, 終了) の秒の一覧。
    """
    log = _run_ffmpeg(["-i", str(path), "-af", "silencedetect=noise=-35dB:d=0.4", "-f", "null", "-"])
    starts = [float(v) for v in re.findall(r"silence_start:\s*([\d.]+)", log)]
    ends = [float(v) for v in re.findall(r"silence_end:\s*([\d.]+)", log)]
    return list(zip(starts, ends))


def choose_cut_points(duration: float, silences: list[tuple[float, float]]) -> list[float]:
    """分ける位置を決める。

    均等に分けた位置の前後 SEARCH_WINDOW_SEC の中で、最も近い無音の中央を選ぶ。
    無音がなければ均等な位置で分ける。

    Args:
        duration: 音声の長さ（秒）。
        silences: 無音の区間。

    Returns:
        list[float]: 先頭の 0 と末尾の duration を含む、分ける位置の一覧。
    """
    count = max(1, math.ceil(duration / CHUNK_SEC))
    cuts = [0.0]
    for k in range(1, count):
        # 均等に分けた位置の近くにある無音を探す
        target = duration * k / count
        near = [((s + e) / 2) for s, e in silences if abs((s + e) / 2 - target) <= SEARCH_WINDOW_SEC]
        cuts.append(min(near, key=lambda m: abs(m - target)) if near else target)
    cuts.append(duration)
    return cuts


def estimate_chunks(duration: float) -> int:
    """分ける数を返す。

    Args:
        duration: 音声の長さ（秒）。

    Returns:
        int: 分ける数。
    """
    return max(1, math.ceil(duration / CHUNK_SEC))


# -------------------------------------------------------------------- Azure


def _load_env(path: Path) -> dict[str, str]:
    """.env ファイルを読み込む。

    Args:
        path: .env のパス。

    Returns:
        dict[str, str]: 変数名ごとの値。
    """
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        # 「名前=値」の行だけを読む（コメントと空行は飛ばす）
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def azure_settings() -> dict:
    """Azure の接続情報を読み込む。

    Returns:
        dict: ok（使えるか）、message（使えないときの理由）、env_file（.env の場所）と、
            使えるときは endpoint、key、model。
    """
    # 設定から .env の場所を決める
    config = load_config()
    env_path = Path(config["azure_env_file"])
    if not env_path.is_absolute():
        env_path = (TOOL_ROOT / env_path).resolve()
    if not env_path.exists():
        return {"ok": False, "message": f".env が見つかりません：{env_path}", "env_file": str(env_path)}

    # 必要な値がそろっているか確かめる
    env = _load_env(env_path)
    missing = [k for k in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_KEY") if not env.get(k)]
    if missing:
        return {"ok": False, "message": f".env に {'、'.join(missing)} がありません。", "env_file": str(env_path)}
    return {
        "ok": True, "message": "", "env_file": str(env_path),
        "endpoint": env["AZURE_OPENAI_ENDPOINT"], "key": env["AZURE_OPENAI_KEY"],
        "model": env.get("AZURE_TRANSCRIBE_MODEL", "gpt-transcribe"),
    }


def _make_client(settings: dict):
    """Azure OpenAI のクライアントを作る。

    Args:
        settings: azure_settings() の結果。

    Returns:
        AzureOpenAI: クライアント。
    """
    from openai import AzureOpenAI

    # エンドポイントからリソース名を取り出し、従来型の経路を組み立てる
    match = re.match(r"https://([^.]+)\.", settings["endpoint"])
    if not match:
        raise TranscribeError("AZURE_OPENAI_ENDPOINT の形式を読み取れませんでした。")
    return AzureOpenAI(
        azure_endpoint=f"https://{match.group(1)}.openai.azure.com",
        api_key=settings["key"],
        api_version=API_VERSION,
        timeout=300,
        max_retries=0,
    )


def _transcribe_file(client, model: str, path: Path, prompt: str) -> str:
    """1つの音声を文字起こしする。

    Args:
        client: AzureOpenAI のクライアント。
        model: デプロイ名。
        path: 音声ファイル。
        prompt: 用語のヒント（空なら渡さない）。

    Returns:
        str: 文字起こしの結果。
    """
    with path.open("rb") as audio:
        kwargs = {"model": model, "file": audio, "language": "ja"}
        if prompt:
            kwargs["prompt"] = prompt
        result = client.audio.transcriptions.create(**kwargs)
    return result.text


# -------------------------------------------------------------------- 見積もりと実行


def audio_path_of(session: dict) -> Path | None:
    """回の音声ファイルの場所を返す。

    Args:
        session: sessions の行。

    Returns:
        Path | None: 音声ファイル。名前が空、または不正なら None。
    """
    name = (session.get("audio_file") or "").strip()
    # フォルダをまたぐ名前は受け付けない
    if not name or Path(name).name != name:
        return None
    return data_dir() / "audio" / name


def _work_dir(session: dict, audio: Path) -> Path:
    """分けた音声と結果を置くフォルダを返す。

    Args:
        session: sessions の行。
        audio: 音声ファイル。

    Returns:
        Path: 作業フォルダ（回と音声の名前ごと）。
    """
    return data_dir() / "transcribe_work" / session["session_id"] / audio.stem


def _find_session(session_id: str) -> dict:
    """回を探す。

    Args:
        session_id: 回のID。

    Returns:
        dict: sessions の行。なければ TranscribeError を送出する。
    """
    session = next((s for s in read_table("sessions") if s["session_id"] == session_id), None)
    if session is None:
        raise TranscribeError("回が見つかりません。")
    return session


def term_prompt() -> str:
    """用語集から、モデルに渡すヒントの文を作る。

    Returns:
        str: 例「用語：砂盃さん、石井さん、MemMen」。
    """
    terms = [t["term"] for t in read_table("terms") if t["term"]]
    return "用語：" + "、".join(terms) if terms else ""


def estimate(session_id: str) -> dict:
    """文字起こしの見積もりを返す。Azure は呼ばない。

    Args:
        session_id: 回のID。

    Returns:
        dict: 音声の有無と長さ、分ける数、呼び出しの回数、料金と時間の目安、
            済んでいる分の数、既存の発言の数、ffmpeg と Azure の準備の状態。
    """
    session = _find_session(session_id)
    audio = audio_path_of(session)
    azure = azure_settings()
    result = {
        "audio_file": session.get("audio_file", ""),
        "audio_exists": bool(audio and audio.exists()),
        "ffmpeg": bool(ffmpeg_path()),
        "azure_ok": azure["ok"],
        "azure_message": azure["message"],
        "model": azure.get("model", ""),
        "existing_utterances": sum(1 for u in read_table("utterances") if u["session_id"] == session_id),
        "job": job_status(session_id),
    }
    if not result["audio_exists"] or not result["ffmpeg"]:
        return result

    # 長さと分ける数から、呼び出しの回数と目安を計算する
    duration = get_duration(audio)
    chunks = estimate_chunks(duration)
    work = _work_dir(session, audio)
    done = sum(1 for i in range(chunks) if (work / f"part{i}.json").exists())
    calls = chunks - done
    minutes = duration / 60 * calls / chunks
    result.update({
        "duration_sec": round(duration, 1),
        "chunks": chunks,
        "done_chunks": done,
        "calls": calls,
        "cost_usd": [round(minutes * USD_PER_MIN_LOW, 3), round(minutes * USD_PER_MIN_HIGH, 3)],
        "cost_jpy": [round(minutes * USD_PER_MIN_LOW * JPY_PER_USD), round(minutes * USD_PER_MIN_HIGH * JPY_PER_USD)],
        "est_sec": round(calls * EST_SEC_PER_CALL + 10),
    })
    return result


def job_status(session_id: str) -> dict:
    """実行中、または最後に実行した処理の状態を返す。

    Args:
        session_id: 回のID。

    Returns:
        dict: state（idle、running、done、error）、message、done、total。
    """
    with _jobs_lock:
        return dict(_jobs.get(session_id, {"state": "idle", "message": "", "done": 0, "total": 0}))


def _set_job(session_id: str, **values) -> None:
    """処理の状態を更新する。

    Args:
        session_id: 回のID。
        **values: 更新する項目。

    Returns:
        None
    """
    with _jobs_lock:
        _jobs.setdefault(session_id, {"state": "idle", "message": "", "done": 0, "total": 0}).update(values)


def start(session_id: str, use_prompt: bool, user: str) -> dict:
    """文字起こしを別のスレッドで始める。

    Args:
        session_id: 回のID。
        use_prompt: 用語集をヒントとして渡すなら True。
        user: 更新者の名前。

    Returns:
        dict: 開始時点の状態。
    """
    # 同じ回の処理が実行中なら始めない
    if job_status(session_id)["state"] == "running":
        raise TranscribeError("この回の文字起こしは実行中です。")

    # 準備ができているか確かめる
    session = _find_session(session_id)
    audio = audio_path_of(session)
    if not audio or not audio.exists():
        raise TranscribeError("音声ファイルが data/audio にありません。")
    settings = azure_settings()
    if not settings["ok"]:
        raise TranscribeError(settings["message"])

    _set_job(session_id, state="running", message="音声を分けています。", done=0, total=0)
    thread = threading.Thread(
        target=_run, args=(session, audio, settings, use_prompt, user), daemon=True,
    )
    thread.start()
    return job_status(session_id)


def _run(session: dict, audio: Path, settings: dict, use_prompt: bool, user: str) -> None:
    """文字起こしの本体（別のスレッドで動く）。

    Args:
        session: sessions の行。
        audio: 音声ファイル。
        settings: azure_settings() の結果。
        use_prompt: 用語集をヒントとして渡すなら True。
        user: 更新者の名前。

    Returns:
        None。結果は utterances.csv に保存し、状態は _jobs に記録する。
    """
    session_id = session["session_id"]
    try:
        # 分ける位置を決める（前回の位置が残っていればそれを使う）
        work = _work_dir(session, audio)
        work.mkdir(parents=True, exist_ok=True)
        cuts_file = work / "cuts.json"
        if cuts_file.exists():
            cuts = json.loads(cuts_file.read_text(encoding="utf-8"))
        else:
            duration = get_duration(audio)
            cuts = choose_cut_points(duration, detect_silences(audio))
            cuts_file.write_text(json.dumps(cuts), encoding="utf-8")

        # 音声を分ける（ほかの形式でも扱えるよう、モノラルの mp3 に変換する）
        parts = []
        for i in range(len(cuts) - 1):
            part = work / f"part{i}.mp3"
            if not part.exists():
                _run_ffmpeg(["-y", "-ss", f"{cuts[i]:.2f}", "-t", f"{cuts[i + 1] - cuts[i]:.2f}", "-i", str(audio),
                             "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", str(part)])
            if not part.exists():
                raise TranscribeError(f"音声を分けられませんでした（{i + 1}つ目）。")
            parts.append(part)
        _set_job(session_id, total=len(parts))

        # 1つずつ文字起こしする（済んだ分は結果を読み込む）
        client = _make_client(settings)
        prompt = term_prompt() if use_prompt else ""
        texts = []
        last_call = 0.0
        for i, part in enumerate(parts):
            cache = work / f"part{i}.json"
            if cache.exists():
                texts.append(json.loads(cache.read_text(encoding="utf-8"))["text"])
                _set_job(session_id, done=i + 1, message=f"{i + 1}/{len(parts)} は前回の結果を使いました。")
                continue

            # 呼び出しの間隔を空ける
            wait = MIN_CALL_INTERVAL_SEC - (time.time() - last_call)
            if last_call and wait > 0:
                _set_job(session_id, message=f"{i + 1}/{len(parts)} の前に{wait:.0f}秒待っています。")
                time.sleep(wait)

            _set_job(session_id, message=f"{i + 1}/{len(parts)} を文字起こししています。")
            last_call = time.time()
            text = _transcribe_file(client, settings["model"], part, prompt)
            cache.write_text(json.dumps({"text": text, "start": cuts[i], "end": cuts[i + 1]}, ensure_ascii=False),
                             encoding="utf-8")
            texts.append(text)
            _set_job(session_id, done=i + 1)

        # 結果を発言として保存する
        count = _save_utterances(session_id, cuts, texts, user)
        _set_job(session_id, state="done", message=f"{count}件の発言を保存しました。")
    except Exception as exc:  # 画面に理由を出すため、すべての失敗を記録する
        _set_job(session_id, state="error", message=f"失敗しました：{exc}（済んだ分は保存されています）")


def split_sentences(text: str) -> list[str]:
    """文字起こしの結果を文に分ける。

    Args:
        text: 文字起こしの結果。

    Returns:
        list[str]: 文の一覧（。？！ の後ろで分ける）。
    """
    pieces = re.split(r"(?<=[。？！?!])", text.replace("\r", "").replace("\n", ""))
    return [p.strip() for p in pieces if p.strip()]


def _save_utterances(session_id: str, cuts: list[float], texts: list[str], user: str) -> int:
    """文字起こしの結果を、文ごとの発言として保存する。

    既存の発言があれば、バックアップしてから置き換える。

    Args:
        session_id: 回のID。
        cuts: 分けた位置。
        texts: 分けた音声ごとの結果。
        user: 更新者の名前。

    Returns:
        int: 保存した発言の数。
    """
    # 既存の発言を置き換える前にバックアップする
    existing = {u["utterance_id"] for u in read_table("utterances") if u["session_id"] == session_id}
    if existing:
        backup("transcribe")
        delete_rows("utterances", existing)

    # 文ごとに発言を作る（時刻は、分けた音声の開始位置）
    rows = []
    for i, text in enumerate(texts):
        for sentence in split_sentences(text):
            rows.append({
                "session_id": session_id,
                "order": str(len(rows) + 1),
                "speaker": "",
                "text": sentence,
                "start_sec": f"{cuts[i]:.1f}",
                "review_status": "未推敲",
                "excluded": "0",
            })
    create_rows("utterances", rows, user)
    return len(rows)


def list_audio_files() -> list[dict]:
    """data/audio にある音声や動画の一覧を返す。

    Returns:
        list[dict]: name（ファイル名）と size_mb（大きさ）。
    """
    folder = data_dir() / "audio"
    return [
        {"name": p.name, "size_mb": round(p.stat().st_size / 1024 / 1024, 1)}
        for p in sorted(folder.glob("*"))
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
    ]
