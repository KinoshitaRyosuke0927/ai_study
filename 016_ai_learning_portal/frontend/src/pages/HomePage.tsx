// ホーム(続きから学習・受講中の講座・学習ロードマップ・自分の学習状況・新着講座)
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { LEVEL_LABEL, type CourseLevel, type RoadmapCourse } from '../api/types'
import { CourseCard, nextAction } from '../components/CourseCard'
import { formatDate } from '../components/format'
import { Header } from '../components/Header'
import { CheckIcon, PlayIcon } from '../components/Icons'
import { ProgressBar } from '../components/Progress'
import { useLoad } from './useLoad'

const LEVELS: CourseLevel[] = ['basic', 'intermediate', 'advanced']

function RoadmapItem({ course }: { course: RoadmapCourse }) {
  return (
    <Link to={`/courses/${course.slug}`} className={`roadmap-item roadmap-${course.state}`}>
      {course.state === 'completed' ? <CheckIcon /> : <span className="roadmap-dot" aria-hidden="true" />}
      <span className="spacer">{course.title}</span>
      <span className="small">{course.state === 'completed' ? '修了' : course.state === 'in_progress' ? '受講中' : ''}</span>
    </Link>
  )
}

export function HomePage() {
  const { data: home, error } = useLoad(() => api.home(), [])

  return (
    <>
      <Header />
      <main className="page home">
        {error && <div className="form-error">{error}</div>}
        {home && (
          <div className="home-grid">
            <div className="home-main">
              {home.continue_course ? (
                <section className="card continue-card">
                  <div className="continue-body">
                    <div className="muted small">続きから学習</div>
                    <div className="continue-title">{home.continue_course.title}</div>
                    <div className="continue-sub">
                      {home.continue_unit_title
                        ? `次の単元:${home.continue_unit_title}`
                        : '全単元を完了しました。小テストで満点を取ると修了です。'}
                    </div>
                    <ProgressBar
                      done={home.continue_course.completed_unit_count}
                      total={home.continue_course.unit_count}
                      label={`${home.continue_course.completed_unit_count} / ${home.continue_course.unit_count} 単元`}
                    />
                  </div>
                  <Link className="btn btn-primary" to={nextAction(home.continue_course).to}>
                    <PlayIcon />
                    {home.continue_unit_title ? '続きから始める' : '小テストを受ける'}
                  </Link>
                </section>
              ) : (
                <section className="card continue-card">
                  <div className="continue-body">
                    <div className="continue-title">ようこそ</div>
                    <div className="continue-sub">講座カタログから講座を選んで、学習を始めましょう。</div>
                  </div>
                  <Link className="btn btn-primary" to="/catalog">
                    講座カタログを見る
                  </Link>
                </section>
              )}

              {home.in_progress.length > 0 && (
                <section className="home-section">
                  <h2 className="section-title">受講中の講座</h2>
                  <div className="course-grid course-grid-2">
                    {home.in_progress.map((c) => (
                      <CourseCard key={c.slug} course={c} compact />
                    ))}
                  </div>
                </section>
              )}

              <section className="home-section">
                <div className="section-head">
                  <h2 className="section-title">学習ロードマップ</h2>
                  <span className="muted small">基礎から順に受講すると、実践レベルまで無理なく進めます</span>
                </div>
                <div className="roadmap">
                  {LEVELS.map((level, i) => (
                    <div key={level} className="card roadmap-col">
                      <div className={`roadmap-step roadmap-step-${level}`}>
                        STEP {i + 1} {LEVEL_LABEL[level]}
                      </div>
                      {home.roadmap[level].length === 0 && <div className="muted small">講座はまだありません</div>}
                      {home.roadmap[level].map((c) => (
                        <RoadmapItem key={c.slug} course={c} />
                      ))}
                    </div>
                  ))}
                </div>
              </section>
            </div>

            <aside className="home-side">
              <section className="card side-card">
                <h2>自分の学習状況</h2>
                <div className="stats stats-3">
                  <div>
                    <span className="stat-num">{home.completed_course_count}</span>
                    <span className="stat-label">修了講座</span>
                  </div>
                  <div>
                    <span className="stat-num">{home.in_progress_count}</span>
                    <span className="stat-label">受講中</span>
                  </div>
                  <div>
                    <span className="stat-num">{home.solved_exercise_count}</span>
                    <span className="stat-label">解いた演習</span>
                  </div>
                </div>
                <Link to="/me">マイ学習を見る</Link>
              </section>
              <section className="card side-card">
                <h2>新着講座</h2>
                {home.new_courses.length === 0 && <div className="muted small">新着講座はありません</div>}
                {home.new_courses.map((c) => (
                  <Link key={c.slug} to={`/courses/${c.slug}`} className="new-course">
                    <span className="new-course-title">{c.title}</span>
                    <span className="muted small">
                      {LEVEL_LABEL[c.level]} ・ 全{c.unit_count}単元 ・ {formatDate(c.published_at)}
                    </span>
                  </Link>
                ))}
              </section>
            </aside>
          </div>
        )}
      </main>
    </>
  )
}
