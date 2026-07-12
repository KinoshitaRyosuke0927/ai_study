import Toast from './Toast'
import './Toast.css'

export type ToastItem = {
  id: number
  message: string
  variant: 'info' | 'error'
}

type ToastStackProps = {
  toasts: ToastItem[]
  onClose: (id: number) => void
}

// 複数のトーストを右上に縦積みで表示する。
// 新しい通知は末尾に追加するだけで、既存の通知は×ボタンをクリックするまで表示され続ける。
function ToastStack({ toasts, onClose }: ToastStackProps) {
  if (toasts.length === 0) return null
  return (
    <div className="toast-stack">
      {toasts.map((toast) => (
        <Toast key={toast.id} message={toast.message} variant={toast.variant} onClose={() => onClose(toast.id)} />
      ))}
    </div>
  )
}

export default ToastStack
