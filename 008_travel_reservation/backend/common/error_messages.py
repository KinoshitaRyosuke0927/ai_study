class ErrorMessages:
    """
    バックエンドAPIが返却するエラーメッセージをまとめたクラス
    """

    E_0001 = {
        "message_id": "msg-E-0001",
        "message_type": "error",
        "message": "ログイン情報が不正です。",
    }
    E_0002 = {
        "message_id": "msg-E-0002",
        "message_type": "error",
        "message": "該当する宿泊プランが見つかりませんでした。",
    }
    E_0003 = {
        "message_id": "msg-E-0003",
        "message_type": "error",
        "message": "指定された日付は満室のため予約できません。",
    }
