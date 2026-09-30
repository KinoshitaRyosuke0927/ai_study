// 検証状態のバッジ(未検証 / 検証済み / 不一致)
import { VERIFY_LABEL, type VerifyStatus } from '../../api/adminTypes'

export function VerifyBadge({ status, unsaved = false }: { status: VerifyStatus | 'new'; unsaved?: boolean }) {
  if (status === 'new') return <span className="vbadge vbadge-todo">未保存</span>
  return (
    <span className={`vbadge vbadge-${status}`}>
      {VERIFY_LABEL[status]}
      {unsaved && '(未保存の変更あり)'}
    </span>
  )
}
