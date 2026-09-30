// 単元画面(ノートブック型:説明セル・例題セル・演習セルを縦に並べる)
import { useCallback, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { SubmitResult, UnitDetail } from '../api/types'
import { CodeCell } from '../components/CodeCell'
import { ExerciseCell } from '../components/ExerciseCell'
import { Header } from '../components/Header'
import { CheckIcon, ResetIcon } from '../components/Icons'
import { Markdown, headingId } from '../components/Markdown'
import { pythonRuntime, useRuntimeStatus } from '../python/runtime'
import { useLoad } from './useLoad'

/** 説明セルの「## 見出し」を目次用に取り出す */
function sectionsOf(unit: UnitDetail): { id: string; label: string }[] {
  const sections: { id: string; label: string }[] = []
  if (unit.goals.length > 0) sections.push({ id: 'sec-goals', label: '学習目標' })
  for (const cell of unit.cells) {
    if (cell.cell_type === 'markdown') {
      for (const line of cell.source.split('\n')) {
        const m = /^##\s+(.+)$/.exec(line.trim())
        if (m) sections.push({ id: headingId(m[1]), label: m[1] })
      }
    } else if (cell.exercise) {
      sections.push({ id: `ex-${cell.exercise.problem_id}`, label: cell.exercise.title })
    }
  }
  return sections
}

function RuntimeBadge() {
  const status = useRuntimeStatus()
  const label: Record<typeof status, string> = {
    idle: '未起動(初回の実行時に準備します)',
    loading: 'Python 実行環境を準備中…',
    installing: 'ライブラリを読み込み中…',
    ready: '準備完了',
    running: '実行中…',
    failed: '読み込みに失敗しました',
  }
  return (
    <span className={`runtime-badge runtime-${status}`} role="status">
      <span className="runtime-dot" aria-hidden="true" />
      Python:{label[status]}
    </span>
  )
}

export function UnitPage() {
  const { unitId = '' } = useParams()
  const id = Number(unitId)
  const { data: unit, error, reload } = useLoad(() => api.unit(id), [id])
  const [justCompleted, setJustCompleted] = useState(false)
  const ctx = `unit-${id}`

  const onSubmitted = useCallback(
    (res: SubmitResult) => {
      // 単元の演習をすべて正解したら、完了の表示と目次を更新する
      if (res.unit_newly_completed) {
        setJustCompleted(true)
        reload()
      }
    },
    [reload],
  )

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
  if (!unit || unit.id !== id) return <Header />

  const sections = sectionsOf(unit)
  let exerciseNo = 0

  return (
    <>
      <Header
        breadcrumb={
          <>
            <Link to="/catalog">講座カタログ</Link> / <Link to={`/courses/${unit.course_slug}`}>{unit.course_title}</Link> /{' '}
            <span className="breadcrumb-current">
              単元{unit.position} {unit.title}
            </span>
          </>
        }
      />
      <div className="unit-layout">
        <nav className="unit-toc" aria-label="目次">
          <div className="toc-label">目次</div>
          {unit.units.map((u) =>
            u.id === unit.id ? (
              <div key={u.id}>
                <div className="toc-item toc-current">
                  {u.completed && <CheckIcon />}
                  {u.position}. {u.title}
                </div>
                {sections.map((s) => (
                  <a key={s.id} className="toc-sub" href={`#${s.id}`}>
                    {s.label}
                  </a>
                ))}
              </div>
            ) : (
              <Link key={u.id} className="toc-item" to={`/units/${u.id}`}>
                {u.completed ? <CheckIcon className="accent" /> : <span className="toc-spacer" />}
                {u.position}. {u.title}
              </Link>
            ),
          )}
          {unit.units.every((u) => u.completed) ? (
            <Link className="toc-item toc-quiz toc-quiz-open" to={`/courses/${unit.course_slug}/quiz`}>
              小テスト
            </Link>
          ) : (
            <div className="toc-item toc-quiz" title="すべての単元を完了すると受験できます">
              小テスト(全単元の完了後)
            </div>
          )}
        </nav>

        <main className="unit-main">
          <div className="unit-column">
            <div className="unit-head">
              <div className="mono accent small">
                {unit.course_title} ・ 単元 {unit.position} / {unit.unit_count}
              </div>
              <h1 className="unit-title">{unit.title}</h1>
              <div className="unit-head-row">
                <span className="muted small">
                  目安 {unit.estimated_minutes}分 ・ 演習 {unit.exercise_count}問
                </span>
                {unit.completed && (
                  <span className="badge badge-pass">
                    <CheckIcon size={12} />
                    完了
                  </span>
                )}
                <span className="spacer" />
                <RuntimeBadge />
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => void pythonRuntime.reset(ctx)}
                  title="この単元で作った変数をすべて消します"
                >
                  <ResetIcon />
                  変数をリセット
                </button>
              </div>
            </div>

            {unit.goals.length > 0 && (
              <section id="sec-goals" className="card goals">
                <div className="goals-title">学習目標</div>
                <ul>
                  {unit.goals.map((g) => (
                    <li key={g}>{g}</li>
                  ))}
                </ul>
              </section>
            )}

            {unit.cells.map((cell) => {
              if (cell.cell_type === 'markdown') {
                return <Markdown key={cell.id} source={cell.source} />
              }
              if (cell.cell_type === 'code') {
                return <CodeCell key={cell.id} ctx={ctx} source={cell.source} datasets={unit.datasets} />
              }
              if (!cell.exercise) return null
              exerciseNo += 1
              return (
                <div key={cell.id} id={`ex-${cell.exercise.problem_id}`}>
                  <ExerciseCell
                    ctx={ctx}
                    exercise={{ ...cell.exercise, title: `${unit.position}-${exerciseNo} ${cell.exercise.title}` }}
                    datasets={unit.datasets}
                    onSubmitted={onSubmitted}
                  />
                </div>
              )
            })}

            {justCompleted && (
              <div className="verdict verdict-pass unit-complete" role="status">
                <CheckIcon size={20} />
                <div>
                  <b>この単元を完了しました。</b>
                  {unit.next_unit
                    ? '次の単元に進みましょう。'
                    : unit.units.every((u) => u.completed)
                      ? 'すべての単元を完了しました。小テストに挑戦しましょう。'
                      : 'まだ完了していない単元があります。'}
                </div>
              </div>
            )}

            <div className="unit-footer">
              {unit.prev_unit ? (
                <Link to={`/units/${unit.prev_unit.id}`}>前の単元:{unit.prev_unit.title}</Link>
              ) : (
                <Link to={`/courses/${unit.course_slug}`}>講座の詳細へ</Link>
              )}
              {unit.next_unit ? (
                <Link className="btn btn-dark" to={`/units/${unit.next_unit.id}`}>
                  次の単元:{unit.next_unit.title}
                </Link>
              ) : unit.units.every((u) => u.completed) ? (
                <Link className="btn btn-dark" to={`/courses/${unit.course_slug}/quiz`}>
                  小テストへ
                </Link>
              ) : (
                <Link className="btn btn-dark" to={`/courses/${unit.course_slug}`}>
                  講座の詳細へ
                </Link>
              )}
            </div>
          </div>
        </main>
      </div>
    </>
  )
}
