// 演習セル(コードを書いて実行し、提出して採点する)
import { useCallback, useState } from 'react'
import { api } from '../api/client'
import type { Dataset, Exercise, SubmitResult } from '../api/types'
import { RunButton } from './CodeCell'
import { CodeEditor } from './CodeEditor'
import { CheckIcon } from './Icons'
import { Markdown } from './Markdown'
import { OutputView } from './OutputView'
import { useCellRunner } from './useCellRunner'

interface Props {
  ctx: string
  exercise: Exercise
  datasets: Dataset[]
  onSubmitted: (result: SubmitResult) => void
}

type Verdict = { passed: boolean; message: string } | null

export function ExerciseCell({ ctx, exercise, datasets, onSubmitted }: Props) {
  const [code, setCode] = useState(exercise.last_answer ?? exercise.starter_code)
  const [passed, setPassed] = useState(exercise.passed)
  const [showHint, setShowHint] = useState(false)
  const [verdict, setVerdict] = useState<Verdict>(null)
  const [submitting, setSubmitting] = useState(false)
  const { running, result, failure, run, clear } = useCellRunner(ctx, datasets)

  const onRun = useCallback(() => void run(code), [run, code])

  // 実行 → 結果を送信して採点
  const onSubmit = async () => {
    setSubmitting(true)
    setVerdict(null)
    try {
      const test = exercise.grading === 'test' ? exercise.test_code : undefined
      const res = await run(code, test)
      if (!res) return // 実行環境の問題(停止・読み込み失敗)は採点しない
      const graded = await api.submitCode(exercise.problem_id, {
        code,
        output: res.output,
        error: res.error,
        test_passed: res.test_passed,
      })
      // テストに落ちた場合は、テストのメッセージも表示する
      const message =
        !graded.passed && res.test_message ? `${graded.message}\n${res.test_message}` : graded.message
      setVerdict({ passed: graded.passed, message })
      if (graded.passed) setPassed(true)
      onSubmitted(graded)
    } catch (err) {
      setVerdict({ passed: false, message: err instanceof Error ? err.message : String(err) })
    } finally {
      setSubmitting(false)
    }
  }

  const onReset = () => {
    setCode(exercise.starter_code)
    setVerdict(null)
    clear()
  }

  const busy = running || submitting

  return (
    <section className="exercise" aria-label={exercise.title}>
      <div className="exercise-head">
        <span className="exercise-label">演習</span>
        <span className="exercise-title">{exercise.title}</span>
        {passed && (
          <span className="badge badge-pass">
            <CheckIcon size={12} />
            正解済み
          </span>
        )}
        <span className="exercise-grading">{exercise.grading === 'test' ? 'テストコードで採点' : '出力一致で採点'}</span>
      </div>
      <div className="exercise-prompt">
        <Markdown source={exercise.prompt} />
      </div>
      <div className="nb-cell">
        <RunButton running={running} onRun={onRun} label="演習セルを実行" primary />
        <div className="cell-box cell-box-exercise">
          <div className="cell-box-bar">
            <span>演習セル(編集できます)</span>
            <span className="mono">Python ・ ブラウザ実行</span>
          </div>
          <div className="cell-editor">
            <CodeEditor value={code} onChange={setCode} onRun={onRun} ariaLabel={`${exercise.title} のコード`} />
          </div>
          <OutputView result={result} failure={failure} />
        </div>
      </div>
      <div className="exercise-actions">
        <button type="button" className="btn btn-primary" onClick={() => void onSubmit()} disabled={busy}>
          {submitting ? '採点中…' : '提出して採点'}
        </button>
        {exercise.hint && (
          <button type="button" className="btn" onClick={() => setShowHint((v) => !v)} aria-expanded={showHint}>
            ヒント
          </button>
        )}
        <button type="button" className="btn" onClick={onReset} disabled={busy}>
          初期コードに戻す
        </button>
      </div>
      {showHint && <div className="exercise-hint">{exercise.hint}</div>}
      {verdict && (
        <div className={`verdict ${verdict.passed ? 'verdict-pass' : 'verdict-fail'}`} role="status">
          {verdict.passed && <CheckIcon size={18} />}
          <div>
            <b>{verdict.passed ? '正解です。' : 'まだ正解ではありません。'}</b>
            <span className="verdict-message">{verdict.message.replace(/^正解です。/, '')}</span>
          </div>
        </div>
      )}
    </section>
  )
}
