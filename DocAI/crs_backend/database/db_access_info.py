from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# 開発環境への接続情報
USER_NAME = "crs_admin"
PASSWORD = "JBDais0343308194"
SERVER = "crs-test.database.windows.net"
DATABASE = "crs"

# パスワードのエンコード
password_encoded = quote_plus(PASSWORD)

# DB接続URL
# PCにインストールされているODBCドライバーを指定
# 参考 : https://learn.microsoft.com/ja-jp/sql/connect/odbc/download-odbc-driver-for-sql-server?view=sql-server-ver17
DATABASE_URL = (
    f"mssql+pyodbc://{USER_NAME}:{password_encoded}@{SERVER}:1433/{DATABASE}"
    "?driver=ODBC+Driver+18+for+SQL+Server"
    "&Encrypt=yes"
    "&TrustServerCertificate=no"
)

# SQLAlchemyエンジン生成
engine = create_engine(DATABASE_URL, echo=False, future=True)
# ローカルセッション生成
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
db = SessionLocal()
# Baseクラスの生成
Base = declarative_base()
