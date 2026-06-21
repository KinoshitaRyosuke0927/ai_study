import os
import sys
import re
import configparser
import requests
from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv


def get_bundle_path() -> str:
    """templates / static の格納先を返す。
    PyInstaller 6+ の onedir では _internal/ 配下 (sys._MEIPASS) に置かれる。"""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def get_config_path() -> str:
    """.env / settings.ini の格納先を返す。
    exe と同じディレクトリに置いてユーザーが編集できるようにする。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BUNDLE_PATH = get_bundle_path()
CONFIG_PATH = get_config_path()

load_dotenv(os.path.join(CONFIG_PATH, ".env"))

app = Flask(
    __name__,
    template_folder=os.path.join(BUNDLE_PATH, "templates"),
    static_folder=os.path.join(BUNDLE_PATH, "static"),
)

TRELLO_API_KEY = os.environ.get("TRELLO_API_KEY")
TRELLO_TOKEN = os.environ.get("TRELLO_TOKEN")
TRELLO_API_BASE = "https://api.trello.com/1"


def load_settings() -> dict:
    """settings.ini を読み込んで辞書で返す。ファイルがない場合は空辞書"""
    config = configparser.ConfigParser()
    config_path = os.path.join(CONFIG_PATH, "settings.ini")
    if not os.path.exists(config_path):
        print("[警告] settings.ini が見つかりません。画面からの手動入力が必要です。")
        return {}
    config.read(config_path, encoding="utf-8")
    return {
        "view_board_url":      config.get("view",   "board_url",    fallback=""),
        "view_default_list":   config.get("view",   "default_list", fallback=""),
        "create_board_url":    config.get("create", "board_url",    fallback=""),
        "create_default_list": config.get("create", "default_list", fallback=""),
    }


SETTINGS = load_settings()


def get_auth_params():
    """Trello API 認証パラメータを返す"""
    if not TRELLO_API_KEY or not TRELLO_TOKEN:
        raise EnvironmentError(
            "環境変数 TRELLO_API_KEY と TRELLO_TOKEN を設定してください"
        )
    return {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN}


def extract_board_id(board_url: str) -> str:
    """Trello ボード URL からボード ID を抽出する。ID だけの入力も許容"""
    match = re.search(r"trello\.com/b/([^/]+)", board_url)
    if match:
        return match.group(1)
    if re.match(r"^[a-zA-Z0-9]+$", board_url.strip()):
        return board_url.strip()
    raise ValueError(f"ボード URL の形式が正しくありません: {board_url}")


@app.route("/")
def index():
    return render_template("index.html", settings=SETTINGS)


@app.route("/api/lists", methods=["GET"])
def get_lists():
    """ボード URL からリスト一覧を返す"""
    try:
        params = get_auth_params()
    except EnvironmentError as e:
        return jsonify({"error": str(e)}), 500

    board_url = request.args.get("board_url", "").strip()
    if not board_url:
        return jsonify({"error": "board_url は必須です"}), 400

    try:
        board_id = extract_board_id(board_url)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    url = f"{TRELLO_API_BASE}/boards/{board_id}/lists"
    params["fields"] = "id,name"

    response = requests.get(url, params=params, timeout=10)
    if not response.ok:
        return jsonify({
            "error": f"Trello API エラー: {response.status_code} {response.text}"
        }), response.status_code

    return jsonify([{"id": l["id"], "name": l["name"]} for l in response.json()])


@app.route("/api/cards", methods=["GET"])
def get_cards():
    """指定リスト内のカード一覧を返す（説明文も含む）"""
    try:
        params = get_auth_params()
    except EnvironmentError as e:
        return jsonify({"error": str(e)}), 500

    list_id = request.args.get("list_id", "").strip()
    if not list_id:
        return jsonify({"error": "list_id は必須です"}), 400

    url = f"{TRELLO_API_BASE}/lists/{list_id}/cards"
    params["fields"] = "id,name,desc,url"

    response = requests.get(url, params=params, timeout=10)
    if not response.ok:
        return jsonify({
            "error": f"Trello API エラー: {response.status_code} {response.text}"
        }), response.status_code

    return jsonify([
        {"id": c["id"], "name": c["name"], "desc": c["desc"], "url": c["url"]}
        for c in response.json()
    ])


@app.route("/api/cards", methods=["POST"])
def create_card():
    """指定リストに新規カードを追加する"""
    try:
        params = get_auth_params()
    except EnvironmentError as e:
        return jsonify({"error": str(e)}), 500

    data = request.get_json()
    if not data:
        return jsonify({"error": "リクエストボディが不正です"}), 400

    list_id = data.get("list_id", "").strip()
    title = data.get("title", "").strip()
    description = data.get("description", "").strip()

    if not list_id:
        return jsonify({"error": "追加先リストを選択してください"}), 400
    if not title:
        return jsonify({"error": "カードタイトルは必須です"}), 400

    url = f"{TRELLO_API_BASE}/cards"
    params.update({"idList": list_id, "name": title, "desc": description})

    response = requests.post(url, params=params, timeout=10)
    if not response.ok:
        return jsonify({
            "error": f"Trello API エラー: {response.status_code} {response.text}"
        }), response.status_code

    card = response.json()
    return jsonify({"id": card["id"], "name": card["name"], "url": card["url"]}), 201


@app.route("/api/cards/<card_id>/comments", methods=["POST"])
def add_comment(card_id):
    """指定カードにコメントを追加する"""
    try:
        params = get_auth_params()
    except EnvironmentError as e:
        return jsonify({"error": str(e)}), 500

    data = request.get_json()
    if not data:
        return jsonify({"error": "リクエストボディが不正です"}), 400

    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "コメント本文は必須です"}), 400

    url = f"{TRELLO_API_BASE}/cards/{card_id}/actions/comments"
    params["text"] = text

    response = requests.post(url, params=params, timeout=10)
    if not response.ok:
        return jsonify({
            "error": f"Trello API エラー: {response.status_code} {response.text}"
        }), response.status_code

    action = response.json()
    return jsonify({"id": action["id"], "text": action["data"]["text"]}), 201


if __name__ == "__main__":
    missing = [v for v in ["TRELLO_API_KEY", "TRELLO_TOKEN"] if not os.environ.get(v)]
    if missing:
        print(f"[警告] 環境変数が未設定です: {', '.join(missing)}")
        print("  .env ファイルを作成して設定してください (.env.example を参照)")
    app.run(debug=False, port=5000)
