// 小テストの編集:選択式・数値入力・表形式・コードの問題を追加・並べ替え・保存・検証する
import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api/client'
import { emptyProblem, type AdminUnit, type AnswerFormat, type Problem, type ProblemIn, type VerifyStatus } from '../../api/adminTypes'
import type { Dataset } from '../../api/types'
import { FORMAT_LABEL } from '../AnswerInput'
import { CodeProblemEditor } from './CodeProblemEditor'
import { KeyedProblemEditor } from './KeyedProblemEditor'
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

  /** 選択式・数値入力・表形式を、作成者が内容を確認したものとして検証済みにする */
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
            全{questions.length}問(
            {(['choice', 'numeric', 'matrix', 'code'] as const)
              .map((f) => `${FORMAT_LABEL[f]} ${formats.filter((x) => x === f).length}`)
              .join('・')}
            )。満点で講座修了です。単元の内容に合わせて、最も適した形式を選んでください。
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
              <KeyedProblemEditor
                problem={p}
                name={q.key}
                status={q.status}
                withTitle={false}
                onChange={(pp) => patch(q.key, pp)}
                onConfirm={() => void confirmAt(i)}
              />
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
        <button type="button" className="btn btn-sm" onClick={() => add('matrix')}>
          ＋ 表形式の選択
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
