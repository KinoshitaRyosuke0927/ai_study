from unittest.mock import patch

import pandas as pd

from models import AccommodationPlan, SearchPlanResponse
from services import accommodation_plan_service

# テスト用のaccommodation_planテーブルデータ
plan_df = pd.DataFrame(
    data=[
        {"hotel_id": 1, "hotel_name": "HOTEL HOLOLIVE", "plan_id": 1, "plan_name": "部屋指定なし 格安プラン", "price": 4500},
        {"hotel_id": 1, "hotel_name": "HOTEL HOLOLIVE", "plan_id": 2, "plan_name": "1泊2日 朝食ビュッフェ付きプラン", "price": 12000},
    ],
).astype({"hotel_id": int, "hotel_name": str, "plan_id": int, "plan_name": str, "price": int})


# 正常系
# キーワードにヒットするプランが存在する場合に一覧が返ること
@patch("database.db_access_service.select_plan", return_value=plan_df)
def test_search_OK_01(mock):
    ## テストデータ用意
    # 検索キーワード
    key_word = "HOLOLIVE"

    ## 期待値
    expected_res = SearchPlanResponse(
        messages=[],
        plans=[
            AccommodationPlan(hotel_id=1, hotel_name="HOTEL HOLOLIVE", plan_id=1, plan_name="部屋指定なし 格安プラン", price=4500),
            AccommodationPlan(hotel_id=1, hotel_name="HOTEL HOLOLIVE", plan_id=2, plan_name="1泊2日 朝食ビュッフェ付きプラン", price=12000),
        ],
    )

    ## テスト処理
    result_res = accommodation_plan_service.search(key_word)

    assert expected_res == result_res


# 正常系
# キーワードにヒットするプランが存在しない場合に空のプラン一覧が返ること
@patch("database.db_access_service.select_plan", return_value=pd.DataFrame())
def test_search_OK_02(mock):
    ## テストデータ用意
    # 検索キーワード
    key_word = "にじさんじ"

    ## 期待値
    expected_res = SearchPlanResponse(messages=[], plans=[])

    ## テスト処理
    result_res = accommodation_plan_service.search(key_word)

    assert expected_res == result_res
