import { useEffect, useState } from 'react'
import { getPlanDetail, type AccommodationPlanDetail } from '../api/planDetailApi'
import Header, { type Tab } from './Header'
import './PlanDetailScreen.css'

type PlanDetailScreenProps = {
  userName: string
  activeTab: Tab
  onTabChange: (tab: Tab) => void
  onLogout: () => void
  planId: number
  onBack: () => void
}

function PlanDetailScreen({ userName, activeTab, onTabChange, onLogout, planId, onBack }: PlanDetailScreenProps) {
  const [plan, setPlan] = useState<AccommodationPlanDetail | null>(null)
  const [errorMessage, setErrorMessage] = useState('')

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

  const mealLabel = plan
    ? [plan.has_breakfast && '朝食', plan.has_lunch && '昼食', plan.has_dinner && '夕食']
        .filter(Boolean)
        .join('・') || 'なし'
    : ''

  return (
    <div className="screen-shell">
      <Header userName={userName} activeTab={activeTab} onTabChange={onTabChange} onLogout={onLogout} />
      <main className="home-body">
        <div className="plan-detail-box">
          <button className="back-link" onClick={onBack}>
            ＜ 検索結果に戻る
          </button>
          {errorMessage && <div className="error-message">{errorMessage}</div>}
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
            </>
          )}
        </div>
      </main>
    </div>
  )
}

export default PlanDetailScreen
