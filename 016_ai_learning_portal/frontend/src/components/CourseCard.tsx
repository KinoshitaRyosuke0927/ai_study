// 講座カード(講座カタログ・ホームで使う)
import { Link } from 'react-router-dom'
import type { CourseSummary } from '../api/types'
import { formatMinutes } from './format'
import { CheckIcon } from './Icons'
import { LevelTag, ProgressBar } from './Progress'

/** 講座の状態(修了・小テスト待ち・受講中・未受講)を1行で表す */
export function courseStatusLabel(c: CourseSummary): string {
  if (c.completed) return '修了'
  if (c.quiz_unlocked) return c.best_quiz_score === null ? '小テスト未受験' : '小テスト再挑戦中'
  if (c.completed_unit_count > 0) return '受講中'
  return '未受講'
}

/** 次に進む先(未完了の単元 → 小テスト → 講座詳細) */
export function nextAction(c: CourseSummary): { to: string; label: string } {
  if (c.next_unit_id) {
    return { to: `/units/${c.next_unit_id}`, label: c.completed_unit_count > 0 ? '続きから学習' : '受講を始める' }
  }
  if (!c.completed) return { to: `/courses/${c.slug}/quiz`, label: '小テストを受ける' }
  return { to: `/courses/${c.slug}`, label: '講座を見直す' }
}

export function CourseCard({ course: c, compact = false }: { course: CourseSummary; compact?: boolean }) {
  const action = nextAction(c)
  return (
    <article className="card course-card">
      <div className="tag-row">
        <LevelTag level={c.level} />
        {c.tags.map((t) => (
          <span key={t} className="tag">
            {t}
          </span>
        ))}
        {c.status === 'draft' && <span className="tag tag-draft">下書き</span>}
        <span className="spacer" />
        {c.completed ? (
          <span className="badge badge-pass">
            <CheckIcon size={12} />
            修了
          </span>
        ) : (
          <span className="muted small">{courseStatusLabel(c)}</span>
        )}
      </div>
      <h2 className="course-card-title">
        <Link to={`/courses/${c.slug}`}>{c.title}</Link>
      </h2>
      {!compact && <p className="course-card-summary">{c.summary}</p>}
      {!compact && (
        <div className="muted small">
          全{c.unit_count}単元 ・ 演習 {c.exercise_count}問 ・ 小テスト {c.quiz_question_count}問 ・ 目安 {formatMinutes(c.estimated_minutes)}
        </div>
      )}
      <ProgressBar done={c.completed_unit_count} total={c.unit_count} label={`${c.completed_unit_count} / ${c.unit_count} 単元`} />
      <div className="card-actions">
        <Link className={`btn ${c.completed ? '' : 'btn-primary'}`} to={action.to}>
          {action.label}
        </Link>
        {!compact && (
          <Link className="btn" to={`/courses/${c.slug}`}>
            講座の詳細
          </Link>
        )}
      </div>
    </article>
  )
}
