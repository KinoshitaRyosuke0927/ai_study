from database.db_access_info import Base
# 日本語の列にはUnicode, 英数字の列にはString
from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Unicode


############################################################
## マスタテーブル定義
############################################################
# m_messageテーブル
class MMessage(Base):
    __tablename__ = 'm_message'

    message_id = Column(String(10), primary_key=True)
    message_type = Column(String(8), nullable=False)
    message = Column(Unicode(255), nullable=False)

# m_task_stateテーブル
class MTaskState(Base):
    __tablename__ = 'm_task_state'

    task_state_id = Column(Integer, primary_key=True)
    task_state_name = Column(Unicode(4), nullable=False)

# m_userテーブル
class MUser(Base):
    __tablename__ = 'm_user'

    user_id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_name = Column(Unicode(30), nullable=False)
    mail_address = Column(String(255), nullable=False, unique=True)
    password = Column(String(255), nullable=False)


############################################################
## トランザクションテーブル定義
############################################################
# t_taskテーブル
class TTask(Base):
    __tablename__ = 't_task'

    task_id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_name = Column(Unicode(255), nullable=False)
    task_state_id = Column(Integer, nullable=False)
    update_at = Column(DateTime, nullable=False)
    user_id = Column(BigInteger, nullable=False)

# t_upload_objectテーブル
class TUploadObject(Base):
    __tablename__ = 't_upload_object'

    upload_object_id = Column(BigInteger, primary_key=True, autoincrement=True)
    upload_object_name = Column(Unicode(255), nullable=False)
    upload_object_type = Column(String(8), nullable=False)
    full_path = Column(Unicode(1000), nullable=False)
    task_id = Column(BigInteger, nullable=False)
    user_id = Column(BigInteger, nullable=False)

# t_result_fileテーブル
class TResultFile(Base):
    __tablename__ = 't_result_file'

    result_file_id = Column(BigInteger, primary_key=True, autoincrement=True)
    result_file_name = Column(Unicode(255), nullable=False)
    original_file_id = Column(BigInteger, nullable=False)
    task_id = Column(BigInteger, nullable=False)
    user_id = Column(BigInteger, nullable=False)
