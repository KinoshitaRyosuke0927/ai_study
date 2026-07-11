import { useEffect, useState } from 'react'
import {
  getPlanDetail,
  getPlanAvailability,
  createReservation,
  type AccommodationPlanDetail,
  type AvailabilityDay,
} from '../api/planDetailApi'
import ScreenLayout from '../../../common/components/ScreenLayout'
import ErrorMessage from '../../../common/components/ErrorMessage'
import AvailabilityCalendar from './AvailabilityCalendar'
import type { HeaderNavProps } from '../../../common/types/navigation'
import './PlanDetailScreen.css'

type PlanDetailScreenProps = HeaderNavProps & {
  userId: number
  planId: number
  onBack: () => void
}

// 宿泊プランの詳細画面。planIdを受け取り、マウント時にAPIから詳細情報を取得して表示する。
function PlanDetailScreen({ userId, planId, onBack, ...headerProps }: PlanDetailScreenProps) {
  const [plan, setPlan] = useState<AccommodationPlanDetail | null>(null)
  const [errorMessage, setErrorMessage] = useState('')

  const [availability, setAvailability] = useState<AvailabilityDay[]>([])
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const [isReserving, setIsReserving] = useState(false)
  const [reservationError, setReservationError] = useState('')
  const [reservationMessage, setReservationMessage] = useState('')
  // 予約完了のたびにこの値を更新し、空室状況の再取得をトリガーする。
  const [availabilityVersion, setAvailabilityVersion] = useState(0)

  // planIdが変わるたびに詳細情報を再取得する。
  // cancelledフラグは、取得中にplanIdが変わって古いリクエストの結果が後から返ってきた場合に、
  // 新しい表示内容を古いレスポンスで上書きしてしまう(レースコンディション)のを防ぐためのもの。
  useEffect(() => {
    let cancelled = false
    async function fetchDetail() {
      setErrorMessage('')
      setPlan(null)
      const response = await getPlanDetail(planId)
      if (cancelled) return
      if (response.messages.length > 0 || !response.plan) {
        setErrorMessage(response.messages[0]?.message ?? '宿泊プラン情報を取得できませんでした。')
        return
      }
      setPlan(response.plan)
    }
    fetchDetail()
    return () => {
      cancelled = true
    }
  }, [planId])

  // 空室状況カレンダーの表示内容を取得する。
  // availabilityVersionは予約完了時にインクリメントし、最新の空室状況を再取得するために使う。
  useEffect(() => {
    let cancelled = false
    async function fetchAvailability() {
      const response = await getPlanAvailability(planId)
      if (cancelled) return
      if (response.messages.length === 0) {
        setAvailability(response.availability)
      }
    }
    fetchAvailability()
    return () => {
      cancelled = true
    }
  }, [planId, availabilityVersion])

  // カレンダーで日付をクリックしたときの処理。
  // 選択中の日付をもう一度クリックした場合は選択を解除する。
  // また、日付を選び直したら以前の予約完了・エラーメッセージは表示し続けない。
  function handleSelectDate(date: string) {
    setSelectedDate((current) => (current === date ? null : date))
    setReservationError('')
    setReservationMessage('')
  }

  // 予約ボタン押下時の処理。
  async function handleReserve() {
    if (!selectedDate) return
    setIsReserving(true)
    setReservationError('')
    setReservationMessage('')
    const response = await createReservation(userId, planId, selectedDate)
    setIsReserving(false)
    if (response.messages.length > 0) {
      setReservationError(response.messages[0].message)
      return
    }
    setReservationMessage(`${selectedDate} で予約が完了しました。`)
    setSelectedDate(null)
    // 予約済みの部屋数が増えたため、空室状況を最新の状態に更新する
    setAvailabilityVersion((version) => version + 1)
  }

  // 朝食・昼食・夕食のうち提供されるものだけを「・」区切りで表示するためのラベルを組み立てる。
  // 該当する食事が一つもない場合は「なし」と表示する。
  const mealLabel = plan
    ? [plan.has_breakfast && '朝食', plan.has_lunch && '昼食', plan.has_dinner && '夕食']
        .filter(Boolean)
        .join('・') || 'なし'
    : ''

  return (
    <ScreenLayout {...headerProps}>
      <div className="plan-detail-box">
        <button className="back-link" onClick={onBack}>
          ＜ 検索結果に戻る
        </button>
        <ErrorMessage message={errorMessage} />
        {/* planが取得できるまでは詳細情報を表示しない(取得中・エラー時はここが非表示になる) */}
        {plan && (
          <>
            <div className="plan-detail-top">
              <div className="plan-detail-hotel-name">{plan.hotel_name}</div>
              <div className="plan-detail-plan-name">{plan.plan_name}</div>
              <div className="plan-detail-price">{plan.price.toLocaleString()}円 <span>/ 泊</span></div>
            </div>
            <div className="plan-detail-section">
              <h4>ホテル情報</h4>
              <div className="plan-detail-row">
                <span className="label">住所</span>
                <span>{plan.hotel_address}</span>
              </div>
              <p className="plan-detail-text">{plan.hotel_introduction}</p>
            </div>
            <div className="plan-detail-section">
              <h4>プラン情報</h4>
              <div className="plan-detail-row">
                <span className="label">エリア</span>
                <span>{plan.area}</span>
              </div>
              <div className="plan-detail-row">
                <span className="label">部屋数</span>
                <span>{plan.room_size}室</span>
              </div>
              <div className="plan-detail-row">
                <span className="label">食事</span>
                <span>{mealLabel}</span>
              </div>
              <p className="plan-detail-text">{plan.introduction}</p>
            </div>
            <div className="plan-detail-section">
              <h4>空室状況</h4>
              <p className="availability-description">向こう2か月分の空室状況を表示しています。</p>
              <div className="availability-box">
                <AvailabilityCalendar
                  availability={availability}
                  selectedDate={selectedDate}
                  onSelectDate={handleSelectDate}
                />
                <div className="reservation-action">
                  <div className="reservation-selected-date">
                    {selectedDate ? `選択中の日付: ${selectedDate}` : '予約する日付を選択してください'}
                  </div>
                  <button
                    className="reservation-btn"
                    onClick={handleReserve}
                    disabled={!selectedDate || isReserving}
                  >
                    予約する
                  </button>
                  <ErrorMessage message={reservationError} />
                  {reservationMessage && <div className="reservation-success">{reservationMessage}</div>}
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </ScreenLayout>
  )
}

export default PlanDetailScreen
