import { API_BASE_URL } from './client'

export type PlanDetailMessage = {
  message_id: string
  message_type: string
  message: string
}

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
  messages: PlanDetailMessage[]
  plan: AccommodationPlanDetail | null
}

export async function getPlanDetail(planId: number): Promise<GetPlanDetailResponse> {
  const res = await fetch(`${API_BASE_URL}/plan-detail/${planId}`)
  return res.json()
}
