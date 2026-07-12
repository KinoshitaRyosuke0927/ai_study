import { useState } from 'react'
import './PlanForm.css'

export type HotelFormValues = {
  hotel_name: string
  address: string
  introduction: string
}

const EMPTY_VALUES: HotelFormValues = {
  hotel_name: '',
  address: '',
  introduction: '',
}

type HotelFormProps = {
  isSubmitting: boolean
  onSubmit: (values: HotelFormValues) => void
  onCancel: () => void
}

// 施設の新規登録で使うフォーム。
function HotelForm({ isSubmitting, onSubmit, onCancel }: HotelFormProps) {
  const [values, setValues] = useState<HotelFormValues>(EMPTY_VALUES)

  function updateValue<K extends keyof HotelFormValues>(key: K, value: HotelFormValues[K]) {
    setValues((current) => ({ ...current, [key]: value }))
  }

  const canSubmit = values.hotel_name.trim() !== '' && values.address.trim() !== ''

  return (
    <div className="plan-form">
      <div className="plan-form-row">
        <label className="plan-form-label">
          施設名称<span className="required-mark">*</span>
        </label>
        <input
          type="text"
          placeholder="例: HOTEL SAMPLE"
          value={values.hotel_name}
          onChange={(e) => updateValue('hotel_name', e.target.value)}
        />
      </div>
      <div className="plan-form-row">
        <label className="plan-form-label">
          住所<span className="required-mark">*</span>
        </label>
        <input
          type="text"
          placeholder="例: 東京都○○区xxN-NN-NN"
          value={values.address}
          onChange={(e) => updateValue('address', e.target.value)}
        />
      </div>
      <div className="plan-form-row">
        <label className="plan-form-label">紹介文</label>
        <textarea
          rows={4}
          placeholder="例: 都心にありながら緑豊かな景観を楽しめる、くつろぎの空間を提供するホテルです。"
          value={values.introduction}
          onChange={(e) => updateValue('introduction', e.target.value)}
        />
      </div>
      <div className="plan-form-actions">
        <button type="button" className="plan-form-cancel" onClick={onCancel} disabled={isSubmitting}>
          キャンセル
        </button>
        <button
          type="button"
          className="plan-form-submit"
          onClick={() => onSubmit(values)}
          disabled={!canSubmit || isSubmitting}
        >
          保存
        </button>
      </div>
    </div>
  )
}

export default HotelForm
