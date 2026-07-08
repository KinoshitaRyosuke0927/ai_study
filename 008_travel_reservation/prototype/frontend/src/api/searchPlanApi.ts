import { API_BASE_URL } from './client'

export type SearchPlanMessage = {
  message_id: string
  message_type: string
  message: string
}

export type AccommodationPlan = {
  hotel_id: number
  hotel_name: string
  plan_id: number
  plan_name: string
  price: number
}

export type SearchPlanResponse = {
  messages: SearchPlanMessage[]
  plans: AccommodationPlan[]
}

export async function searchPlan(keyWord: string): Promise<SearchPlanResponse> {
  const res = await fetch(`${API_BASE_URL}/search-plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key_word: keyWord }),
  })
  return res.json()
}
