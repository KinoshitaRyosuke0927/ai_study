import { getJson, putJson, postJson, deleteJson } from '../../../../common/api/client'
import type { ApiMessage } from '../../../../common/api/types'

// common/constants.py の AREA_CODE に対応するエリアの選択肢。
// バックエンドが未知のエリアコードもそのまま表示できる作りのため、選択肢はここで管理する。
export const AREA_OPTIONS: { code: string; label: string }[] = [{ code: '0301', label: '東京' }]

// エリアコードを表示用の地域名称に変換する。未知のコードの場合はコードのまま返す。
export function getAreaLabel(areaCode: string): string {
  return AREA_OPTIONS.find((option) => option.code === areaCode)?.label ?? areaCode
}

// 施設一覧の1件分。
export type HotelSummary = {
  hotel_id: number
  hotel_name: string
  address: string
}

export type GetHotelsResponse = {
  messages: ApiMessage[]
  hotels: HotelSummary[]
}

// オーナーのユーザIDを指定して、所有する施設の一覧を取得するAPIを呼び出す。
export function getHotels(ownerUserId: number): Promise<GetHotelsResponse> {
  return getJson(`/admin/hotels/owner/${ownerUserId}`)
}

export type CreateHotelResponse = {
  messages: ApiMessage[]
  hotel_id: number | null
}

// 施設を新規登録するAPIを呼び出す。
export function createHotel(
  ownerUserId: number,
  hotelName: string,
  address: string,
  introduction: string
): Promise<CreateHotelResponse> {
  return postJson('/admin/hotels', {
    owner_user_id: ownerUserId,
    hotel_name: hotelName,
    address,
    introduction,
  })
}

// 管理画面で編集する宿泊プランの1件分。
export type AccommodationPlan = {
  plan_id: number
  plan_name: string
  price: number
  area: string
  room_size: number
  capacity: number
  has_breakfast: boolean
  has_lunch: boolean
  has_dinner: boolean
  introduction: string
}

// 施設詳細情報(施設の基本情報+宿泊プラン一覧)。
export type HotelDetail = {
  hotel_id: number
  hotel_name: string
  address: string
  introduction: string
  plans: AccommodationPlan[]
}

export type GetHotelDetailResponse = {
  messages: ApiMessage[]
  // 該当施設が存在しない場合を表現するためnull許容にしている。
  hotel: HotelDetail | null
}

// 施設IDを指定して詳細情報を取得するAPIを呼び出す。
export function getHotelDetail(hotelId: number): Promise<GetHotelDetailResponse> {
  return getJson(`/admin/hotels/${hotelId}`)
}

export type UpdateHotelResponse = {
  messages: ApiMessage[]
}

// 施設の基本情報(名称・住所・紹介文)を更新するAPIを呼び出す。
export function updateHotel(
  hotelId: number,
  hotelName: string,
  address: string,
  introduction: string
): Promise<UpdateHotelResponse> {
  return putJson(`/admin/hotels/${hotelId}`, { hotel_name: hotelName, address, introduction })
}

// 宿泊プランの登録・更新フォームで扱う値一式。
export type PlanFormValues = {
  plan_name: string
  price: number
  area: string
  room_size: number
  capacity: number
  has_breakfast: boolean
  has_lunch: boolean
  has_dinner: boolean
  introduction: string
}

export type CreatePlanResponse = {
  messages: ApiMessage[]
  plan_id: number | null
}

// 施設IDを指定して新しい宿泊プランを登録するAPIを呼び出す。
export function createPlan(hotelId: number, plan: PlanFormValues): Promise<CreatePlanResponse> {
  return postJson(`/admin/hotels/${hotelId}/plans`, plan)
}

export type UpdatePlanResponse = {
  messages: ApiMessage[]
}

// 既存の宿泊プランを更新するAPIを呼び出す。
export function updatePlan(planId: number, plan: PlanFormValues): Promise<UpdatePlanResponse> {
  return putJson(`/admin/plans/${planId}`, plan)
}

export type DeletePlanResponse = {
  messages: ApiMessage[]
}

// 宿泊プランを削除するAPIを呼び出す。
export function deletePlan(planId: number): Promise<DeletePlanResponse> {
  return deleteJson(`/admin/plans/${planId}`)
}
