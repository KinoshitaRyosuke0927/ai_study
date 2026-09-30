// 単元エディタ(ノートブック型):説明・例題・演習のセルを編集・並べ替え・保存・検証する
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client'
import { emptyProblem, type AdminUnit, type CellIn, type ProblemIn, type VerifyStatus } from '../../api/adminTypes'
import type { Dataset } from '../../api/types'
import { CodeEditor } from '../CodeEditor'
import { RunButton } from '../CodeCell'
import { Markdown } from '../Markdown'
import { OutputView } from '../OutputView'
import { useCellRunner } from '../useCellRunner'
import { CodeProblemEditor } from './CodeProblemEditor'
import { verifyProblem } from './verify'

interface DraftCell {
  key: string
  id: number | null
  cell_type: CellIn['cell_type']
  source: string
  problem: ProblemIn | null
  status: VerifyStatus | 'new'
  expected: string
  aiGenerated: boolean
}

let keySeq = 0
const nextKey = () => `new-${++keySeq}`

function toDrafts(unit: AdminUnit): DraftCell[] {
  return unit.cells.map((c) => ({
    key: `cell-${c.id}`,
    id: c.id,
    cell_type: c.cell_type,
    source: c.source,
    problem: c.problem ? { ...c.problem } : null,
    status: c.problem ? c.problem.verify_status : 'new',
    expected: c.problem?.expected_output ?? '',
    aiGenerated: c.ai_generated,
  }))
}

const TYPE_LABEL = { markdown: 'テキスト', code: 'コード(例題)', exercise: '演習' } as const

/** 例題コードセル(編集して試しに実行できる) */
function ExampleCell({ ctx, value, onChange, datasets }: { ctx: string; value: string; onChange: (v: string) => void; datasets: Dataset[] }) {
  const { running, result, failure, run } = useCellRunner(ctx, datasets)
  const onRun = useCallback(() => void run(value), [run, value])
  return (
    <div className="nb-cell">
      <RunButton running={running} onRun={onRun} label="例題を試しに実行" />
      <div className="cell-box">
        <div className="cell-editor cell-editor-example">
          <CodeEditor value={value} onChange={onChange} onRun={onRun} ariaLabel="例題コード" />
        </div>
        <OutputView result={result} failure={failure} />
      </div>
    </div>
  )
}

/** 説明セル(Markdown の編集とプレビュー) */
function MarkdownCell({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [preview, setPreview] = useState(value.trim().length > 0)
  return (
    <div className="md-cell">
      <div className="md-cell-bar">
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setPreview((v) => !v)}>
          {preview ? '編集' : 'プレビュー'}
        </button>
      </div>
      {preview ? (
        <div className="md-preview" onDoubleClick={() => setPreview(false)}>
          <Markdown source={value || '(空のテキストセル)'} />
        </div>
      ) : (
        <textarea
          className="md-source"
          rows={Math.max(4, value.split('\n').length + 1)}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-label="テキストセルの Markdown"
        />
      )}
    </div>
  )
}

interface Props {
  unit: AdminUnit
  unitCount: number
  datasets: Dataset[]
  onSaved: (unit: AdminUnit) => void
  onDirtyChange: (dirty: boolean) => void
  onMove: (delta: -1 | 1) => void
  onDelete: () => void
  /** 検証・「作成者の解答を正とする」の後に呼ばれる(目次の検証数を更新するため) */
  onVerified: () => void
}

