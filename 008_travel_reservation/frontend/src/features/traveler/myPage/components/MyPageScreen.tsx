import { useEffect, useState } from 'react'
import ScreenLayout from '../../../../common/components/ScreenLayout'
import ErrorMessage from '../../../../common/components/ErrorMessage'
import type { HeaderNavProps } from '../../../../common/types/navigation'
import { getReservations, type Reservation } from '../api/reservationApi'
import './MyPageScreen.css'

// マイページのサイドメニュー項目。今後項目を追加する場合はここにユニオン型を増やしていく想定。
type SideMenuItem = 'currentReservations' | 'pastReservations' | 'comingSoon'

type MyPageScreenProps = HeaderNavProps & {
  userId: number
}

// マイページ表示時点の日付をYYYY-MM-DD形式で取得する。
// date_of_stay(YYYY-MM-DD形式の文字列)と直接比較できるように、ローカル日時から組み立てている。
function getTodayString() {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

// マイページ画面。左側のサイドメニューから選んだ項目に応じて、右側に内容を表示する。
function MyPageScreen({ userId, ...headerProps }: MyPageScreenProps) {
  const [selectedMenu, setSelectedMenu] = useState<SideMenuItem>('currentReservations')
  const [reservations, setReservations] = useState<Reservation[]>([])
  const [errorMessage, setErrorMessage] = useState('')

  // マイページ表示時にログイン中ユーザーの予約一覧(予約日昇順)を取得する。
  useEffect(() => {
    let cancelled = false
    async function fetchReservations() {
      setErrorMessage('')
      const response = await getReservations(userId)
      if (cancelled) return
      if (response.messages.length > 0) {
        setErrorMessage(response.messages[0].message)
        setReservations([])
        return
      }
      setReservations(response.reservations)
    }
    fetchReservations()
    return () => {
      cancelled = true
    }
  }, [userId])

  // マイページ表示時点を基準に、現在(当日以降)の予約と過去の予約を分ける。
  const todayStr = getTodayString()
  const currentReservations = reservations.filter((reservation) => reservation.date_of_stay >= todayStr)
  const pastReservations = reservations.filter((reservation) => reservation.date_of_stay < todayStr)

  // 選択中のサイドメニューに応じて、タイトル・表示対象の予約一覧・0件時のメッセージを切り替える。
  const reservationPanel =
    selectedMenu === 'currentReservations'
      ? { title: '現在の予約', list: currentReservations, emptyMessage: '現在予約している宿泊プランはありません。' }
      : { title: '過去の予約', list: pastReservations, emptyMessage: '過去の予約履歴はありません。' }

  return (
    <ScreenLayout {...headerProps}>
      <div className="mypage-layout">
        <nav className="mypage-sidebar">
          <span
            className={`mypage-sidebar-item${selectedMenu === 'currentReservations' ? ' active' : ''}`}
            onClick={() => setSelectedMenu('currentReservations')}
          >
            現在の予約
          </span>
          <span
            className={`mypage-sidebar-item${selectedMenu === 'pastReservations' ? ' active' : ''}`}
            onClick={() => setSelectedMenu('pastReservations')}
          >
            過去の予約
          </span>
          <span
            className={`mypage-sidebar-item${selectedMenu === 'comingSoon' ? ' active' : ''}`}
            onClick={() => setSelectedMenu('comingSoon')}
          >
            Coming Soon...
          </span>
        </nav>
        {/* サイドメニューの選択によって表示内容(予約一覧/Coming Soon)が変わっても、
            メインカードの位置が動いて見えないよう、常に同じ.mypage-panelで統一して表示している。 */}
        <div className="mypage-content">
          {selectedMenu === 'comingSoon' ? (
            <div className="mypage-panel mypage-coming-soon">Coming Soon...</div>
          ) : (
            <div className="mypage-panel">
              <h3>{reservationPanel.title}</h3>
              <ErrorMessage message={errorMessage} />
              {!errorMessage && (
                reservationPanel.list.length === 0 ? (
                  <div className="reservation-list-empty">{reservationPanel.emptyMessage}</div>
                ) : (
                  <div className="reservation-cards">
                    {reservationPanel.list.map((reservation, index) => (
                      // 同じプランでも宿泊日ごとに1件の予約として記録されるため、plan_idとdate_of_stayを組み合わせてkeyにしている。
                      <div className="reservation-card" key={`${reservation.plan_id}-${reservation.date_of_stay}-${index}`}>
                        <div className="reservation-card-main">
                          <div className="reservation-hotel-name">{reservation.hotel_name}</div>
                          <div className="reservation-plan-name">{reservation.plan_name}</div>
                          <div className="reservation-date">宿泊日: {reservation.date_of_stay}</div>
                        </div>
                        <div className="reservation-card-side">
                          <div className="reservation-price">{reservation.price.toLocaleString()}円</div>
                          <div className="reservation-status">{reservation.status}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                )
              )}
            </div>
          )}
        </div>
      </div>
    </ScreenLayout>
  )
}

export default MyPageScreen
