import os

from common.constant import TRANSLATABLE_FILE_EXT
from database import db_access_service


def length_validation(display_string: str, target_string: str, l_min: int, l_max: int) -> list[dict[str, str]]:
    """
    入力された文字列から半角/全角スペースを除いた長さが, 指定された範囲以内に収まっているかをチェックする関数

    Args
    -----------------
    - display_string; str,              表示文字列
    - target_string: str,               確認対象文字列
    - l_min: int,                       最小値
    - l_max: int,                       最大値

    Returns
    -----------------
    - error_list: list[dict],           エラーリスト

    """
    # 入れ物用意
    error_list = []
    # 半角/全角スペースを削除
    remove_string = target_string.replace(" ", "").replace("　", "")
    # 長さが条件に満たない場合
    if (len(remove_string) == 0) or (len(target_string) < l_min) or (l_max < len(target_string)):
        # 該当のエラーメッセージを取得
        error_dict = db_access_service.select_message("msg-E-0002")
        # 表示用の文言をセット
        error_dict["message"] = error_dict["message"].format(display_string, display_string, l_min, l_max)
        # エラーのリストに追加
        error_list.append(error_dict)

    return error_list


def filter_data(metadata_list: list[dict]) -> list[bool]:
    """
    変換対象として登録されたオブジェクト配列に合わせて, 変換対象として適切(True)か不適切(False)かを判別して返却する

    Args
    -----------------
    - metadata_list: list[dict],            変換対象のオブジェクト情報からなる配列

    Returns
    -----------------
    - filter_result: list[bool],            変換対象のデータの判定結果からなる配列

    """
    # フィルタ結果の配列用意
    filter_result = []
    # 変換対象のオブジェクトごとに確認
    for meta in metadata_list:
        # オブジェクト種別がfolderの場合
        if meta["upload_object_type"] == "folder":
            # フィルタ結果の配列にTrueを追加
            filter_result.append(True)
        # オブジェクト種別がfileの場合
        else:
            # ファイル名称から拡張子を取得
            _, ext = os.path.splitext(meta["upload_object_name"])
            # 変換対象のファイル形式か確認
            result = ext in TRANSLATABLE_FILE_EXT
            # フィルタ結果の配列に追加
            filter_result.append(result)

    # フィルタ結果を返却
    return filter_result
