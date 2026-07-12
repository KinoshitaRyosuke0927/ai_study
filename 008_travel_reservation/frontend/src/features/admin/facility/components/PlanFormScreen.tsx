import type { PlanFormValues } from '../api/facilityApi'
import PlanForm from './PlanForm'
import './PlanFormScreen.css'

type PlanFormScreenProps = {
  title: string
  // 指定した場合は編集、未指定(null)の場合は新規登録として扱う。
  initialValues: PlanFormValues | null
  isSubmitting: boolean
  onSubmit: (values: PlanFormValues) => void
  onBack: () => void
}

// 宿泊プランの新規登録・編集を行う画面。施設詳細画面から切り替えて表示する。
function PlanFormScreen({ title, initialValues, isSubmitting, onSubmit, onBack }: PlanFormScreenProps) {
  return (
    <div className="plan-form-screen">
      <button className="back-link" onClick={onBack}>
        ＜ 施設詳細に戻る
      </button>
      <h3>{title}</h3>
      <PlanForm initialValues={initialValues} isSubmitting={isSubmitting} onSubmit={onSubmit} onCancel={onBack} />
    </div>
  )
}

export default PlanFormScreen
