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
    E_0004 = {
        "message_id": "msg-E-0004",
        "message_type": "error",
        "message": "施設登録の申請をした方のみがログインできます。",
    }
    E_0005 = {
        "message_id": "msg-E-0005",
        "message_type": "error",
        "message": "該当する施設が見つかりませんでした。",
    }
    E_0006 = {
        "message_id": "msg-E-0006",
        "message_type": "error",
        "message": "予約が存在するため、この宿泊プランは削除できません。",
    }


class InfoMessages:
    """
    バックエンドAPIが返却する正常終了メッセージをまとめたクラス
    """

    I_0001 = {
        "message_id": "msg-I-0001",
        "message_type": "info",
        "message": "施設情報を保存しました。",
    }
    I_0002 = {
        "message_id": "msg-I-0002",
        "message_type": "info",
        "message": "宿泊プランを追加しました。",
    }
    I_0003 = {
        "message_id": "msg-I-0003",
        "message_type": "info",
        "message": "宿泊プランを更新しました。",
    }
    I_0004 = {
        "message_id": "msg-I-0004",
        "message_type": "info",
        "message": "宿泊プランを削除しました。",
    }
    I_0005 = {
        "message_id": "msg-I-0005",
        "message_type": "info",
        "message": "施設情報を追加しました。",
    }
