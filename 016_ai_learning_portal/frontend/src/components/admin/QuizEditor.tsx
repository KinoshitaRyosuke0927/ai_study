// 小テストの編集:選択式・数値入力・コードの問題を追加・並べ替え・保存・検証する
import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api/client'
import { emptyProblem, type AdminUnit, type AnswerFormat, type Problem, type ProblemIn, type VerifyStatus } from '../../api/adminTypes'
import type { Dataset } from '../../api/types'
import { Markdown } from '../Markdown'
import { CodeProblemEditor } from './CodeProblemEditor'
import { VerifyBadge } from './VerifyBadge'
import { verifyProblem } from './verify'

interface DraftQuestion {
  key: string
  problem: ProblemIn
  status: VerifyStatus | 'new'
  expected: string
}

let keySeq = 0
const toDrafts = (quiz: Problem[]): DraftQuestion[] =>
  quiz.map((p) => ({ key: `q-${p.id}`, problem: { ...p }, status: p.verify_status, expected: p.expected_output }))

const FORMAT_LABEL: Record<AnswerFormat, string> = { choice: '選択式', numeric: '数値入力', code: 'コード' }

interface Props {
  courseId: number
  quiz: Problem[]
  units: AdminUnit[]
  datasets: Dataset[]
  onSaved: (quiz: Problem[]) => void
  onDirtyChange: (dirty: boolean) => void
  /** 検証・「作成者の解答を正とする」の後に呼ばれる(目次の検証数を更新するため) */
  onVerified: () => void
}

