"""講座の画像(アップロード・配信・権限・取り込み)のテスト。"""

import base64
import json
import shutil

import pytest
from fastapi.testclient import TestClient

from tests.conftest import SAMPLE_COURSE

# 1x1 の PNG 画像
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


@pytest.fixture()
def admin(seeded):
    """管理者でログイン済みのクライアント。"""
    from app.main import app

    c = TestClient(app)
    assert c.post("/api/auth/login", json={"login_name": "admin", "password": "pw-admin"}).status_code == 200
    return c


def _new_course(c: TestClient, slug: str) -> int:
    """下書きの講座を作って ID を返す。"""
    info = {"slug": slug, "title": "画像の講座", "summary": "概要", "level": "basic"}
    return c.post("/api/authoring/courses", json=info).json()["id"]


def test_upload_and_view_image(admin, client):
    cid = _new_course(admin, "img-course")
    res = admin.post(f"/api/authoring/courses/{cid}/images", files={"file": ("hist_a.png", PNG, "image/png")})
    assert res.status_code == 200
    images = res.json()["images"]
    assert [(i["filename"], i["size"]) for i in images] == [("hist_a.png", len(PNG))]
    assert images[0]["url"] == "/api/courses/img-course/images/hist_a.png"
    # 作成者(管理者)は表示できる
    got = admin.get(images[0]["url"])
    assert got.status_code == 200 and got.content == PNG and got.headers["content-type"] == "image/png"
    assert got.headers["x-content-type-options"] == "nosniff"
    # 下書きの講座の画像は、ほかのユーザからは見えない
    assert client.get(images[0]["url"]).status_code == 404
    # 同名は置き換え、削除もできる
    res = admin.post(f"/api/authoring/courses/{cid}/images", files={"file": ("hist_a.png", PNG + b"x", "image/png")})
    assert [i["size"] for i in res.json()["images"]] == [len(PNG) + 1]
    assert admin.delete(f"/api/authoring/images/{images[0]['id']}").status_code == 204
    assert admin.get(images[0]["url"]).status_code == 404


def test_reject_invalid_images(admin):
    cid = _new_course(admin, "img-bad")
    url = f"/api/authoring/courses/{cid}/images"
    # SVG・拡張子と中身の不一致・使えないファイル名・2MB 超は受け付けない
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    cases = [
        (("a.svg", svg, "image/svg+xml"), "PNG / JPEG"),
        (("a.png", b"GIF89a....", "image/png"), "一致しません"),
        (("図1.png", PNG, "image/png"), "使えません"),
        (("big.png", PNG + b"0" * (2 * 1024 * 1024), "image/png"), "2MB"),
    ]
    for file, message in cases:
        res = admin.post(url, files={"file": file})
        assert res.status_code == 400 and message in res.json()["detail"], file[0]


def test_others_cannot_upload(client, admin):
    cid = _new_course(admin, "img-other")
    # 他人の講座には画像を追加できない(講座の存在も分からない)
    res = client.post(f"/api/authoring/courses/{cid}/images", files={"file": ("a.png", PNG, "image/png")})
    assert res.status_code == 404


def test_import_course_with_images(tmp_path, admin):
    from app.infra import db
    from app.services.notebook_import import import_course

    # サンプル講座に images/ を足し、単元の説明に images/ への参照を書く
    course_dir = tmp_path / "course"
    shutil.copytree(SAMPLE_COURSE, course_dir)
    (course_dir / "images").mkdir()
    (course_dir / "images" / "fig1.png").write_bytes(PNG)
    meta = json.loads((course_dir / "course.json").read_text(encoding="utf-8"))
    meta["slug"] = "with-images"
    (course_dir / "course.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    first = course_dir / meta["units"][0]["file"]
    nb = json.loads(first.read_text(encoding="utf-8"))
    nb["cells"][0]["source"] = ["# データの種類\n", "概要\n\n", "![図](images/fig1.png)"]
    first.write_text(json.dumps(nb, ensure_ascii=False), encoding="utf-8")
    with db.new_session() as session:
        import_course(session, course_dir)
        session.commit()
    # 参照は image: に読み替えられ、画像も登録されている
    editor = admin.get("/api/authoring/courses").json()
    cid = next(c["id"] for c in editor if c["slug"] == "with-images")
    detail = admin.get(f"/api/authoring/courses/{cid}").json()
    assert detail["units"][0]["summary"].endswith("![図](image:fig1.png)")
    assert [i["filename"] for i in detail["images"]] == ["fig1.png"]
    assert admin.get("/api/courses/with-images/images/fig1.png").content == PNG
    # 講座を削除すると画像も表示できなくなる
    assert admin.delete(f"/api/authoring/courses/{cid}").status_code == 204
    assert admin.get("/api/courses/with-images/images/fig1.png").status_code == 404
