import './Toast.css'

type ToastProps = {
  message: string
  // バックエンドのApiMessage.message_typeに対応。'error'の場合は警告色で表示する。
  variant?: 'info' | 'error'
  onClose: () => void
}

// 操作完了・エラーをユーザーに知らせるポップアップ通知。
// 一定時間で自動的には消えず、×ボタンをクリックしたときのみ閉じる。
function Toast({ message, variant = 'info', onClose }: ToastProps) {
  return (
    <div className={`toast toast-${variant}`} role="status">
      <span className="toast-message">{message}</span>
      <button className="toast-close" onClick={onClose} aria-label="閉じる">
        ×
      </button>
    </div>
  )
}

export default Toast
