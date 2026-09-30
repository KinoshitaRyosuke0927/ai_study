// 講座詳細(概要・進捗・単元一覧)
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { Header } from '../components/Header'
import { CheckIcon, PlayIcon } from '../components/Icons'
import { LevelTag, ProgressBar } from '../components/Progress'
import { useLoad } from './useLoad'

export function CourseDetailPage() {
  const { slug = '' } = useParams()
  const { data: course, error } = useLoad(() => api.course(slug), [slug])

  if (error) {
    return (
      <>
        <Header />
        <main className="page">
          <div className="form-error">{error}</div>
        </main>
      </>
    )
  }
  if (!course) return <Header />

  const nextUnit = course.units.find((u) => u.id === course.next_unit_id)

  return (
    <>
      <Header />
      <section className="course-hero">
        <div className="course-hero-main">
          <div className="muted small">
            <Link to="/catalog">講座カタログ</Link> / {course.title}
          </div>
          <div className="tag-row">
            <LevelTag level={course.level} />
            {course.tags.map((t) => (
              <span key={t} className="tag">
                {t}
              </span>
            ))}
            {course.status === 'draft' && <span className="tag tag-draft">下書き</span>}
          </div>
          <h1 className="course-hero-title">{course.title}</h1>
          <p className="course-hero-summary">{course.summary}</p>
          <div className="meta-row">
            <span>全{course.unit_count}単元</span>
            <span>目安 約{Math.round((course.estimated_minutes / 60) * 10) / 10}時間</span>
            <span>演習 {course.exercise_count}問</span>
            <span>小テスト {course.quiz_question_count}問</span>
            {course.author_name && <span>作成者 {course.author_name}</span>}
          </div>
        </div>
        <div className="card progress-card">
          <div className="progress-card-head">
            <b>あなたの進捗</b>
            <span className="mono muted">
              {course.completed_unit_count} / {course.unit_count} 単元
            </span>
          </div>
          <ProgressBar done={course.completed_unit_count} total={course.unit_count} />
          {course.completed ? (
            <div className="verdict verdict-pass">
              <CheckIcon size={18} />
              <div>この講座を修了しました</div>
            </div>
          ) : nextUnit ? (
            <Link className="btn btn-primary btn-block" to={`/units/${nextUnit.id}`}>
              <PlayIcon />
              {course.completed_unit_count > 0 ? '続きから' : '受講を始める'}:単元{nextUnit.position} {nextUnit.title}
            </Link>
          ) : (
            <Link className="btn btn-primary btn-block" to={`/courses/${course.slug}/quiz`}>
              <PlayIcon />
              小テストを受ける(満点で修了)
            </Link>
          )}
        </div>
      </section>

      <main className="page course-body">
        <section className="unit-list">
          <h2 className="section-title">単元</h2>
          {course.units.map((u) => {
            const current = u.id === course.next_unit_id
            return (
              <Link
                key={u.id}
                to={`/units/${u.id}`}
                className={`unit-row${current ? ' unit-row-current' : ''}`}
              >
                <span className={`unit-no${u.completed ? ' unit-no-done' : current ? ' unit-no-current' : ''}`}>
                  {u.completed ? <CheckIcon /> : u.position}
                </span>
                <span className="unit-row-main">
                  <span className="unit-row-title">
                    {u.position}. {u.title}
                  </span>
                  <span className="muted small">{u.summary}</span>
                </span>
                <span className="unit-row-meta muted small">
                  {u.estimated_minutes}分 ・ 演習{u.exercise_count}問
                  <br />
                  <span className={u.completed || current ? 'accent' : ''}>
                    {u.completed ? '完了' : current ? '次に学習' : '未受講'}
                  </span>
                </span>
              </Link>
            )
          })}
          {course.quiz_unlocked ? (
            <Link to={`/courses/${course.slug}/quiz`} className="unit-row unit-row-quiz">
              <span className="unit-row-main">
                <span className="unit-row-title">小テスト</span>
                <span className="small">
                  全{course.quiz_question_count}問。満点で講座修了。何度でも受け直せます
                </span>
              </span>
              <span className="unit-row-meta small warm">
                {course.completed
                  ? '修了済み'
                  : course.best_quiz_score === null
                    ? '受験する'
                    : `最高 ${course.best_quiz_score} / ${course.quiz_question_count}`}
              </span>
            </Link>
          ) : (
            <div className="unit-row unit-row-quiz unit-row-locked" aria-disabled="true">
              <span className="unit-row-main">
                <span className="unit-row-title">小テスト</span>
                <span className="small">全{course.quiz_question_count}問。すべての単元を完了すると受験できます</span>
              </span>
              <span className="unit-row-meta small muted">
                あと {course.unit_count - course.completed_unit_count} 単元
              </span>
            </div>
          )}
        </section>

        <aside className="side">
          {course.outcomes.length > 0 && (
            <section className="card side-card">
              <h2>この講座で身につくこと</h2>
              <ul>
                {course.outcomes.map((o) => (
                  <li key={o}>{o}</li>
                ))}
              </ul>
            </section>
          )}
          {course.prerequisites.length > 0 && (
            <section className="card side-card">
              <h2>前提となる講座</h2>
              {course.prerequisites.map((p) => (
                <div key={p.slug} className="prereq">
                  {p.completed && <CheckIcon />}
                  <Link to={`/courses/${p.slug}`}>{p.title}</Link>
                  {p.completed && <span className="muted small">修了済み</span>}
                </div>
              ))}
            </section>
          )}
          <section className="side-card side-card-dashed">
            <h2>学習環境</h2>
            <p>コードはブラウザ内で実行されます。環境構築は不要です。</p>
            {course.libraries.length > 0 && <p>使用ライブラリ:{course.libraries.join(' / ')}</p>}
            {course.datasets.length > 0 && <p>データ:{course.datasets.map((d) => d.filename).join(', ')}</p>}
          </section>
        </aside>
      </main>
    </>
  )
}
