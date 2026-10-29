// メンバーの受講状況:メンバーごとの受講状況の一覧(講座数が増えても横に伸びない)と、選んだメンバーの詳細
import { useState } from 'react'
import type { ProgressCell, ProgressMatrix } from '../../api/adminTypes'
import { api } from '../../api/client'
import { AdminNav } from '../../components/admin/AdminNav'
import { formatDate, formatDateTime } from '../../components/format'
import { Header } from '../../components/Header'
import { CheckIcon } from '../../components/Icons'
import { useLoad } from '../useLoad'

type Course = ProgressMatrix['courses'][number]

/** 1講座分の状況を文言にする(ツールチップ用) */
function stateText(c: ProgressCell): string {
  if (c.state === 'completed') return '修了'
  if (c.state === 'in_progress') return `受講中 ${c.done}/${c.total}`
  return '未受講'
}

/** 1講座分の状況のバッジ(修了・受講中・未受講) */
function StateBadge({ cell }: { cell: ProgressCell | undefined }) {
  if (cell?.state === 'completed')
    return (
      <span className="cell-done">
        <CheckIcon size={10} />
        修了
      </span>
    )
  if (cell?.state === 'in_progress')
    return (
      <span className="cell-prog mono">
        {cell.done}/{cell.total}
      </span>
    )
  return <span className="muted">—</span>
}