export function UnitEditor({ unit, unitCount, datasets, onSaved, onDirtyChange, onMove, onDelete, onVerified }: Props) {
  const [title, setTitle] = useState(unit.title)
  const [summary, setSummary] = useState(unit.summary)
  const [goals, setGoals] = useState(unit.goals.join('\n'))
  const [minutes, setMinutes] = useState(unit.estimated_minutes)
  const [cells, setCells] = useState<DraftCell[]>(() => toDrafts(unit))
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

  // 保存していない変更があるときは、ページを離れる前に確認する
  useEffect(() => {
    if (!dirty) return
    const handler = (e: BeforeUnloadEvent) => e.preventDefault()
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [dirty])

  const update = (key: string, patch: Partial<DraftCell>) => {
    setCells((cs) => cs.map((c) => (c.key === key ? { ...c, ...patch } : c)))
    setDirty(true)
  }
  const updateProblem = (key: string, patch: Partial<ProblemIn>) => {
    setCells((cs) => cs.map((c) => (c.key === key && c.problem ? { ...c, problem: { ...c.problem, ...patch } } : c)))
    setDirty(true)
  }
  const move = (index: number, delta: -1 | 1) => {
    setCells((cs) => {
      const next = [...cs]
      const target = index + delta
      if (target < 0 || target >= next.length) return cs
      ;[next[index], next[target]] = [next[target], next[index]]
      return next
    })
    setDirty(true)
  }
  const remove = (key: string) => {
    const cell = cells.find((c) => c.key === key)
    if (cell?.cell_type === 'exercise' && !window.confirm('この演習を削除しますか?受講者の提出記録も削除されます。')) return
    setCells((cs) => cs.filter((c) => c.key !== key))
    setDirty(true)
  }
  const add = (type: CellIn['cell_type']) => {
    const problem = type === 'exercise' ? emptyProblem('code') : null
    setCells((cs) => [...cs, { key: nextKey(), id: null, cell_type: type, source: '', problem, status: 'new', expected: '', aiGenerated: false }])
    setDirty(true)
  }

  /** 単元を保存し、保存後の単元を返す */
  const save = async (): Promise<AdminUnit | null> => {
    setSaving(true)
    setMessage(null)
    try {
      const saved = await api.admin.saveUnit(unit.id, {
        title,
        summary,
        goals: goals.split('\n'),
        estimated_minutes: minutes,
        cells: cells.map((c) => ({ id: c.id, cell_type: c.cell_type, source: c.source, problem: c.problem })),
      })
      // 保存前と同じキーを使い、編集中の部品(検証中の演習など)が作り直されないようにする
      setCells((prev) => toDrafts(saved).map((d, i) => ({ ...d, key: prev[i]?.key ?? d.key })))
      setTitle(saved.title)
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

  /** 演習を検証する(未保存なら先に保存する) */
  const verifyAt = async (index: number) => {
    // 未保存の変更があれば先に保存する(検証は保存済みの内容に対して行う)
    let source: AdminUnit = unit
    if (dirty || cells[index].id === null) {
      const saved = await save()
      if (!saved) throw new Error('保存に失敗したため検証できません。上のメッセージを確認してください。')
      source = saved
    }
    const problem = source.cells[index]?.problem
    if (!problem) throw new Error('演習が見つかりません。保存してからもう一度お試しください。')
    const res = await verifyProblem(problem, datasets)
    onVerified()
    setCells((cs) => cs.map((c, i) => (i === index ? { ...c, status: res.verify_status, expected: res.expected_output } : c)))
    return res
  }

  const acceptAt = async (index: number, output: string) => {
    const id = cells[index].problem?.id
    if (!id) throw new Error('先に保存してください')
    const res = await api.admin.acceptAuthor(id, output)
    onVerified()
    setCells((cs) => cs.map((c, i) => (i === index ? { ...c, status: res.verify_status, expected: res.expected_output } : c)))
    return res
  }

  let exerciseNo = 0

  return (
    <div className="unit-editor">
      <div className="ue-head">
        <div className="spacer">
          <div className="mono accent small">
            単元 {unit.position} / {unitCount}
          </div>
          <input
            className="ue-title"
            aria-label="単元タイトル"
            value={title}
            onChange={(e) => {
              setTitle(e.target.value)
              setDirty(true)
            }}
          />
        </div>
        <div className="row-actions">
          <button type="button" className="btn btn-sm" onClick={() => onMove(-1)} disabled={unit.position === 1 || dirty} title={dirty ? '保存してから並べ替えてください' : ''}>
            前へ
          </button>
          <button type="button" className="btn btn-sm" onClick={() => onMove(1)} disabled={unit.position === unitCount || dirty} title={dirty ? '保存してから並べ替えてください' : ''}>
            後へ
          </button>
          <button type="button" className="btn btn-sm btn-danger" onClick={onDelete}>
            単元を削除
          </button>
          <Link className="btn btn-sm" to={`/units/${unit.id}`} target="_blank">
            受講者表示でプレビュー
          </Link>
        </div>
      </div>

      <div className="card ue-info">
        <label className="field">
          概要(講座詳細の単元一覧に表示)
          <input
            value={summary}
            onChange={(e) => {
              setSummary(e.target.value)
              setDirty(true)
            }}
          />
        </label>
        <div className="ue-info-row">
          <label className="field spacer">
            学習目標(1行に1つ)
            <textarea
              rows={3}
              value={goals}
              onChange={(e) => {
                setGoals(e.target.value)
                setDirty(true)
              }}
            />
          </label>
          <label className="field field-narrow">
            目安時間(分)
            <input
              type="number"
              min={1}
              max={600}
              value={minutes}
              onChange={(e) => {
                setMinutes(Number(e.target.value) || 1)
                setDirty(true)
              }}
            />
          </label>
        </div>
      </div>

      {cells.length === 0 && <div className="muted ue-empty">セルがありません。下のボタンで説明・例題・演習を追加してください。</div>}

      {cells.map((c, i) => {
        if (c.cell_type === 'exercise') exerciseNo += 1
        return (
          <div key={c.key} className={`ue-cell ue-cell-${c.cell_type}`}>
            <div className="ue-cell-bar">
              <span className="ue-cell-type">
                {TYPE_LABEL[c.cell_type]}
                {c.cell_type === 'exercise' && ` ${unit.position}-${exerciseNo}`}
              </span>
              {c.aiGenerated && <span className="tag tag-ai">AI 生成</span>}
              <span className="spacer" />
              <button type="button" className="icon-btn" aria-label="上へ移動" onClick={() => move(i, -1)} disabled={i === 0}>
                ↑
              </button>
              <button type="button" className="icon-btn" aria-label="下へ移動" onClick={() => move(i, 1)} disabled={i === cells.length - 1}>
                ↓
              </button>
              <button type="button" className="icon-btn" aria-label="セルを削除" onClick={() => remove(c.key)}>
                ×
              </button>
            </div>
            {c.cell_type === 'markdown' && <MarkdownCell value={c.source} onChange={(v) => update(c.key, { source: v })} />}
            {c.cell_type === 'code' && (
              <ExampleCell ctx={`editor-unit-${unit.id}`} value={c.source} onChange={(v) => update(c.key, { source: v })} datasets={datasets} />
            )}
            {c.cell_type === 'exercise' && c.problem && (
              <CodeProblemEditor
                problem={c.problem}
                status={c.status}
                dirty={dirty}
                expectedOutput={c.expected}
                withTitle
                onChange={(patch) => updateProblem(c.key, patch)}
                onVerify={() => verifyAt(i)}
                onAcceptAuthor={(output) => acceptAt(i, output)}
              />
            )}
          </div>
        )
      })}

      <div className="ue-add">
        <button type="button" className="btn btn-sm" onClick={() => add('markdown')}>
          ＋ テキスト
        </button>
        <button type="button" className="btn btn-sm" onClick={() => add('code')}>
          ＋ コード(例題)
        </button>
        <button type="button" className="btn btn-sm" onClick={() => add('exercise')}>
          ＋ 演習
        </button>
      </div>

      <div className="save-bar">
        {message && <span className={message.ok ? 'accent' : 'warm'}>{message.text}</span>}
        <span className="spacer muted small">{dirty ? '保存していない変更があります' : ''}</span>
        <button type="button" className="btn btn-primary" onClick={() => void save()} disabled={!dirty || saving}>
          {saving ? '保存中…' : '単元を保存'}
        </button>
      </div>
    </div>
  )
}
