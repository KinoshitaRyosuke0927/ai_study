import { useEffect, useState } from 'react'
import { getPlanDetail, type AccommodationPlanDetail } from '../api/planDetailApi'
import ScreenLayout from '../../../common/components/ScreenLayout'
import ErrorMessage from '../../../common/components/ErrorMessage'
import type { HeaderNavProps } from '../../../common/types/navigation'
import './PlanDetailScreen.css'

type PlanDetailScreenProps = HeaderNavProps & {
  planId: number
  onBack: () => void
}

// 宿泊プランの詳細画面。planIdを受け取り、マウント時にAPIから詳細情報を取得して表示する。
function PlanDetailScreen({ planId, onBack, ...headerProps }: PlanDetailScreenProps) {
  const [plan, setPlan] = useState<AccommodationPlanDetail | null>(null)
  const [errorMessage, setErrorMessage] = useState('')

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
          </>
        )}
      </div>
    </ScreenLayout>
  )
}

export default PlanDetailScreen