function MemberDetail({ userId, name, courses, cells }: { userId: number; name: string; courses: Course[]; cells: ProgressCell[] }) {
  const { data: m, error } = useLoad(() => api.admin.member(userId), [userId])
  if (error) return <div className="form-error">{error}</div>
  if (!m) return <div className="muted small">読み込み中…</div>
  return (
    <div className="form-stack">
      <div className="member-name">{name}</div>
      <div className="stats stats-2">
        <div className="stat-box">
          <span className="stat-num">{m.completed_course_count}</span>
          <span className="stat-label">修了講座</span>
        </div>
        <div className="stat-box">
          <span className="stat-num">{m.in_progress_count}</span>
          <span className="stat-label">受講中</span>
        </div>
        <div className="stat-box">
          <span className="stat-num">{m.solved_exercise_count}</span>
          <span className="stat-label">解いた演習</span>
        </div>
        <div className="stat-box">
          <span className="stat-num">{m.quiz_attempt_count}</span>
          <span className="stat-label">小テスト受験</span>
        </div>
      </div>
      <div>
        <div className="field-label">講座ごとの状況</div>
        {courses.length === 0 && <div className="muted small">公開中の講座はありません</div>}
        {courses.map((c) => (
          <div key={c.id} className="kv small">
            <span>{c.title}</span>
            <StateBadge cell={cells.find((x) => x.course_id === c.id)} />
          </div>
        ))}
      </div>
      <div>
        <div className="field-label">受講中の講座</div>
        {m.in_progress.length === 0 && <div className="muted small">ありません</div>}
        {m.in_progress.map((c) => (
          <div key={c.slug} className="kv">
            <span>{c.title}</span>
            <span className="mono muted">
              {c.completed_unit_count} / {c.unit_count}
            </span>
          </div>
        ))}
      </div>
      <div>
        <div className="field-label">小テストの受験履歴</div>
        {m.quiz_history.length === 0 && <div className="muted small">ありません</div>}
        {m.quiz_history.slice(0, 6).map((h, i) => (
          <div key={i} className="kv small">
            <span>
              {h.course_title} <span className="muted">{formatDate(h.created_at)}</span>
            </span>
            <span className={`mono ${h.score === h.total ? 'accent' : ''}`}>
              {h.score} / {h.total}
            </span>
          </div>
        ))}
      </div>
      <div>
        <div className="field-label">最近の学習</div>
        {m.activities.slice(0, 5).map((a, i) => (
          <div key={i} className="kv small">
            <span>{a.text}</span>
            <span className="mono muted">{formatDateTime(a.at)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function MembersProgressPage() {
  const { data, error } = useLoad(() => api.admin.progress(), [])
  const [selected, setSelected] = useState<number | null>(null)
  // 状況を確認する講座(未選択なら講座ごとの状況は一覧の小さな四角で表示する)
  const [courseId, setCourseId] = useState<number | null>(null)
  const members = data?.members ?? []
  const courses = data?.courses ?? []
  const current = members.find((m) => m.id === selected) ?? members[0]
  const focusCourse = courses.find((c) => c.id === courseId)
  const activeCount = members.filter((m) => m.cells.some((c) => c.state !== 'none')).length
  const completedCount = members.filter((m) => m.cells.some((c) => c.state === 'completed')).length

  return (
    <>
      <Header />
      <AdminNav />
      <main className="page">
        <div className="page-head">
          <div className="spacer">
            <h1 className="page-title">メンバーの受講状況</h1>
          </div>
          {data && (
            <div className="stats stats-3 head-stats">
              <div className="card stat-card">
                <span className="stat-num">{members.length}</span>
                <span className="stat-label">登録メンバー</span>
              </div>
              <div className="card stat-card">
                <span className="stat-num">{activeCount}</span>
                <span className="stat-label">受講中の講座がある</span>
              </div>
              <div className="card stat-card">
                <span className="stat-num">{completedCount}</span>
                <span className="stat-label">1講座以上 修了</span>
              </div>
            </div>
          )}
        </div>
        {error && <div className="form-error">{error}</div>}
        <div className="legend">
          <span>
            <span className="cell-done legend-mark" />
            修了
          </span>
          <span>
            <span className="cell-prog legend-mark" />
            受講中(完了単元 / 全単元)
          </span>
          <span>
            <span className="dot-none legend-mark" />
            未受講
          </span>
          <label className="inline-select progress-course-select">
            講座を選んで確認
            <select value={courseId ?? ''} onChange={(e) => setCourseId(e.target.value ? Number(e.target.value) : null)}>
              <option value="">選択しない</option>
              {courses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                </option>
              ))}
            </select>
          </label>
          <span className="spacer" />
          <span className="muted small">メンバー名を押すと詳細を表示します。四角にカーソルを合わせると講座名を表示します</span>
        </div>
        {data && (
          <div className="progress-layout">
            <div className="card list-card table-scroll">
              <table className="table progress-table">
                <thead>
                  <tr>
                    <th>メンバー</th>
                    {focusCourse && <th className="focus-col">{focusCourse.title}</th>}
                    <th className="num">修了</th>
                    <th className="num">受講中</th>
                    <th>講座ごとの状況({courses.length}講座)</th>
                    <th>最終学習</th>
                  </tr>
                </thead>
                <tbody>
                  {members.map((m) => {
                    // 講座の並び順に合わせて状況を取り出す
                    const cells = courses.map((c) => m.cells.find((x) => x.course_id === c.id))
                    return (
                      <tr key={m.id} className={current?.id === m.id ? 'row-selected' : ''}>
                        <td className="nowrap">
                          <button type="button" className="link-btn" onClick={() => setSelected(m.id)} aria-pressed={current?.id === m.id}>
                            {m.display_name}
                          </button>
                          {m.is_admin && <span className="muted small"> 管理者</span>}
                        </td>
                        {focusCourse && (
                          <td className="focus-col nowrap">
                            <StateBadge cell={m.cells.find((x) => x.course_id === focusCourse.id)} />
                          </td>
                        )}
                        <td className="num mono">{m.cells.filter((c) => c.state === 'completed').length}</td>
                        <td className="num mono">{m.cells.filter((c) => c.state === 'in_progress').length}</td>
                        <td>
                          <div className="course-dots">
                            {courses.map((c, i) => {
                              const cell = cells[i]
                              const label = `${c.title}:${cell ? stateText(cell) : '未受講'}`
                              return (
                                <span
                                  key={c.id}
                                  className={`dot dot-${cell?.state ?? 'none'}${c.id === courseId ? ' dot-focus' : ''}`}
                                  title={label}
                                  aria-label={label}
                                  role="img"
                                />
                              )
                            })}
                          </div>
                        </td>
                        <td className="muted small nowrap">{m.last_activity ? formatDate(m.last_activity) : '—'}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              {courses.length === 0 && <div className="list-row muted">公開中の講座はありません。</div>}
            </div>
            <aside className="card side-card member-side">
              {current ? (
                <MemberDetail key={current.id} userId={current.id} name={current.display_name} courses={courses} cells={current.cells} />
              ) : (
                <div className="muted">メンバーがいません</div>
              )}
            </aside>
          </div>
        )}
      </main>
    </>
  )
}
