import './ConfirmDialog.css'

type ConfirmDialogProps = {
  message: string
  onCancel: () => void
  onConfirm: () => void
}

// ブラウザ標準のconfirm()の代わりに使う、確認ダイアログ。
// 背景のオーバーレイをクリックした場合は「キャンセル」ボタンと同じ扱いにする。
function ConfirmDialog({ message, onCancel, onConfirm }: ConfirmDialogProps) {
  return (
    <div className="confirm-dialog-overlay" onClick={onCancel}>
      <div
        className="confirm-dialog"
        role="alertdialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="confirm-dialog-message">{message}</p>
        <div className="confirm-dialog-actions">
          <button className="confirm-dialog-cancel" onClick={onCancel}>
            キャンセル
          </button>
          <button className="confirm-dialog-ok" onClick={onConfirm}>
            OK
          </button>
        </div>
      </div>
    </div>
  )
}

export default ConfirmDialog
