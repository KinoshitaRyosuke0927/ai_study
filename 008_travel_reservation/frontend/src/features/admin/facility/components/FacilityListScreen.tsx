import { useEffect, useRef, useState } from 'react'
import { getHotels, createHotel, type HotelSummary } from '../api/facilityApi'
import type { ApiMessage } from '../../../../common/api/types'
import ToastStack, { type ToastItem } from '../../../../common/components/ToastStack'
import HotelFormScreen from './HotelFormScreen'
import type { HotelFormValues } from './HotelForm'
import './FacilityListScreen.css'

type FacilityListScreenProps = {
  ownerUserId: number
  onSelectHotel: (hotelId: number) => void
}

// 「宿泊施設」メニューのトップ画面。ログイン中のオーナーが所有する施設の一覧を表示する。
function FacilityListScreen({ ownerUserId, onSelectHotel }: FacilityListScreenProps) {
  const [hotels, setHotels] = useState<HotelSummary[]>([])
  const [isLoaded, setIsLoaded] = useState(false)
  // 施設一覧の再取得をトリガーするためのバージョン番号(施設の新規登録のたびにインクリメントする)。
  const [reloadVersion, setReloadVersion] = useState(0)

  // 施設の新規登録フォームの表示状態と、送信中状態。
  const [isAddingHotel, setIsAddingHotel] = useState(false)
  const [isSubmittingHotel, setIsSubmittingHotel] = useState(false)

  // バックエンドから返却されたメッセージ(正常終了・エラーいずれも)を知らせるポップアップ通知。
  // ×ボタンで閉じるまで表示され続けるよう、配列で保持する。
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const nextToastId = useRef(0)

  function showResponseToast(messages: ApiMessage[]): boolean {
    if (messages.length === 0) return false
    const isError = messages[0].message_type === 'error'
    nextToastId.current += 1
    setToasts((current) => [
      ...current,
      { id: nextToastId.current, message: messages[0].message, variant: isError ? 'error' : 'info' },
    ])
    return isError
  }

  function handleCloseToast(id: number) {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }

  useEffect(() => {
    let cancelled = false
    async function fetchHotels() {
      setIsLoaded(false)
      const response = await getHotels(ownerUserId)
      if (cancelled) return
      if (showResponseToast(response.messages)) {
        setIsLoaded(true)
        return
      }
      setHotels(response.hotels)
      setIsLoaded(true)
    }
    fetchHotels()
    return () => {
      cancelled = true
    }
  }, [ownerUserId, reloadVersion])

  async function handleSubmitHotelForm(values: HotelFormValues) {
    setIsSubmittingHotel(true)
    const response = await createHotel(ownerUserId, values.hotel_name, values.address, values.introduction)
    setIsSubmittingHotel(false)
    if (showResponseToast(response.messages)) return
    setIsAddingHotel(false)
    setReloadVersion((version) => version + 1)
  }

  const toastStack = <ToastStack toasts={toasts} onClose={handleCloseToast} />

  // 施設の新規登録中は、施設一覧画面ではなく専用の登録画面を表示する。
  if (isAddingHotel) {
    return (
      <>
        {toastStack}
        <HotelFormScreen
          isSubmitting={isSubmittingHotel}
          onSubmit={handleSubmitHotelForm}
          onBack={() => setIsAddingHotel(false)}
        />
      </>
    )
  }

  return (
    <div className="facility-list-box">
      {toastStack}
      <div className="facility-list-header">
        <h3>宿泊施設一覧</h3>
        <button className="edit-btn" onClick={() => setIsAddingHotel(true)}>
          施設を追加
        </button>
      </div>
      {isLoaded && hotels.length === 0 && (
        <div className="facility-list-empty">登録されている施設がありません。</div>
      )}
      <div className="facility-list">
        {hotels.map((hotel) => (
          <div className="facility-card" key={hotel.hotel_id} onClick={() => onSelectHotel(hotel.hotel_id)}>
            <div className="facility-card-name">{hotel.hotel_name}</div>
            <div className="facility-card-address">{hotel.address}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default FacilityListScreen
