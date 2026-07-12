import { getJson, postJson } from '../../../../common/api/client'
import type { ApiMessage } from '../../../../common/api/types'

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

// 1日分の空室状況(その日に予約可能かどうか)。
export type AvailabilityDay = {
  date_of_stay: string
  is_available: boolean
}

export type GetPlanAvailabilityResponse = {
  messages: ApiMessage[]
  capacity: number
  availability: AvailabilityDay[]
}

// プランIDを指定して、当日以降の空室状況を取得するAPIを呼び出す。
export function getPlanAvailability(planId: number): Promise<GetPlanAvailabilityResponse> {
  return getJson(`/plan-availability/${planId}`)
}

export type CreateReservationResponse = {
  messages: ApiMessage[]
}

// ユーザID・プランID・宿泊日を指定して予約を登録するAPIを呼び出す。
export function createReservation(
  userId: number,
  planId: number,
  dateOfStay: string
): Promise<CreateReservationResponse> {
  return postJson('/reservations', { user_id: userId, plan_id: planId, date_of_stay: dateOfStay })
}
