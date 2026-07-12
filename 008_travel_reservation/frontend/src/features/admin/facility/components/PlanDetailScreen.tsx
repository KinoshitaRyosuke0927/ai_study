import { getAreaLabel, type AccommodationPlan } from '../api/facilityApi'
import './PlanDetailScreen.css'

type PlanDetailScreenProps = {
  plan: AccommodationPlan
  onBack: () => void
  onEdit: () => void
  onDelete: () => void
}

// 宿泊プランの詳細画面。施設詳細画面のプラン一覧からカードをクリックした際に表示する。
// ここから編集画面(PlanFormScreen)への遷移、および削除を行える。
function PlanDetailScreen({ plan, onBack, onEdit, onDelete }: PlanDetailScreenProps) {
  const mealLabel =
    [plan.has_breakfast && '朝食', plan.has_lunch && '昼食', plan.has_dinner && '夕食'].filter(Boolean).join('・') ||
    'なし'

  return (
    <div className="plan-detail-screen">
      <button className="back-link" onClick={onBack}>
        ＜ 施設詳細に戻る
      </button>
      <div className="facility-detail-section">
        <div className="facility-detail-section-header">
          <h4>宿泊プラン詳細</h4>
          <div className="admin-plan-actions">
            <button className="edit-btn" onClick={onEdit}>
              編集
            </button>
            <button className="delete-btn" onClick={onDelete}>
              削除
            </button>
          </div>
        </div>
        <div className="facility-detail-name">{plan.plan_name}</div>
        <div className="facility-detail-row">
          <span className="label">価格</span>
          <span>{plan.price.toLocaleString()}円 / 泊</span>
        </div>
        <div className="facility-detail-row">
          <span className="label">エリア</span>
          <span>{getAreaLabel(plan.area)}</span>
        </div>
        <div className="facility-detail-row">
          <span className="label">部屋の広さ</span>
          <span>{plan.room_size}㎡</span>
        </div>
        <div className="facility-detail-row">
          <span className="label">部屋数</span>
          <span>1日{plan.capacity}室</span>
        </div>
        <div className="facility-detail-row">
          <span className="label">食事</span>
          <span>{mealLabel}</span>
        </div>
        <p className="facility-detail-text">{plan.introduction}</p>
      </div>
    </div>
  )
}

export default PlanDetailScreen
