// 講座一覧(フェーズ2でホーム画面・講座カタログに発展させる)
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { Header } from '../components/Header'
import { LevelTag, ProgressBar } from '../components/Progress'
import { useLoad } from './useLoad'

export function CourseListPage() {
  const { data: courses, error } = useLoad(() => api.courses(), [])

  return (
    <>
      <Header />
      <main className="page">
        <h1 className="page-title">講座一覧</h1>
        {error && <div className="form-error">{error}</div>}
        {courses && courses.length === 0 && <p className="muted">公開中の講座はまだありません。</p>}
        <div className="course-grid">
          {courses?.map((c) => (
            <article key={c.slug} className="card course-card">
              <div className="tag-row">
                <LevelTag level={c.level} />
                {c.tags.map((t) => (
                  <span key={t} className="tag">
                    {t}
                  </span>
                ))}
                {c.status === 'draft' && <span className="tag tag-draft">下書き</span>}
              </div>
              <h2 className="course-card-title">
                <Link to={`/courses/${c.slug}`}>{c.title}</Link>
              </h2>
              <p className="course-card-summary">{c.summary}</p>
              <div className="muted small">
                全{c.unit_count}単元 ・ 演習 {c.exercise_count}問 ・ 目安 約{Math.round(c.estimated_minutes / 60 * 10) / 10}時間
              </div>
              <ProgressBar done={c.completed_unit_count} total={c.unit_count} label={`${c.completed_unit_count} / ${c.unit_count} 単元`} />
              <div className="card-actions">
                {c.next_unit_id ? (
                  <Link className="btn btn-primary" to={`/units/${c.next_unit_id}`}>
                    {c.completed_unit_count > 0 ? '続きから学習' : '受講を始める'}
                  </Link>
                ) : (
                  <span className="badge badge-pass">全単元完了</span>
                )}
                <Link className="btn" to={`/courses/${c.slug}`}>
                  講座の詳細
                </Link>
              </div>
            </article>
          ))}
        </div>
      </main>
    </>
  )
}
