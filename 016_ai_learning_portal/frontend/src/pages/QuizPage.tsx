// 小テスト(全単元の完了後に受験できる。満点で講座修了。何度でも受け直せる)
import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { Quiz, QuizAnswer, QuizQuestion, QuizQuestionResult, QuizResult } from '../api/types'
import { RunButton } from '../components/CodeCell'
import { CodeEditor } from '../components/CodeEditor'
import { formatDate } from '../components/format'
import { Header } from '../components/Header'
import { CheckIcon } from '../components/Icons'
import { Markdown } from '../components/Markdown'
import { OutputView } from '../components/OutputView'
import type { RunResult } from '../python/protocol'
import { pythonRuntime } from '../python/runtime'
import { useLoad } from './useLoad'

const FORMAT_LABEL = { choice: '選択式', numeric: '数値入力', code: 'コード' } as const

type RunState = { result: RunResult | null; failure: string | null }

/** 採点結果の表示(正解なら解説、不正解なら復習する単元へのリンク) */
function Feedback({ result }: { result: QuizQuestionResult }) {
  if (result.correct) {
    return (
      <div className="verdict verdict-pass">
        <CheckIcon size={18} />
        <div>
          <b>正解</b>
          {result.explanation && <span className="verdict-message">　{result.explanation}</span>}
        </div>
      </div>
    )
  }
  return (
    <div className="verdict verdict-fail">
      <div>
        <b>{result.answered ? '不正解' : '未回答'}</b>
        {result.answered && result.message !== '不正解です。' && (
          <span className="verdict-message">　{result.message}</span>
        )}
        {result.related_unit && (
          <Link className="review-link" to={`/units/${result.related_unit.id}`}>
            復習:単元{result.related_unit.position} {result.related_unit.title}
          </Link>
        )}
      </div>
    </div>
  )
}

