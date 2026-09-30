// マイページ(自分の受講状況・修了した講座・小テストの受験履歴・最近の学習)
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { nextAction } from '../components/CourseCard'
import { formatDate, formatDateTime } from '../components/format'
import { Header } from '../components/Header'
import { CheckIcon } from '../components/Icons'
import { LevelTag, ProgressBar } from '../components/Progress'
import { useAuth } from '../auth/AuthContext'
import { useLoad } from './useLoad'

export function MyPage() {
  const { user } = useAuth()
  const { data: me, error } = useLoad(() => api.myPage(), [])

  return (
    <>
      <Header />
      <main className="page">
        <section className="my-head">
          <div className="my-name">
            <h1 className="page-title">{user?.display_name} さんの学習</h1>
            <div className="muted small">この画面の内容は、あなたと管理者だけが見られます。</div>
          </div>
          {me && (
            <div className="stats stats-4">
              <div className="card stat-card">
                <span className="stat-num">{me.completed_course_count}</span>
                <span className="stat-label">修了講座</span>
              </div>
              <div className="card stat-card">
                <span className="stat-num">{me.in_progress_count}</span>
                <span className="stat-label">受講中</span>
              </div>
              <div className="card stat-card">
                <span className="stat-num">{me.solved_exercise_count}</span>
                <span className="stat-label">解いた演習</span>
              </div>
              <div className="card stat-card">
                <span className="stat-num">{me.quiz_attempt_count}</span>
                <span className="stat-label">小テスト受験回数</span>
              </div>
            </div>
          )}
        </section>
        {error && <div className="form-error">{error}</div>}
        {me && (
          <div className="my-grid">
            <div className="my-main">
              <section>
                <h2 className="section-title">受講中の講座</h2>
                <div className="card list-card">
                  {me.in_progress.length === 0 && (
                    <div className="list-row muted">
                      受講中の講座はありません。<Link to="/catalog">講座カタログ</Link>から始めましょう。
                    </div>
                  )}
                  {me.in_progress.map((c) => {
                    const action = nextAction(c)
                    return (
                      <div key={c.slug} className="list-row">
                        <div className="spacer list-main">
                          <div className="list-title">
                            <Link to={`/courses/${c.slug}`}>{c.title}</Link>
                            <LevelTag level={c.level} />
                          </div>
                          <div className="list-meta">
                            <ProgressBar
                              done={c.completed_unit_count}
                              total={c.unit_count}
                              label={`${c.completed_unit_count} / ${c.unit_count} 単元`}
                            />
                            <span className="muted small">
                              小テスト:
                              {c.best_quiz_score === null
                                ? c.quiz_unlocked
                                  ? '受験できます'
                                  : '全単元の完了後に受験できます'
                                : `最高 ${c.best_quiz_score} / ${c.quiz_question_count}`}
                            </span>
                          </div>
                        </div>
                        <Link className="btn btn-primary" to={action.to}>
                          {action.label}
                        </Link>
                      </div>
                    )
                  })}
                </div>
              </section>

              <section>
                <h2 className="section-title">修了した講座</h2>
                <div className="card list-card">
                  {me.completed.length === 0 && <div className="list-row muted">修了した講座はまだありません。</div>}
                  {me.completed.map((c) => (
                    <div key={c.slug} className="list-row">
                      <span className="done-mark" aria-hidden="true">
                        <CheckIcon size={18} />
                      </span>
                      <div className="spacer list-main">
                        <Link to={`/courses/${c.slug}`} className="list-title">
                          {c.title}
                        </Link>
                        <span className="muted small">
                          修了日 {formatDate(c.completed_at)} ・ 小テスト満点(受験 {c.attempt_count}回)
                        </span>
                      </div>
                      <Link to={`/courses/${c.slug}`}>見直す</Link>
                    </div>
                  ))}
                </div>
              </section>
            </div>

            <aside className="my-side">
              <section>
                <h2 className="section-title">小テストの受験履歴</h2>
                <div className="card list-card">
                  {me.quiz_history.length === 0 && <div className="list-row muted">まだ受験していません。</div>}
                  {me.quiz_history.length > 0 && (
                    <table className="table">
                      <thead>
                        <tr>
                          <th>講座</th>
                          <th>受験日</th>
                          <th className="num">得点</th>
                        </tr>
                      </thead>
                      <tbody>
                        {me.quiz_history.map((h, i) => (
                          <tr key={i}>
                            <td>
                              <Link to={`/courses/${h.course_slug}/quiz`}>{h.course_title}</Link>
                            </td>
                            <td className="muted">{formatDate(h.created_at)}</td>
                            <td className={`num mono ${h.score === h.total ? 'accent' : 'warm'}`}>
                              {h.score} / {h.total}
                              {h.score === h.total ? ' 満点' : ''}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </section>
              <section>
                <h2 className="section-title">最近の学習</h2>
                <div className="card list-card">
                  {me.activities.length === 0 && <div className="list-row muted">まだ記録はありません。</div>}
                  {me.activities.map((a, i) => (
                    <div key={i} className="activity">
                      <span className="mono muted small activity-at">{formatDateTime(a.at)}</span>
                      <span>{a.text}</span>
                    </div>
                  ))}
                </div>
              </section>
            </aside>
          </div>
        )}
      </main>
    </>
  )
}
