import { useEffect, useRef, useState } from 'react'
import {
  getHotelDetail,
  updateHotel,
  createPlan,
  updatePlan,
  deletePlan,
  type HotelDetail,
  type AccommodationPlan,
  type PlanFormValues,
} from '../api/facilityApi'
import type { ApiMessage } from '../../../../common/api/types'
import ToastStack, { type ToastItem } from '../../../../common/components/ToastStack'
import ConfirmDialog from '../../../../common/components/ConfirmDialog'
import PlanFormScreen from './PlanFormScreen'
import PlanDetailScreen from './PlanDetailScreen'
import './FacilityDetailScreen.css'

type FacilityDetailScreenProps = {
  hotelId: number
  onBack: () => void
}

// プランの新規登録・編集フォームの表示対象。'new'は新規登録、number編集中のplan_idを表す。
type PlanFormTarget = 'new' | number | null

// 宿泊プラン(AccommodationPlan)からフォーム初期値(PlanFormValues)を組み立てる。
function toFormValues(plan: AccommodationPlan): PlanFormValues {
  return {
    plan_name: plan.plan_name,
    price: plan.price,
    area: plan.area,
    room_size: plan.room_size,
    capacity: plan.capacity,
    has_breakfast: plan.has_breakfast,
    has_lunch: plan.has_lunch,
    has_dinner: plan.has_dinner,
    introduction: plan.introduction,
  }
}

