from enum import Enum


# ファイルのアップロード先
class FileShareName(Enum):
    UPLOAD = "upload_file"
    RESULT = "result_file"

# メッセージタイプ
class MessageType(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

# タスク状態
class TaskState(Enum):
    WAITING = 1
    DOING = 2
    RERUN = 3
    DONE = 4

# タスク詳細画面の操作モード
class OperationType(Enum):
    CREATE = "create"
    INQUIRY = "inquiry"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"


# ファイル共有へのファイルアップロード処理の最大同時実行数
MAX_FILE_UPLOAD_NUM = 5

# システムで変換可能なファイル形式
TRANSLATABLE_FILE_EXT = [".py"]
