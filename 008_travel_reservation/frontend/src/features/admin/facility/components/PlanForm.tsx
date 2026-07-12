import { useState } from 'react'
import { AREA_OPTIONS, type PlanFormValues } from '../api/facilityApi'
import './PlanForm.css'

// price・room_size・capacityを除いた項目の初期値。
type OtherValues = Omit<PlanFormValues, 'price' | 'room_size' | 'capacity'>

const EMPTY_OTHER_VALUES: OtherValues = {
  plan_name: '',
  area: AREA_OPTIONS[0].code,
  has_breakfast: false,
  has_lunch: false,
  has_dinner: false,
  introduction: '',
}

type PlanFormProps = {
  // 指定した場合は編集、未指定(null)の場合は新規登録として扱う。
  initialValues: PlanFormValues | null
  isSubmitting: boolean
  onSubmit: (values: PlanFormValues) => void
  onCancel: () => void
}

// 宿泊プランの新規登録・編集で共通して使うフォーム。
function PlanForm({ initialValues, isSubmitting, onSubmit, onCancel }: PlanFormProps) {
  const [values, setValues] = useState<OtherValues>(initialValues ?? EMPTY_OTHER_VALUES)
  // 価格・部屋の広さ・部屋数は、新規登録時に0や1が最初から入力されているように見えないよう、
  // 文字列(空欄可)で保持し、プレースホルダーで入力例を示す。
  const [priceInput, setPriceInput] = useState(initialValues ? String(initialValues.price) : '')
  const [roomSizeInput, setRoomSizeInput] = useState(initialValues ? String(initialValues.room_size) : '')
  const [capacityInput, setCapacityInput] = useState(initialValues ? String(initialValues.capacity) : '')

  function updateValue<K extends keyof OtherValues>(key: K, value: OtherValues[K]) {
    setValues((current) => ({ ...current, [key]: value }))
  }

  // 半角数字以外の入力(全角数字・記号など)を取り除いてから反映する。
  function sanitizeDigits(rawValue: string) {
    return rawValue.replace(/[^0-9]/g, '')
  }

  const canSubmit =
    values.plan_name.trim() !== '' && Number(priceInput) > 0 && Number(roomSizeInput) > 0 && Number(capacityInput) > 0

  function handleSubmit() {
    onSubmit({
      ...values,
      price: Number(priceInput) || 0,
      room_size: Number(roomSizeInput) || 0,
      capacity: Number(capacityInput) || 0,
    })
  }

  return (
    <div className="plan-form">
      <div className="plan-form-row">
        <label className="plan-form-label">
          プラン名<span className="required-mark">*</span>
        </label>
        <input
          type="text"
          placeholder="例: 1泊2日 朝食ビュッフェ付きプラン"
          value={values.plan_name}
          onChange={(e) => updateValue('plan_name', e.target.value)}
        />
      </div>
      <div className="plan-form-row">
        <label className="plan-form-label">
          価格(円)<span className="required-mark">*</span>
        </label>
        <input
          type="text"
          inputMode="numeric"
          placeholder="例: 12000"
          value={priceInput}
          onChange={(e) => setPriceInput(sanitizeDigits(e.target.value))}
        />
      </div>
      <div className="plan-form-row">
        <label className="plan-form-label">
          エリア<span className="required-mark">*</span>
        </label>
        <select value={values.area} onChange={(e) => updateValue('area', e.target.value)}>
          {AREA_OPTIONS.map((option) => (
            <option key={option.code} value={option.code}>
              {option.label}
            </option>
          ))}
        </select>
      </div>
      <div className="plan-form-row">
        <label className="plan-form-label">
          部屋の広さ(㎡)<span className="required-mark">*</span>
        </label>
        <input
          type="text"
          inputMode="numeric"
          placeholder="例: 25"
          value={roomSizeInput}
          onChange={(e) => setRoomSizeInput(sanitizeDigits(e.target.value))}
        />
      </div>
      <div className="plan-form-row">
        <label className="plan-form-label">
          1日あたりの部屋数<span className="required-mark">*</span>
        </label>
        <input
          type="text"
          inputMode="numeric"
          placeholder="例: 5"
          value={capacityInput}
          onChange={(e) => setCapacityInput(sanitizeDigits(e.target.value))}
        />
      </div>
      <div className="plan-form-row">
        <label className="plan-form-label">食事</label>
        <div className="plan-form-checkboxes">
          <span className="plan-form-checkbox-item">
            <input
              type="checkbox"
              checked={values.has_breakfast}
              onChange={(e) => updateValue('has_breakfast', e.target.checked)}
            />
            <span>朝食</span>
          </span>
          <span className="plan-form-checkbox-item">
            <input
              type="checkbox"
              checked={values.has_lunch}
              onChange={(e) => updateValue('has_lunch', e.target.checked)}
            />
            <span>昼食</span>
          </span>
          <span className="plan-form-checkbox-item">
            <input
              type="checkbox"
              checked={values.has_dinner}
              onChange={(e) => updateValue('has_dinner', e.target.checked)}
            />
            <span>夕食</span>
          </span>
        </div>
      </div>
      <div className="plan-form-row">
        <label className="plan-form-label">プラン紹介文</label>
        <textarea
          rows={4}
          placeholder="例: 一日の疲れを癒す露天風呂と、旬の食材を使った会席料理が自慢のプランです。"
          value={values.introduction}
          onChange={(e) => updateValue('introduction', e.target.value)}
        />
      </div>
      <div className="plan-form-actions">
        <button type="button" className="plan-form-cancel" onClick={onCancel} disabled={isSubmitting}>
          キャンセル
        </button>
        <button type="button" className="plan-form-submit" onClick={handleSubmit} disabled={!canSubmit || isSubmitting}>
          保存
        </button>
      </div>
    </div>
  )
}

export default PlanForm
