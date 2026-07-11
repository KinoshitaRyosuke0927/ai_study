import os
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

# backend/.env が存在すれば読み込む(存在しない場合は何もしない)
load_dotenv()


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """
    DB接続用のEngineを取得する(初回呼び出し時に生成し、以降はキャッシュを再利用する)

    実際にDBへアクセスするタイミングまで接続情報の検証を遅延させるため、
    モジュールのimport時ではなく呼び出し時にEngineを生成する。
    """
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "3306")
    user = os.environ.get("DB_USER", "ais_admin")
    database = os.environ.get("DB_NAME", "travel_reservation")
    password = os.environ.get("DB_PASSWORD")
    if not password:
        raise RuntimeError(
            "環境変数DB_PASSWORDが設定されていません。"
            "backend/.env に DB_PASSWORD=<ais_adminのパスワード> を設定してください。"
        )

    url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"
    return create_engine(url, pool_pre_ping=True)