export function QuizPage() {
  const { slug = '' } = useParams()
  const { data: quiz, error, reload } = useLoad(() => api.quiz(slug), [slug])
  const [answers, setAnswers] = useState<Record<number, string>>({})
  const [codes, setCodes] = useState<Record<number, string>>({})
  const [runs, setRuns] = useState<Record<number, RunState>>({})
  const [running, setRunning] = useState<number | null>(null)
  const [grading, setGrading] = useState(false)
  const [gradeError, setGradeError] = useState<string | null>(null)
  const [result, setResult] = useState<QuizResult | null>(null)
  const ctx = `quiz-${slug}`

  // 問題を読み込んだら、コード問題に初期コードを入れる
  const init = useCallback((q: Quiz) => {
    setCodes(Object.fromEntries(q.questions.filter((x) => x.answer_format === 'code').map((x) => [x.problem_id, x.starter_code])))
    setAnswers({})
    setRuns({})
    setResult(null)
    setGradeError(null)
  }, [])
  const [initializedFor, setInitializedFor] = useState<string | null>(null)
  useEffect(() => {
    if (quiz && initializedFor !== quiz.course_slug) {
      init(quiz)
      setInitializedFor(quiz.course_slug)
    }
  }, [quiz, initializedFor, init])

  /** コード問題を1問実行する(失敗時は null) */
  const runCode = useCallback(
    async (q: QuizQuestion): Promise<RunResult | null> => {
      if (!quiz) return null
      setRunning(q.problem_id)
      try {
        const test = q.grading === 'test' ? q.test_code : undefined
        const res = await pythonRuntime.run(ctx, codes[q.problem_id] ?? '', quiz.datasets, test)
        setRuns((r) => ({ ...r, [q.problem_id]: { result: res, failure: null } }))
        return res
      } catch (err) {
        const failure = err instanceof Error ? err.message : String(err)
        setRuns((r) => ({ ...r, [q.problem_id]: { result: null, failure } }))
        return null
      } finally {
        setRunning(null)
      }
    },
    [quiz, codes, ctx],
  )

  // 採点:コード問題をすべて実行してから、回答をまとめて提出する
  const onGrade = async () => {
    if (!quiz) return
    setGrading(true)
    setGradeError(null)
    try {
      const payload: QuizAnswer[] = []
      for (const q of quiz.questions) {
        if (q.answer_format === 'code') {
          const res = await runCode(q)
          if (!res) throw new Error(`問${q.position} のコードを実行できませんでした。実行結果を確認してから、もう一度採点してください。`)
          payload.push({
            problem_id: q.problem_id,
            answer: codes[q.problem_id] ?? '',
            output: res.output,
            error: res.error,
            test_passed: res.test_passed,
          })
        } else if (answers[q.problem_id]?.trim()) {
          payload.push({ problem_id: q.problem_id, answer: answers[q.problem_id] })
        }
      }
      const res = await api.submitQuiz(slug, payload)
      setResult(res)
      reload()
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (err) {
      setGradeError(err instanceof Error ? err.message : String(err))
    } finally {
      setGrading(false)
    }
  }

  const onRetake = () => {
    if (quiz) init(quiz)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const header = (
    <Header
      breadcrumb={
        <>
          <Link to="/catalog">講座カタログ</Link> / <Link to={`/courses/${slug}`}>{quiz?.course_title ?? slug}</Link> /{' '}
          <span className="breadcrumb-current">小テスト</span>
        </>
      }
    />
  )

  if (error) {
    return (
      <>
        {header}
        <main className="page">
          <div className="form-error">{error}</div>
        </main>
      </>
    )
  }
  if (!quiz) return header

  // 全単元を完了していない場合は、受験できない理由を表示する
  if (!quiz.unlocked) {
    return (
      <>
        {header}
        <main className="page quiz-locked">
          <h1 className="page-title">小テスト</h1>
          <section className="card side-card">
            <h2>すべての単元を完了すると受験できます</h2>
            <p>単元の演習をすべて正解すると、その単元は完了になります。残りの単元は次のとおりです。</p>
            <ul>
              {quiz.remaining_units.map((u) => (
                <li key={u.id}>
                  <Link to={`/units/${u.id}`}>
                    単元{u.position} {u.title}
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        </main>
      </>
    )
  }

  const resultOf = (pid: number) => result?.results.find((r) => r.problem_id === pid) ?? null
  const answered = (q: QuizQuestion) =>
    q.answer_format === 'code'
      ? codes[q.problem_id] !== q.starter_code || runs[q.problem_id] !== undefined
      : Boolean(answers[q.problem_id]?.trim())
  const answeredCount = quiz.questions.filter(answered).length
  const busy = grading || running !== null

  return (
    <>
      {header}
      <div className="unit-layout">
        <nav className="unit-toc" aria-label="問題">
          <div className="toc-label">問題</div>
          {quiz.questions.map((q) => {
            const r = resultOf(q.problem_id)
            return (
              <a key={q.problem_id} className="toc-item quiz-nav" href={`#q-${q.problem_id}`}>
                <span className="mono">Q{q.position}</span>
                <span className="spacer">{FORMAT_LABEL[q.answer_format]}</span>
                <span className={`small ${r ? (r.correct ? 'accent' : 'warm') : 'muted'}`}>
                  {r ? (r.correct ? '正解' : '不正解') : answered(q) ? '回答済み' : '未回答'}
                </span>
              </a>
            )
          })}
          <div className="card quiz-count">
            <span className="muted small">回答済み</span>
            <span className="mono quiz-count-num">
              {answeredCount} / {quiz.questions.length}
            </span>
          </div>
          {quiz.attempts.length > 0 && (
            <div className="quiz-history">
              <div className="toc-label">受験履歴</div>
              {quiz.attempts.slice(0, 5).map((a) => (
                <div key={a.id} className="small quiz-history-row">
                  <span className="muted">{formatDate(a.created_at)}</span>
                  <span className={`mono ${a.score === a.total ? 'accent' : ''}`}>
                    {a.score} / {a.total}
                  </span>
                </div>
              ))}
            </div>
          )}
          <Link className="small quiz-back" to={`/courses/${slug}`}>
            講座の詳細に戻る
          </Link>
        </nav>

        <main className="unit-main">
          <div className="unit-column">
            <div className="unit-head">
              <div className="mono small warm">{quiz.course_title} ・ 小テスト</div>
              <h1 className="unit-title">小テスト</h1>
              <p className="quiz-lead">
                全{quiz.questions.length}問。<b>満点で講座修了</b>です。制限時間はなく、何度でも受け直せます。
                理解を確かめるためのテストなので、分からない問題は単元に戻って確認してください。
              </p>
            </div>

            {result?.perfect && (
              <section className="quiz-perfect" role="status">
                <span className="quiz-perfect-mark" aria-hidden="true">
                  <CheckIcon size={28} />
                </span>
                <div className="spacer">
                  <div className="mono">
                    {result.attempt.score} / {result.attempt.total} 正解
                  </div>
                  <div className="quiz-perfect-title">「{quiz.course_title}」を修了しました</div>
                  <div className="small">修了記録はマイ学習に残ります。</div>
                </div>
                <Link className="btn" to="/me">
                  マイ学習へ
                </Link>
              </section>
            )}
            {result && !result.perfect && (
              <section className="card quiz-notyet" role="status">
                <span className="mono quiz-score">
                  {result.attempt.score} / {result.attempt.total}
                </span>
                <div className="spacer">
                  <b>あと少しです。</b>
                  <div className="muted">間違えた問題の関連単元を確認してから、回答を直してもう一度採点できます。</div>
                </div>
                <button type="button" className="btn" onClick={onRetake}>
                  最初から受け直す
                </button>
              </section>
            )}
            {!result && quiz.completed && (
              <div className="verdict verdict-pass">
                <CheckIcon size={18} />
                <div>この講座は修了済みです。復習のために何度でも受け直せます。</div>
              </div>
            )}

            {quiz.questions.map((q) => {
              const r = resultOf(q.problem_id)
              return (
                <section key={q.problem_id} id={`q-${q.problem_id}`} className="exercise quiz-q">
                  <div className="exercise-head">
                    <span className="mono accent">Q{q.position}</span>
                    <span className="tag">{FORMAT_LABEL[q.answer_format]}</span>
                    {q.answer_format === 'code' && (
                      <span className="exercise-grading">{q.grading === 'test' ? 'テストコードで採点' : '出力一致で採点'}</span>
                    )}
                  </div>
                  <Markdown source={q.prompt} />

                  {q.answer_format === 'choice' && (
                    <fieldset className="choices">
                      <legend className="sr-only">Q{q.position} の選択肢</legend>
                      {q.choices.map((c) => (
                        <label key={c} className={`choice${answers[q.problem_id] === c ? ' choice-on' : ''}`}>
                          <input
                            type="radio"
                            name={`q-${q.problem_id}`}
                            value={c}
                            checked={answers[q.problem_id] === c}
                            onChange={() => setAnswers((a) => ({ ...a, [q.problem_id]: c }))}
                          />
                          {c}
                        </label>
                      ))}
                    </fieldset>
                  )}

                  {q.answer_format === 'numeric' && (
                    <label className="numeric">
                      解答
                      <input
                        inputMode="decimal"
                        value={answers[q.problem_id] ?? ''}
                        onChange={(e) => setAnswers((a) => ({ ...a, [q.problem_id]: e.target.value }))}
                        placeholder="数値を入力"
                      />
                    </label>
                  )}

                  {q.answer_format === 'code' && (
                    <div className="nb-cell">
                      <RunButton
                        running={running === q.problem_id}
                        onRun={() => void runCode(q)}
                        label={`Q${q.position} のコードを実行`}
                        primary
                      />
                      <div className="cell-box cell-box-exercise">
                        <div className="cell-editor">
                          <CodeEditor
                            value={codes[q.problem_id] ?? ''}
                            onChange={(v) => setCodes((c) => ({ ...c, [q.problem_id]: v }))}
                            onRun={() => void runCode(q)}
                            ariaLabel={`Q${q.position} のコード`}
                          />
                        </div>
                        <OutputView result={runs[q.problem_id]?.result ?? null} failure={runs[q.problem_id]?.failure ?? null} />
                      </div>
                    </div>
                  )}

                  {r && <Feedback result={r} />}
                </section>
              )
            })}

            {gradeError && <div className="form-error">{gradeError}</div>}
            <div className="quiz-submit">
              <span className="muted small">未回答の問題があっても採点できます</span>
              <button type="button" className="btn btn-primary btn-lg" onClick={() => void onGrade()} disabled={busy}>
                {grading ? '採点中…' : result ? 'もう一度採点する' : '採点する'}
              </button>
            </div>
          </div>
        </main>
      </div>
    </>
  )
}