export function QuizEditor({ courseId, quiz, units, datasets, onSaved, onDirtyChange, onVerified }: Props) {
  const [questions, setQuestions] = useState<DraftQuestion[]>(() => toDrafts(quiz))
  const [dirty, setDirtyState] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const [preview, setPreview] = useState<Record<string, boolean>>({})

  const setDirty = useCallback(
    (v: boolean) => {
      setDirtyState(v)
      onDirtyChange(v)
    },
    [onDirtyChange],
  )
  useEffect(() => {
    if (!dirty) return
    const handler = (e: BeforeUnloadEvent) => e.preventDefault()
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [dirty])

  const patch = (key: string, p: Partial<ProblemIn>) => {
    setQuestions((qs) => qs.map((q) => (q.key === key ? { ...q, problem: { ...q.problem, ...p } } : q)))
    setDirty(true)
  }
  const move = (index: number, delta: -1 | 1) => {
    setQuestions((qs) => {
      const next = [...qs]
      const t = index + delta
      if (t < 0 || t >= next.length) return qs
      ;[next[index], next[t]] = [next[t], next[index]]
      return next
    })
    setDirty(true)
  }
  const remove = (key: string) => {
    if (!window.confirm('この問題を削除しますか?')) return
    setQuestions((qs) => qs.filter((q) => q.key !== key))
    setDirty(true)
  }
  const add = (format: AnswerFormat) => {
    setQuestions((qs) => [...qs, { key: `new-${++keySeq}`, problem: emptyProblem(format), status: 'new', expected: '' }])
    setDirty(true)
  }

  const save = async (): Promise<Problem[] | null> => {
    setSaving(true)
    setMessage(null)
    try {
      const saved = await api.admin.saveQuiz(courseId, questions.map((q) => q.problem))
      // 保存前と同じキーを使い、編集中の部品(検証中の問題など)が作り直されないようにする
      setQuestions((prev) => toDrafts(saved).map((d, i) => ({ ...d, key: prev[i]?.key ?? d.key })))
      setDirty(false)
      setMessage({ ok: true, text: '保存しました' })
      onSaved(saved)
      return saved
    } catch (err) {
      setMessage({ ok: false, text: err instanceof Error ? err.message : String(err) })
      return null
    } finally {
      setSaving(false)
    }
  }

  const verifyAt = async (index: number) => {
    // 未保存の変更があれば先に保存する
    let source: Problem[] = quiz
    if (dirty || !questions[index].problem.id) {
      const saved = await save()
      if (!saved) throw new Error('保存に失敗したため検証できません。下のメッセージを確認してください。')
      source = saved
    }
    const problem = source[index]
    if (!problem) throw new Error('問題が見つかりません')
    const res = await verifyProblem(problem, datasets)
    onVerified()
    setQuestions((qs) => qs.map((q, i) => (i === index ? { ...q, status: res.verify_status, expected: res.expected_output } : q)))
    return res
  }

  const acceptAt = async (index: number, output: string) => {
    const id = questions[index].problem.id
    if (!id) throw new Error('先に保存してください')
    const res = await api.admin.acceptAuthor(id, output)
    onVerified()
    setQuestions((qs) => qs.map((q, i) => (i === index ? { ...q, status: res.verify_status, expected: res.expected_output } : q)))
    return res
  }

  /** 選択式・数値入力を、作成者が内容を確認したものとして検証済みにする */
  const confirmAt = async (index: number) => {
    const id = questions[index].problem.id
    if (!id || dirty) {
      setMessage({ ok: false, text: '先に小テストを保存してください' })
      return
    }
    try {
      const res = await api.admin.confirm(id)
      setQuestions((qs) => qs.map((q, i) => (i === index ? { ...q, status: res.verify_status } : q)))
      onVerified()
    } catch (err) {
      setMessage({ ok: false, text: err instanceof Error ? err.message : String(err) })
    }
  }

  const formats = questions.map((q) => q.problem.answer_format)

  return (
    <div className="unit-editor">
      <div className="ue-head">
        <div className="spacer">
          <div className="mono warm small">小テスト</div>
          <h2 className="ue-title-static">小テスト</h2>
          <div className="muted small">
            全{questions.length}問(選択式 {formats.filter((f) => f === 'choice').length}・数値入力 {formats.filter((f) => f === 'numeric').length}・コード{' '}
            {formats.filter((f) => f === 'code').length})。満点で講座修了です。単元の内容に合わせて、最も適した形式を選んでください。
          </div>
        </div>
      </div>

      {questions.length === 0 && <div className="muted ue-empty">問題がありません。下のボタンで追加してください。</div>}

      {questions.map((q, i) => {
        const p = q.problem
        return (
          <div key={q.key} className="ue-cell ue-cell-quiz">
            <div className="ue-cell-bar">
              <span className="ue-cell-type">
                Q{i + 1} {FORMAT_LABEL[p.answer_format]}
              </span>
              {p.answer_format !== 'code' && <VerifyBadge status={q.status} unsaved={dirty && q.status !== 'new'} />}
              <span className="spacer" />
              <label className="inline-select">
                関連単元
                <select
                  value={p.related_unit_id ?? ''}
                  onChange={(e) => patch(q.key, { related_unit_id: e.target.value ? Number(e.target.value) : null })}
                >
                  <option value="">なし</option>
                  {units.map((u) => (
                    <option key={u.id} value={u.id}>
                      単元{u.position} {u.title}
                    </option>
                  ))}
                </select>
              </label>
              <button type="button" className="icon-btn" aria-label="上へ移動" onClick={() => move(i, -1)} disabled={i === 0}>
                ↑
              </button>
              <button type="button" className="icon-btn" aria-label="下へ移動" onClick={() => move(i, 1)} disabled={i === questions.length - 1}>
                ↓
              </button>
              <button type="button" className="icon-btn" aria-label="問題を削除" onClick={() => remove(q.key)}>
                ×
              </button>
            </div>

            {p.answer_format === 'code' ? (
              <CodeProblemEditor
                problem={p}
                status={q.status}
                dirty={dirty}
                expectedOutput={q.expected}
                withTitle={false}
                onChange={(pp) => patch(q.key, pp)}
                onVerify={() => verifyAt(i)}
                onAcceptAuthor={(output) => acceptAt(i, output)}
              />
            ) : (
              <div className="form-stack qe-body">
                <div className="field">
                  <div className="field-head">
                    <span>問題文(Markdown)</span>
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => setPreview((v) => ({ ...v, [q.key]: !v[q.key] }))}>
                      {preview[q.key] ? '編集' : 'プレビュー'}
                    </button>
                  </div>
                  {preview[q.key] ? (
                    <div className="md-preview">
                      <Markdown source={p.prompt || '(問題文がありません)'} />
                    </div>
                  ) : (
                    <textarea rows={3} value={p.prompt} onChange={(e) => patch(q.key, { prompt: e.target.value })} />
                  )}
                </div>

                {p.answer_format === 'choice' && (
                  <fieldset className="choice-edit">
                    <legend>選択肢(正解を1つ選ぶ)</legend>
                    {p.choices.map((c, ci) => (
                      <div key={ci} className="choice-edit-row">
                        <input
                          type="radio"
                          name={`correct-${q.key}`}
                          aria-label={`選択肢 ${ci + 1} を正解にする`}
                          checked={c !== '' && p.correct_answer === c}
                          onChange={() => patch(q.key, { correct_answer: c })}
                        />
                        <input
                          className="spacer"
                          value={c}
                          aria-label={`選択肢 ${ci + 1}`}
                          onChange={(e) => {
                            const choices = [...p.choices]
                            const wasCorrect = p.correct_answer === choices[ci]
                            choices[ci] = e.target.value
                            patch(q.key, { choices, ...(wasCorrect ? { correct_answer: e.target.value } : {}) })
                          }}
                        />
                        <button
                          type="button"
                          className="icon-btn"
                          aria-label={`選択肢 ${ci + 1} を削除`}
                          onClick={() => patch(q.key, { choices: p.choices.filter((_, x) => x !== ci) })}
                          disabled={p.choices.length <= 2}
                        >
                          ×
                        </button>
                      </div>
                    ))}
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => patch(q.key, { choices: [...p.choices, ''] })}>
                      ＋ 選択肢を追加
                    </button>
                  </fieldset>
                )}

                {p.answer_format === 'numeric' && (
                  <div className="ue-info-row">
                    <label className="field field-narrow">
                      正解の数値
                      <input className="mono" value={p.correct_answer} onChange={(e) => patch(q.key, { correct_answer: e.target.value })} />
                    </label>
                    <label className="field field-narrow">
                      許容誤差
                      <input
                        className="mono"
                        value={String(p.tolerance)}
                        onChange={(e) => patch(q.key, { tolerance: Number(e.target.value) || 0 })}
                      />
                    </label>
                  </div>
                )}

                <label className="field">
                  解説(正解したときに表示)
                  <textarea rows={2} value={p.explanation} onChange={(e) => patch(q.key, { explanation: e.target.value })} />
                </label>
                {q.status !== 'verified' && p.id && (
                  <div className="pe-verify qe-confirm">
                    <span className="spacer muted small">問題文・選択肢・正解が正しいことを確認したら、検証済みにしてください(AI が作った問題など)。</span>
                    <button type="button" className="btn btn-sm btn-primary" onClick={() => void confirmAt(i)}>
                      内容を確認して検証済みにする
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        )
      })}

      <div className="ue-add">
        <button type="button" className="btn btn-sm" onClick={() => add('choice')}>
          ＋ 選択式
        </button>
        <button type="button" className="btn btn-sm" onClick={() => add('numeric')}>
          ＋ 数値入力
        </button>
        <button type="button" className="btn btn-sm" onClick={() => add('code')}>
          ＋ コード
        </button>
      </div>

      <div className="save-bar">
        {message && <span className={message.ok ? 'accent' : 'warm'}>{message.text}</span>}
        <span className="spacer muted small">{dirty ? '保存していない変更があります' : ''}</span>
        <button type="button" className="btn btn-primary" onClick={() => void save()} disabled={!dirty || saving}>
          {saving ? '保存中…' : '小テストを保存'}
        </button>
      </div>
    </div>
  )
}
