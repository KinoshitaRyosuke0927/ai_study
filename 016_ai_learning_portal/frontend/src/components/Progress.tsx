// 進捗バーとレベルのタグ
import { LEVEL_LABEL, type CourseLevel } from '../api/types'

export function ProgressBar({ done, total, label }: { done: number; total: number; label?: string }) {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0
  return (
    <div className="progress-row">
      <div className="progress" role="progressbar" aria-valuenow={done} aria-valuemin={0} aria-valuemax={total}>
        <div className="progress-fill" style={{ width: `${pct}%` }} />
      </div>
      {label && <span className="progress-label mono">{label}</span>}
    </div>
  )
}

export function LevelTag({ level }: { level: CourseLevel }) {
  return <span className="tag tag-level">{LEVEL_LABEL[level]}</span>
}
