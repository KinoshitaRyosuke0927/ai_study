"""講座の画像(アップロード・一覧・配信・削除)を扱うモジュール。

画像は、講座の説明・問題文・解説の Markdown から ![説明](image:ファイル名) の形で参照する。
受け付ける形式は PNG / JPEG / GIF / WebP のみ(SVG はスクリプトを埋め込めるため受け付けない)。
形式は拡張子だけでなく、ファイル先頭のバイト列でも確認する。
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infra.image_store import get_image_store
from app.models import Course, CourseImage, User
from app.services.course_service import NotFoundError, _viewable

# 画像1枚の上限サイズ
MAX_IMAGE_BYTES = 2 * 1024 * 1024
# ファイル名(英数字で始まり、英数字と . _ - だけ。Markdown の参照にそのまま書けるようにする)
_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
# 拡張子 → 形式
_EXTENSIONS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}


class ImageInputError(Exception):
    """画像のファイル名・形式・サイズに誤りがある(画面にそのまま表示するメッセージを持つ)。"""


def _sniff(data: bytes) -> str | None:
    """
    ファイル先頭のバイト列から画像の形式を判定する

    Args
    -----------------
    - data: bytes,                      ファイルの中身

    Returns
    -----------------
    - content_type: str | None,         画像の形式(対応していなければ None)

    """
    # 形式ごとの先頭バイト列で判定して返却
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def image_key(course_id: int, filename: str) -> str:
    """
    画像の保存先のキーを返す

    Args
    -----------------
    - course_id: int,                   講座 ID
    - filename: str,                    ファイル名

    Returns
    -----------------
    - key: str,                         キー(講座 ID/ファイル名)

    """
    # 講座ごとのフォルダに分けて返却
    return f"{course_id}/{filename}"


def validate_image(filename: str, data: bytes) -> tuple[str, str]:
    """
    画像のファイル名・形式・サイズを確認する

    Args
    -----------------
    - filename: str,                    アップロードされたファイル名(フォルダを含んでもよい)
    - data: bytes,                      ファイルの中身

    Returns
    -----------------
    - name: str,                        保存するファイル名
    - content_type: str,                画像の形式

    """
    # フォルダ部分を除いたファイル名の確認
    name = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not _FILENAME.match(name):
        raise ImageInputError(
            f"ファイル名「{name}」は使えません。半角英数字で始まり、半角英数字と . _ - だけからなる名前にしてください"
        )
    # 拡張子と中身の形式が、対応する画像形式で一致していることを確認
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    expected = _EXTENSIONS.get(ext)
    if expected is None:
        raise ImageInputError("PNG / JPEG / GIF / WebP の画像だけをアップロードできます")
    actual = _sniff(data)
    if actual is None or actual != expected:
        raise ImageInputError(f"「{name}」の中身が拡張子({ext})の画像形式と一致しません")
    # サイズの確認
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageInputError(f"「{name}」が大きすぎます(上限 2MB)")
    # ファイル名と形式を返却
    return name, actual


def add_image(session: Session, course_id: int, filename: str, data: bytes) -> CourseImage:
    """
    講座に画像を追加する(同名の画像は置き換える)

    Args
    -----------------
    - session: Session,                 DB セッション
    - course_id: int,                   講座 ID
    - filename: str,                    ファイル名
    - data: bytes,                      画像の中身

    Returns
    -----------------
    - image: CourseImage,               追加・更新した画像

    """
    # 講座を取得し、ファイル名・形式・サイズを確認
    course = session.get(Course, course_id)
    if course is None:
        raise NotFoundError(course_id)
    name, content_type = validate_image(filename, data)
    # 中身を保存先に書き込む
    get_image_store().put(image_key(course.id, name), data)
    # 一覧に追加(同名があれば更新)
    image = session.scalar(select(CourseImage).where(CourseImage.course_id == course.id, CourseImage.filename == name))
    if image is None:
        image = CourseImage(course_id=course.id, filename=name)
        session.add(image)
    image.content_type = content_type
    image.size = len(data)
    session.flush()
    return image


def delete_image(session: Session, image_id: int) -> None:
    """
    画像を削除する

    Args
    -----------------
    - session: Session,                 DB セッション
    - image_id: int,                    画像 ID

    """
    # 画像を取得して、中身と一覧の両方から削除
    image = session.get(CourseImage, image_id)
    if image is None:
        raise NotFoundError(image_id)
    get_image_store().delete(image_key(image.course_id, image.filename))
    session.delete(image)
    session.flush()


def delete_course_images(course_id: int) -> None:
    """
    講座の画像の中身をまとめて削除する(講座の削除時に呼ぶ。一覧は講座と一緒に削除される)

    Args
    -----------------
    - course_id: int,                   講座 ID

    """
    # 講座のフォルダごと削除
    get_image_store().delete_prefix(f"{course_id}/")


def load_image(session: Session, user: User, slug: str, filename: str) -> tuple[bytes, str]:
    """
    受講画面などで表示する画像を読み込む(閲覧できる講座の画像だけ)

    Args
    -----------------
    - session: Session,                 DB セッション
    - user: User,                       ログイン中ユーザ
    - slug: str,                        講座の識別名
    - filename: str,                    ファイル名

    Returns
    -----------------
    - data: bytes,                      画像の中身
    - content_type: str,                画像の形式

    """
    # 講座と画像を取得(閲覧できない講座の画像は「見つからない」)
    course = session.scalar(select(Course).where(Course.slug == slug))
    if course is None or not _viewable(user, course):
        raise NotFoundError(slug)
    image = session.scalar(select(CourseImage).where(CourseImage.course_id == course.id, CourseImage.filename == filename))
    if image is None:
        raise NotFoundError(filename)
    # 保存先から中身を読み込んで返却
    data = get_image_store().get(image_key(course.id, image.filename))
    if data is None:
        raise NotFoundError(filename)
    return data, image.content_type
