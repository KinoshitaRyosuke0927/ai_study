"""文字起こしと推敲の API。"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import transcribe, utterance_ops
from ..config import load_config
from ..storage import data_dir

router = APIRouter(prefix="/api")


class StartTranscribe(BaseModel):
    """文字起こしの開始の指示を受け取る。"""

    confirm: bool = False
    use_prompt: bool = False


class UtteranceTarget(BaseModel):
    """操作する発言を受け取る。"""

    utterance_id: str = ""
    position: int = 0


class ReplaceText(BaseModel):
    """文字の置き換えの指示を受け取る。"""

    wrong: str
    right: str
    utterance_id: str = ""


class BulkUpdate(BaseModel):
    """発言のまとめての更新を受け取る。"""

    values: dict
    utterance_ids: list[str] | None = None


def _user() -> str:
    """更新者の名前を返す。

    Returns:
        str: config.json の user_name。
    """
    return load_config()["user_name"]


def _call(func, *args):
    """発言の操作を呼び、失敗を画面に出せる形にする。

    Args:
        func: utterance_ops の関数。
        *args: 関数に渡す引数。

    Returns:
        object: 関数の戻り値。
    """
    try:
        return func(*args)
    except utterance_ops.UtteranceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/audio-files")
def get_audio_files() -> dict:
    """data/audio にある音声や動画の一覧を返す。

    Returns:
        dict: files（ファイル名と大きさの一覧）。
    """
    return {"files": transcribe.list_audio_files()}


@router.get("/audio/{name}")
def get_audio(name: str) -> FileResponse:
    """音声ファイルを返す（推敲画面での再生に使う）。

    Args:
        name: data/audio の中のファイル名。

    Returns:
        FileResponse: 音声ファイル。
    """
    # フォルダをまたぐ名前は受け付けない
    if Path(name).name != name:
        raise HTTPException(status_code=400, detail="ファイル名が正しくありません。")
    path = data_dir() / "audio" / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="音声ファイルがありません。")
    return FileResponse(path)


@router.get("/sessions/{session_id}/transcribe/estimate")
def get_estimate(session_id: str) -> dict:
    """文字起こしの見積もりを返す。Azure は呼ばない。

    Args:
        session_id: 回のID。

    Returns:
        dict: transcribe.estimate の結果。
    """
    try:
        return transcribe.estimate(session_id)
    except transcribe.TranscribeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/sessions/{session_id}/transcribe")
def post_transcribe(session_id: str, body: StartTranscribe) -> dict:
    """文字起こしを始める。Azure のモデルを呼ぶため、画面で確認した後だけ受け付ける。

    Args:
        session_id: 回のID。
        body: 確認の有無と、用語のヒントを渡すかどうか。

    Returns:
        dict: 開始時点の状態。
    """
    if not body.confirm:
        raise HTTPException(status_code=400, detail="見積もりを確認してから実行してください。")
    try:
        return transcribe.start(session_id, body.use_prompt, _user())
    except transcribe.TranscribeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/sessions/{session_id}/transcribe/status")
def get_transcribe_status(session_id: str) -> dict:
    """文字起こしの進み具合を返す。

    Args:
        session_id: 回のID。

    Returns:
        dict: transcribe.job_status の結果。
    """
    return transcribe.job_status(session_id)


@router.post("/sessions/{session_id}/utterances/merge")
def post_merge(session_id: str, body: UtteranceTarget) -> dict:
    """発言を1つ前の発言につなげる。

    Args:
        session_id: 回のID。
        body: つなげる発言。

    Returns:
        dict: 空。
    """
    _call(utterance_ops.merge_with_previous, session_id, body.utterance_id, _user())
    return {}


@router.post("/sessions/{session_id}/utterances/merge-speakers")
def post_merge_speakers(session_id: str) -> dict:
    """続けて同じ発言者が話している発言をまとめる。

    Args:
        session_id: 回のID。

    Returns:
        dict: merged（減った発言の数）。
    """
    return {"merged": _call(utterance_ops.merge_same_speakers, session_id, _user())}


@router.post("/sessions/{session_id}/utterances/split")
def post_split(session_id: str, body: UtteranceTarget) -> dict:
    """発言を2つに分ける。

    Args:
        session_id: 回のID。
        body: 分ける発言と位置。

    Returns:
        dict: 空。
    """
    _call(utterance_ops.split_utterance, session_id, body.utterance_id, body.position, _user())
    return {}


@router.post("/sessions/{session_id}/utterances/insert")
def post_insert(session_id: str, body: UtteranceTarget) -> dict:
    """発言の直後に空の発言を入れる。

    Args:
        session_id: 回のID。
        body: この発言の直後に入れる（空なら先頭）。

    Returns:
        dict: 入れた発言。
    """
    return _call(utterance_ops.insert_after, session_id, body.utterance_id, _user())


@router.post("/sessions/{session_id}/utterances/replace")
def post_replace(session_id: str, body: ReplaceText) -> dict:
    """発言の中の文字を置き換える。

    Args:
        session_id: 回のID。
        body: 置き換える前と後の文字、対象の発言（空なら回のすべて）。

    Returns:
        dict: replaced（置き換えた発言の数）。
    """
    return {"replaced": _call(utterance_ops.replace_text, session_id, body.wrong, body.right, _user(),
                              body.utterance_id)}


@router.post("/sessions/{session_id}/utterances/bulk")
def post_bulk(session_id: str, body: BulkUpdate) -> dict:
    """発言をまとめて更新する。

    Args:
        session_id: 回のID。
        body: 変更する値と対象の発言。

    Returns:
        dict: updated（更新した発言の数）。
    """
    return {"updated": _call(utterance_ops.bulk_update, session_id, body.values, _user(), body.utterance_ids)}
