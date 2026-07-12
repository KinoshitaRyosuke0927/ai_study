import { postJson } from '../../../../common/api/client'
import type { ApiMessage } from '../../../../common/api/types'

// 検索結果として表示する宿泊プランの情報。
// 一覧表示に必要な最小限の項目のみを持ち、詳細情報はplanDetailApi側で別途取得する。
export type AccommodationPlan = {
  hotel_id: number
  hotel_name: string
  plan_id: number
  plan_name: string
  price: number
}

export type SearchPlanResponse = {
  messages: ApiMessage[]
  plans: AccommodationPlan[]
}

// キーワードに一致する宿泊プランを検索するAPIを呼び出す。
// バックエンドのフィールド名(key_word)に合わせてリクエストボディを組み立てている。
export function searchPlan(keyWord: string): Promise<SearchPlanResponse> {
  return postJson('/search-plan', { key_word: keyWord })
}