// 施設詳細画面。施設の基本情報の編集と、宿泊プランの追加・編集・削除を行う。
function FacilityDetailScreen({ hotelId, onBack }: FacilityDetailScreenProps) {
  const [hotel, setHotel] = useState<HotelDetail | null>(null)
  // 施設情報の再取得をトリガーするためのバージョン番号(プランの追加・編集・削除、施設情報更新のたびにインクリメントする)。
  const [reloadVersion, setReloadVersion] = useState(0)

  // 施設の基本情報(名称・住所・紹介文)の編集state。
  const [isEditingHotel, setIsEditingHotel] = useState(false)
  const [hotelName, setHotelName] = useState('')
  const [address, setAddress] = useState('')
  const [introduction, setIntroduction] = useState('')
  const [isSavingHotel, setIsSavingHotel] = useState(false)

  // プラン新規登録・編集フォームの表示対象と、送信中状態。
  const [planFormTarget, setPlanFormTarget] = useState<PlanFormTarget>(null)
  const [isSubmittingPlan, setIsSubmittingPlan] = useState(false)

  // プラン一覧のカードをクリックして表示中のプラン詳細画面の対象plan_id。nullのときは非表示。
  const [selectedPlanId, setSelectedPlanId] = useState<number | null>(null)

  // 削除確認ダイアログの表示対象(削除確認中のプラン)。nullのときは非表示。
  const [deleteTargetPlan, setDeleteTargetPlan] = useState<AccommodationPlan | null>(null)

  // バックエンドから返却されたメッセージ(正常終了・エラーいずれも)を知らせるポップアップ通知。
  // message_typeが'error'の場合は警告色で表示し、それ以外は正常終了として表示する。
  // 複数件同時に発生しても消さずに積み上げて表示するため、配列で保持する。
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const nextToastId = useRef(0)

  // バックエンドのレスポンスからメッセージを取り出し、トーストに追加する。
  // 成功・失敗いずれのメッセージもバックエンドがmessagesに詰めて返す設計のため、
  // ここではmessage_typeを見て表示色を切り替えるだけで済む。
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

  // hotelIdが変わる、または再取得トリガーが変化するたびに施設詳細情報を取得する。
  useEffect(() => {
    let cancelled = false
    async function fetchDetail() {
      const response = await getHotelDetail(hotelId)
      if (cancelled) return
      if (response.messages.length > 0 || !response.hotel) {
        showResponseToast(response.messages)
        return
      }
      setHotel(response.hotel)
      setHotelName(response.hotel.hotel_name)
      setAddress(response.hotel.address)
      setIntroduction(response.hotel.introduction)
    }
    fetchDetail()
    return () => {
      cancelled = true
    }
  }, [hotelId, reloadVersion])

  function handleStartEditHotel() {
    if (!hotel) return
    setHotelName(hotel.hotel_name)
    setAddress(hotel.address)
    setIntroduction(hotel.introduction)
    setIsEditingHotel(true)
  }

  async function handleSaveHotel() {
    setIsSavingHotel(true)
    const response = await updateHotel(hotelId, hotelName, address, introduction)
    setIsSavingHotel(false)
    if (showResponseToast(response.messages)) return
    setIsEditingHotel(false)
    setReloadVersion((version) => version + 1)
  }

  async function handleSubmitPlanForm(values: PlanFormValues) {
    setIsSubmittingPlan(true)
    const isNew = planFormTarget === 'new'
    const response = isNew ? await createPlan(hotelId, values) : await updatePlan(planFormTarget as number, values)
    setIsSubmittingPlan(false)
    if (showResponseToast(response.messages)) return
    setPlanFormTarget(null)
    setReloadVersion((version) => version + 1)
  }

  async function handleConfirmDeletePlan() {
    if (!deleteTargetPlan) return
    const response = await deletePlan(deleteTargetPlan.plan_id)
    setDeleteTargetPlan(null)
    if (showResponseToast(response.messages)) return
    setSelectedPlanId(null)
    setReloadVersion((version) => version + 1)
  }

  const mealLabel = (plan: AccommodationPlan) =>
    [plan.has_breakfast && '朝食', plan.has_lunch && '昼食', plan.has_dinner && '夕食'].filter(Boolean).join('・') ||
    'なし'

  const toastStack = <ToastStack toasts={toasts} onClose={handleCloseToast} />

  // プラン追加・編集中は、施設詳細画面ではなく専用のプラン登録・編集画面を表示する。
  if (planFormTarget !== null) {
    const editingPlan = planFormTarget === 'new' ? null : hotel?.plans.find((plan) => plan.plan_id === planFormTarget)
    return (
      <>
        {toastStack}
        <PlanFormScreen
          title={planFormTarget === 'new' ? 'プランを追加' : 'プランを編集'}
          initialValues={editingPlan ? toFormValues(editingPlan) : null}
          isSubmitting={isSubmittingPlan}
          onSubmit={handleSubmitPlanForm}
          onBack={() => setPlanFormTarget(null)}
        />
      </>
    )
  }

  // プラン一覧のカードをクリックした後は、プラン詳細画面を表示する。
  if (selectedPlanId !== null) {
    const selectedPlan = hotel?.plans.find((plan) => plan.plan_id === selectedPlanId)
    if (selectedPlan) {
      return (
        <>
          {toastStack}
          <PlanDetailScreen
            plan={selectedPlan}
            onBack={() => setSelectedPlanId(null)}
            onEdit={() => setPlanFormTarget(selectedPlan.plan_id)}
            onDelete={() => setDeleteTargetPlan(selectedPlan)}
          />
          {deleteTargetPlan && (
            <ConfirmDialog
              message={`宿泊プラン「${deleteTargetPlan.plan_name}」を削除します。よろしいですか？`}
              onCancel={() => setDeleteTargetPlan(null)}
              onConfirm={handleConfirmDeletePlan}
            />
          )}
        </>
      )
    }
  }

  return (
    <div className="facility-detail-box">
      {toastStack}
      <button className="back-link" onClick={onBack}>
        ＜ 施設一覧に戻る
      </button>
      {hotel && (
        <>
          <div className="facility-detail-section">
            <div className="facility-detail-section-header">
              <h4>施設情報</h4>
              {!isEditingHotel && (
                <button className="edit-btn" onClick={handleStartEditHotel}>
                  編集
                </button>
              )}
            </div>
            {isEditingHotel ? (
              <div className="hotel-edit-form">
                <div className="hotel-edit-row">
                  <label className="hotel-edit-label">施設名称</label>
                  <input type="text" value={hotelName} onChange={(e) => setHotelName(e.target.value)} />
                </div>
                <div className="hotel-edit-row">
                  <label className="hotel-edit-label">住所</label>
                  <input type="text" value={address} onChange={(e) => setAddress(e.target.value)} />
                </div>
                <div className="hotel-edit-row">
                  <label className="hotel-edit-label">紹介文</label>
                  <textarea rows={4} value={introduction} onChange={(e) => setIntroduction(e.target.value)} />
                </div>
                <div className="hotel-edit-actions">
                  <button
                    className="plan-form-cancel"
                    onClick={() => setIsEditingHotel(false)}
                    disabled={isSavingHotel}
                  >
                    キャンセル
                  </button>
                  <button
                    className="plan-form-submit"
                    onClick={handleSaveHotel}
                    disabled={isSavingHotel || hotelName.trim() === '' || address.trim() === ''}
                  >
                    保存
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div className="facility-detail-name">{hotel.hotel_name}</div>
                <div className="facility-detail-row">
                  <span className="label">住所</span>
                  <span>{hotel.address}</span>
                </div>
                <p className="facility-detail-text">{hotel.introduction}</p>
              </>
            )}
          </div>

          <div className="facility-detail-section">
            <div className="facility-detail-section-header">
              <h4>宿泊プラン</h4>
              <button className="edit-btn" onClick={() => setPlanFormTarget('new')}>
                プランを追加
              </button>
            </div>

            {hotel.plans.length === 0 ? (
              <div className="plan-list-empty">登録されている宿泊プランがありません。</div>
            ) : (
              <div className="admin-plan-list">
                {hotel.plans.map((plan) => (
                  <div
                    className="admin-plan-card admin-plan-card-clickable"
                    key={plan.plan_id}
                    onClick={() => setSelectedPlanId(plan.plan_id)}
                  >
                    <div className="admin-plan-card-main">
                      <div className="admin-plan-name">{plan.plan_name}</div>
                      <div className="admin-plan-meta">
                        {plan.room_size}㎡ ・ 1日{plan.capacity}室 ・ 食事: {mealLabel(plan)}
                      </div>
                    </div>
                    <div className="admin-plan-price">{plan.price.toLocaleString()}円</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

export default FacilityDetailScreen
