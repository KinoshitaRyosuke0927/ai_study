import { getJson } from '../../../common/api/client'
import type { ApiMessage } from '../../../common/api/types'

// プラン詳細画面で表示する宿泊プランの詳細情報。
// 検索結果一覧(AccommodationPlan)より項目が多く、ホテルの住所・紹介文や食事条件などを含む。
export type AccommodationPlanDetail = {
  hotel_id: number
  hotel_name: string
  hotel_address: string
  hotel_introduction: string
  plan_id: number
  plan_name: string
  price: number
  area: string
  room_size: number
  has_breakfast: boolean
  has_lunch: boolean
  has_dinner: boolean
  introduction: string
}

export type GetPlanDetailResponse = {
  messages: ApiMessage[]
  // 該当プランが存在しない場合を表現するためnull許容にしている。
  plan: AccommodationPlanDetail | null
}

// プランIDを指定して詳細情報を取得するAPIを呼び出す。
export function getPlanDetail(planId: number): Promise<GetPlanDetailResponse> {
  return getJson(`/plan-detail/${planId}`)
}
