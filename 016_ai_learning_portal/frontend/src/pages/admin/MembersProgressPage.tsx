// メンバーの受講状況:メンバー × 公開中の講座の表と、選んだメンバーの詳細
import { useState } from 'react'
import { api } from '../../api/client'
import { AdminNav } from '../../components/admin/AdminNav'
import { formatDate, formatDateTime } from '../../components/format'
import { Header } from '../../components/Header'
import { CheckIcon } from '../../components/Icons'
import { useLoad } from '../useLoad'

function MemberDetail({ userId, name }: { userId: number; name: string }) {
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
  const members = data?.members ?? []
  const current = members.find((m) => m.id === selected) ?? members[0]
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
            <div className="muted small">学習の支援と講座改善のための情報です。人事評価には使用しません。</div>
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
          <span>— 未受講</span>
          <span className="spacer" />
          <span className="muted small">メンバー名を押すと詳細を表示します</span>
        </div>
        {data && (
          <div className="progress-layout">
            <div className="card list-card matrix-wrap">
              <table className="table matrix">
                <thead>
                  <tr>
                    <th>メンバー</th>
                    {data.courses.map((c) => (
                      <th key={c.id}>{c.title}</th>
                    ))}
                    <th>最終学習</th>
                  </tr>
                </thead>
                <tbody>
                  {members.map((m) => (
                    <tr key={m.id} className={current?.id === m.id ? 'row-selected' : ''}>
                      <td>
                        <button type="button" className="link-btn" onClick={() => setSelected(m.id)} aria-pressed={current?.id === m.id}>
                          {m.display_name}
                        </button>
                        {m.is_admin && <span className="muted small"> 管理者</span>}
                      </td>
                      {m.cells.map((c) => (
                        <td key={c.course_id}>
                          {c.state === 'completed' && (
                            <span className="cell-done">
                              <CheckIcon size={10} />
                              修了
                            </span>
                          )}
                          {c.state === 'in_progress' && (
                            <span className="cell-prog mono">
                              {c.done}/{c.total}
                            </span>
                          )}
                          {c.state === 'none' && <span className="muted">—</span>}
                        </td>
                      ))}
                      <td className="muted small">{m.last_activity ? formatDate(m.last_activity) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {data.courses.length === 0 && <div className="list-row muted">公開中の講座はありません。</div>}
            </div>
            <aside className="card side-card member-side">
              {current ? <MemberDetail key={current.id} userId={current.id} name={current.display_name} /> : <div className="muted">メンバーがいません</div>}
            </aside>
          </div>
        )}
      </main>
    </>
  )
}
