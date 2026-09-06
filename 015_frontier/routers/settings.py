"""実行時設定(データ取得に関する設定 / acquisition_settings.json)の取得・保存。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from viewers.options import (
    check_github_path,
    check_github_repo,
    check_growi_path,
    list_mattermost_channels,
    list_trello_boards,
)
from config.runtime import (
    RuntimeConfig,
    load_runtime_config,
    save_runtime_config,
)
from config.settings import get_settings

router = APIRouter()


class SettingsBody(BaseModel):
    """/api/settings (POST) のリクエストボディ。"""

    since_date: str | None = None  # "YYYY-MM-DD" または null
    mattermost_channel_ids: list[str] = []
    trello_board_ids: list[str] = []
    github_repo: str = ""          # "owner/repo" またはリポジトリ名。空可
    github_design_path: str = ""   # リポジトリからの相対パス(設計書フォルダ)。空可
    growi_page_path: str = ""      # "/projects/foo"。空可


@router.get("/api/settings")
def api_get_settings() -> dict[str, Any]:
    """現在の実行時設定 + 選択肢(Mattermost チャンネル / Trello ボード)を返す。

    選択肢は設定画面の表示時に `.env` のトークンで都度取得する。
    """
    settings = get_settings()
    rc = load_runtime_config()
    channels, mm_err = list_mattermost_channels(settings)
    boards, trello_err = list_trello_boards(settings)
    return {
        "config": rc.to_api_dict(),
        "options": {
            "mattermost": {"channels": channels, "error": mm_err},
            "trello": {"boards": boards, "error": trello_err},
        },
    }


@router.post("/api/settings")
def api_save_settings(body: SettingsBody) -> dict[str, Any]:
    """実行時設定を acquisition_settings.json へ保存する。

    GitHub のリポジトリ名称 / 設計書パス、参照する Wiki のページは、保存時に
    `.env` の Git アカウント情報・GROWI トークンで実際にアクセスできるか確認する。
    確認に失敗した場合はエラーを返し、保存しない(422)。
    """
    from datetime import date as _date

    settings = get_settings()

    since_date = None
    if body.since_date:
        try:
            since_date = _date.fromisoformat(body.since_date)
        except ValueError:
            raise HTTPException(status_code=422, detail="since_date は YYYY-MM-DD 形式")

    # --- アクセス確認(GitHub リポジトリ / 設計書パス / GROWI パス)---
    field_errors: dict[str, str] = {}
    github_repo = body.github_repo.strip()
    github_design_path = body.github_design_path.strip().strip("/")
    growi_page_path = body.growi_page_path.strip()

    if github_repo:
        resolved, err = check_github_repo(settings, github_repo)
        if err:
            field_errors["github_repo"] = err
        else:
            github_repo = resolved  # 解決した owner/repo を保存する

    # 設計書パスはリポジトリが有効なときだけ、その配下に存在するか確認する
    if github_design_path and "github_repo" not in field_errors:
        err = check_github_path(settings, github_repo, github_design_path)
        if err:
            field_errors["github_design_path"] = err

    if growi_page_path:
        _count, err = check_growi_path(settings, growi_page_path)
        if err:
            field_errors["growi_page_path"] = err

    if field_errors:
        # 保存は行わず、どの項目でアクセスできなかったかを返す
        raise HTTPException(
            status_code=422,
            detail={"message": "アクセス確認に失敗したため保存しませんでした", "errors": field_errors},
        )

    rc = RuntimeConfig(
        since_date=since_date,
        mattermost_channel_ids=[c for c in body.mattermost_channel_ids if c],
        trello_board_ids=[b for b in body.trello_board_ids if b],
        github_repo=github_repo,
        github_design_path=github_design_path,
        growi_page_path=growi_page_path,
    )
    save_runtime_config(rc)
    return {"status": "saved", "config": rc.to_api_dict()}
