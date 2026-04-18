from unittest.mock import patch

from common import common_validate


# 正常系
# 入力文字列の長さが正常にチェックできること
def test_length_validation_OK_01():
    ## テストデータ用意
    # 入力文字列
    test_text = "てすともじれつ"
    # 最小値
    l_min = 1
    # 最大値
    l_max = 10

    ## テスト処理
    result_list = common_validate.length_validation("", test_text, l_min, l_max)

    assert len(result_list) == 0


# 正常系
# 入力文字列の長さが規定外の場合に検知できること
@patch(
        "database.db_access_service.select_message",
        return_value={"message_id": "mag-E-0002", "message_type": "error", "message": "{}が正しくありません。{}は{}文字以上{}文字以下にしてください。"}
)
def test_length_validation_OK_02(mock):
    ## テストデータ用意
    # 入力文字列
    test_text = ""
    # 最小値
    l_min = 1
    # 最大値
    l_max = 10

    ## テスト処理
    result_list = common_validate.length_validation("", test_text, l_min, l_max)

    assert len(result_list) == 1


# 正常系
# 入力文字列の長さが規定外の場合に検知できること
@patch(
        "database.db_access_service.select_message",
        return_value={"message_id": "mag-E-0002", "message_type": "error", "message": "{}が正しくありません。{}は{}文字以上{}文字以下にしてください。"}
)
def test_length_validation_OK_03(mock):
    ## テストデータ用意
    # 入力文字列
    test_text = "てすともじれつてすともじれつ"
    # 最小値
    l_min = 1
    # 最大値
    l_max = 10

    ## テスト処理
    result_list = common_validate.length_validation("", test_text, l_min, l_max)

    assert len(result_list) == 1


# 正常系
# スペースのみの場合に検知できること
@patch(
        "database.db_access_service.select_message",
        return_value={"message_id": "mag-E-0002", "message_type": "error", "message": "{}が正しくありません。{}は{}文字以上{}文字以下にしてください。"}
)
def test_length_validation_OK_04(mock):
    ## テストデータ用意
    # 入力文字列
    test_text = " 　　　  　 "
    # 最小値
    l_min = 1
    # 最大値
    l_max = 10

    ## テスト処理
    result_list = common_validate.length_validation("", test_text, l_min, l_max)

    assert len(result_list) == 1


# 正常系
# スペース以外の文字が存在する場合はスペースも文字数にカウントされること
def test_length_validation_OK_05():
    ## テストデータ用意
    # 入力文字列
    test_text = "て　す　と　もじれつ"
    # 最小値
    l_min = 1
    # 最大値
    l_max = 10

    ## テスト処理
    result_list = common_validate.length_validation("", test_text, l_min, l_max)

    assert len(result_list) == 0


# 正常系
# スペースを含めた入力文字列の長さが規定外の場合に検知できること
@patch(
        "database.db_access_service.select_message",
        return_value={"message_id": "mag-E-0002", "message_type": "error", "message": "{}が正しくありません。{}は{}文字以上{}文字以下にしてください。"}
)
def test_length_validation_OK_06(mock):
    ## テストデータ用意
    # 入力文字列
    test_text = "て　す　と　も じ れ つ "
    # 最小値
    l_min = 1
    # 最大値
    l_max = 10

    ## テスト処理
    result_list = common_validate.length_validation("", test_text, l_min, l_max)

    assert len(result_list) == 1


# 正常系
# エラーメッセージが正しく整形されること
@patch(
        "database.db_access_service.select_message",
        return_value={"message_id": "mag-E-0002", "message_type": "error", "message": "{}が正しくありません。{}は{}文字以上{}文字以下にしてください。"}
)
def test_length_validation_OK_07(mock):
    ## テストデータ用意
    # 入力文字列
    test_text = "めっせーじかくにんもじれつ"
    # 最小値
    l_min = 1
    # 最大値
    l_max = 10

    ## 期待値
    expected_dict = {"message_id": "mag-E-0002", "message_type": "error", "message": "文字の長さが正しくありません。文字の長さは1文字以上10文字以下にしてください。"}

    ## テスト処理
    result_list = common_validate.length_validation("文字の長さ", test_text, l_min, l_max)

    assert len(result_list) == 1
    assert result_list[0] == expected_dict


# 正常系
# 空の配列に対してエラーにならないこと
def test_filter_data_OK_01():
    ## テストデータ用意
    # フィルタ対象の配列
    metadata_list = []

    ## 期待値
    expected_list = []

    ## テスト処理
    result_list = common_validate.filter_data(metadata_list)

    assert result_list == expected_list


# 正常系
# 適切なデータのみの場合に正常に処理が行われること
def test_filter_data_OK_02():
    ## テストデータ用意
    # フィルタ対象の配列
    metadata_list = []
    # 辞書データ
    metadata_folder = {}
    metadata_folder["upload_object_type"] = "folder"
    metadata_file = {}
    metadata_file["upload_object_type"] = "file"
    metadata_file["upload_object_name"] = "sample.py"
    # データ追加
    metadata_list.append(metadata_file)
    metadata_list.append(metadata_folder)
    metadata_list.append(metadata_folder)
    metadata_list.append(metadata_file)
    metadata_list.append(metadata_file)
    metadata_list.append(metadata_folder)
    metadata_list.append(metadata_file)
    metadata_list.append(metadata_file)
    metadata_list.append(metadata_file)

    ## 期待値
    expected_list = [True] * len(metadata_list)

    ## テスト処理
    result_list = common_validate.filter_data(metadata_list)

    assert result_list == expected_list


# 正常系
# 不適切なデータを含む場合でも正常に処理が行われること
def test_filter_data_OK_03():
    ## テストデータ用意
    # フィルタ対象の配列
    metadata_list = []
    # 辞書データ
    metadata_folder = {}
    metadata_folder["upload_object_type"] = "folder"
    metadata_file_py = {}
    metadata_file_py["upload_object_type"] = "file"
    metadata_file_py["upload_object_name"] = "sample.py"
    metadata_file_txt = {}
    metadata_file_txt["upload_object_type"] = "file"
    metadata_file_txt["upload_object_name"] = "sample.txt"
    # データ追加
    metadata_list.append(metadata_file_txt)
    metadata_list.append(metadata_folder)
    metadata_list.append(metadata_folder)
    metadata_list.append(metadata_file_py)
    metadata_list.append(metadata_file_txt)
    metadata_list.append(metadata_folder)
    metadata_list.append(metadata_file_py)
    metadata_list.append(metadata_file_txt)
    metadata_list.append(metadata_file_py)

    ## 期待値
    expected_list = [False, True, True, True, False, True, True, False, True]

    ## テスト処理
    result_list = common_validate.filter_data(metadata_list)

    assert result_list == expected_list
