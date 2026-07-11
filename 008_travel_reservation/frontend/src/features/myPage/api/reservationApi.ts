import { getJson } from '../../../common/api/client'
import type { ApiMessage } from '../../../common/api/types'

// マイページの予約確認で表示する、宿泊プラン詳細を含んだ予約情報。
export type Reservation = {
  hotel_id: number
  hotel_name: string
  plan_id: number
  plan_name: string
  price: number
  date_of_stay: string
  status: string
}

export type GetReservationsResponse = {
  messages: ApiMessage[]
  reservations: Reservation[]
}

// ユーザIDを指定して、そのユーザの予約一覧(予約日昇順)を取得するAPIを呼び出す。
export function getReservations(userId: number): Promise<GetReservationsResponse> {
  return getJson(`/reservations/${userId}`)
}
