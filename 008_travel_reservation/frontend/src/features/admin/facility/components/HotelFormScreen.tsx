import HotelForm, { type HotelFormValues } from './HotelForm'
import './PlanFormScreen.css'

type HotelFormScreenProps = {
  isSubmitting: boolean
  onSubmit: (values: HotelFormValues) => void
  onBack: () => void
}

// 施設の新規登録を行う画面。施設一覧画面から切り替えて表示する。
function HotelFormScreen({ isSubmitting, onSubmit, onBack }: HotelFormScreenProps) {
  return (
    <div className="plan-form-screen">
      <button className="back-link" onClick={onBack}>
        ＜ 施設一覧に戻る
      </button>
      <h3>施設を追加</h3>
      <HotelForm isSubmitting={isSubmitting} onSubmit={onSubmit} onCancel={onBack} />
    </div>
  )
}

export default HotelFormScreen
