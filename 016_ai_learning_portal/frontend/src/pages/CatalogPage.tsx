// 講座カタログ(レベル・状態・タグ・キーワードで絞り込み)
import { useMemo, useState } from 'react'
import { api } from '../api/client'
import { LEVEL_LABEL, type CourseLevel, type CourseSummary } from '../api/types'
import { CourseCard } from '../components/CourseCard'
import { Header } from '../components/Header'
import { useLoad } from './useLoad'

type StatusFilter = 'all' | 'in_progress' | 'not_started' | 'completed'

const STATUS_LABEL: Record<StatusFilter, string> = {
  all: 'すべて',
  in_progress: '受講中',
  not_started: '未受講',
  completed: '修了',
}

function statusOf(c: CourseSummary): StatusFilter {
  if (c.completed) return 'completed'
  if (c.completed_unit_count > 0 || c.best_quiz_score !== null) return 'in_progress'
  return 'not_started'
}

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: string }) {
  return (
    <button type="button" className={`chip${on ? ' chip-on' : ''}`} aria-pressed={on} onClick={onClick}>
      {children}
    </button>
  )
}

export function CatalogPage() {
  const { data: courses, error } = useLoad(() => api.courses(), [])
  const [level, setLevel] = useState<CourseLevel | 'all'>('all')
  const [status, setStatus] = useState<StatusFilter>('all')
  const [tag, setTag] = useState<string | null>(null)
  const [keyword, setKeyword] = useState('')

  const tags = useMemo(() => [...new Set((courses ?? []).flatMap((c) => c.tags))].sort(), [courses])

  const visible = (courses ?? []).filter((c) => {
    if (level !== 'all' && c.level !== level) return false
    if (status !== 'all' && statusOf(c) !== status) return false
    if (tag && !c.tags.includes(tag)) return false
    const kw = keyword.trim().toLowerCase()
    if (kw && !`${c.title} ${c.summary} ${c.tags.join(' ')}`.toLowerCase().includes(kw)) return false
    return true
  })

  return (
    <>
      <Header />
      <main className="page">
        <h1 className="page-title">講座カタログ</h1>
        <div className="filters">
          <div className="filter-row">
            <span className="filter-label">レベル</span>
            <Chip on={level === 'all'} onClick={() => setLevel('all')}>
              すべて
            </Chip>
            {(Object.keys(LEVEL_LABEL) as CourseLevel[]).map((l) => (
              <Chip key={l} on={level === l} onClick={() => setLevel(l)}>
                {LEVEL_LABEL[l]}
              </Chip>
            ))}
            <span className="filter-label filter-gap">状態</span>
            {(Object.keys(STATUS_LABEL) as StatusFilter[]).map((s) => (
              <Chip key={s} on={status === s} onClick={() => setStatus(s)}>
                {STATUS_LABEL[s]}
              </Chip>
            ))}
            <span className="spacer" />
            <label className="search">
              検索
              <input value={keyword} onChange={(e) => setKeyword(e.target.value)} placeholder="講座名・タグ" />
            </label>
          </div>
          {tags.length > 0 && (
            <div className="filter-row">
              <span className="filter-label">タグ</span>
              <Chip on={tag === null} onClick={() => setTag(null)}>
                すべて
              </Chip>
              {tags.map((t) => (
                <Chip key={t} on={tag === t} onClick={() => setTag(t)}>
                  {t}
                </Chip>
              ))}
            </div>
          )}
        </div>
        {error && <div className="form-error">{error}</div>}
        {courses && visible.length === 0 && <p className="muted">条件に合う講座はありません。</p>}
        <div className="course-grid">
          {visible.map((c) => (
            <CourseCard key={c.slug} course={c} />
          ))}
        </div>
      </main>
    </>
  )
}
