// 選択式・数値入力・表形式の問題(演習・小テスト共通)の編集:問題文 / 選択肢と正解 / 解説 + 内容の確認
import { useState } from 'react'
import type { ProblemIn, VerifyStatus } from '../../api/adminTypes'
import { AnswerInput, matrixValues } from '../AnswerInput'
import { Markdown } from '../Markdown'

interface Props {
  problem: ProblemIn
  name: string // 正解のラジオボタンの name 属性に使う識別名
  status: VerifyStatus | 'new'
  withTitle: boolean // 演習ならタイトル・ヒントも編集する
  onChange: (patch: Partial<ProblemIn>) => void
  /** 内容を確認して検証済みにする(保存済みの問題のみ) */
  onConfirm: () => void
}

/** 選択式の選択肢と正解 */
function ChoiceFields({ p, name, onChange }: { p: ProblemIn; name: string; onChange: Props['onChange'] }) {
  return (
    <fieldset className="choice-edit">
      <legend>選択肢(正解を1つ選ぶ)</legend>
      {p.choices.map((c, ci) => (
        <div key={ci} className="choice-edit-row">
          <input
            type="radio"
            name={`correct-${name}`}
            aria-label={`選択肢 ${ci + 1} を正解にする`}
            checked={c !== '' && p.correct_answer === c}
            onChange={() => onChange({ correct_answer: c })}
          />
          <input
            className="spacer"
            value={c}
            aria-label={`選択肢 ${ci + 1}`}
            onChange={(e) => {
              const choices = [...p.choices]
              const wasCorrect = p.correct_answer === choices[ci]
              choices[ci] = e.target.value
              onChange({ choices, ...(wasCorrect ? { correct_answer: e.target.value } : {}) })
            }}
          />
          <button
            type="button"
            className="icon-btn"
            aria-label={`選択肢 ${ci + 1} を削除`}
            onClick={() => onChange({ choices: p.choices.filter((_, x) => x !== ci) })}
            disabled={p.choices.length <= 2}
          >
            ×
          </button>
        </div>
      ))}
      <button type="button" className="btn btn-ghost btn-sm" onClick={() => onChange({ choices: [...p.choices, ''] })}>
        ＋ 選択肢を追加
      </button>
    </fieldset>
  )
}

/** 表形式の選択肢(列)・行・行ごとの正解 */
function MatrixFields({ p, name, onChange }: { p: ProblemIn; name: string; onChange: Props['onChange'] }) {
  const answers = matrixValues(p.correct_answer, p.matrix_rows.length)
  const setAnswers = (next: string[]) => JSON.stringify(next)

  // 選択肢の名前を変えたら、その選択肢を正解にしている行も追従させる
  const renameChoice = (ci: number, value: string) => {
    const old = p.choices[ci]
    const choices = [...p.choices]
    choices[ci] = value
    onChange({ choices, correct_answer: setAnswers(answers.map((a) => (a !== '' && a === old ? value : a))) })
  }
  const removeChoice = (ci: number) => {
    const old = p.choices[ci]
    onChange({
      choices: p.choices.filter((_, x) => x !== ci),
      correct_answer: setAnswers(answers.map((a) => (a === old ? '' : a))),
    })
  }
  const renameRow = (ri: number, value: string) => {
    const rows = [...p.matrix_rows]
    rows[ri] = value
    onChange({ matrix_rows: rows })
  }
  const removeRow = (ri: number) =>
    onChange({
      matrix_rows: p.matrix_rows.filter((_, x) => x !== ri),
      correct_answer: setAnswers(answers.filter((_, x) => x !== ri)),
    })
  const addRow = () => onChange({ matrix_rows: [...p.matrix_rows, ''], correct_answer: setAnswers([...answers, '']) })
  const choose = (ri: number, value: string) => {
    const next = [...answers]
    next[ri] = value
    onChange({ correct_answer: setAnswers(next) })
  }

  return (
    <div className="matrix-edit">
      <fieldset className="choice-edit">
        <legend>選択肢(表の列。すべての行で共通)</legend>
        {p.choices.map((c, ci) => (
          <div key={ci} className="choice-edit-row">
            <input className="spacer" value={c} aria-label={`選択肢 ${ci + 1}`} onChange={(e) => renameChoice(ci, e.target.value)} />
            <button
              type="button"
              className="icon-btn"
              aria-label={`選択肢 ${ci + 1} を削除`}
              onClick={() => removeChoice(ci)}
              disabled={p.choices.length <= 2}
            >
              ×
            </button>
          </div>
        ))}
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => onChange({ choices: [...p.choices, ''] })}>
          ＋ 選択肢を追加
        </button>
      </fieldset>
      <fieldset className="choice-edit">
        <legend>行(分類する項目)と正解</legend>
        {p.matrix_rows.map((r, ri) => (
          <div key={ri} className="choice-edit-row">
            <input
              className="spacer"
              value={r}
              aria-label={`行 ${ri + 1} の項目名`}
              placeholder="例:`region`(地域)"
              onChange={(e) => renameRow(ri, e.target.value)}
            />
            <select
              aria-label={`行 ${ri + 1} の正解`}
              name={`correct-${name}-${ri}`}
              value={answers[ri]}
              onChange={(e) => choose(ri, e.target.value)}
            >
              <option value="">(正解を選ぶ)</option>
              {p.choices
                .filter((c) => c.trim())
                .map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
            </select>
            <button
              type="button"
              className="icon-btn"
              aria-label={`行 ${ri + 1} を削除`}
              onClick={() => removeRow(ri)}
              disabled={p.matrix_rows.length <= 1}
            >
              ×
            </button>
          </div>
        ))}
        <button type="button" className="btn btn-ghost btn-sm" onClick={addRow}>
          ＋ 行を追加
        </button>
      </fieldset>
    </div>
  )
}

export function KeyedProblemEditor({ problem: p, name, status, withTitle, onChange, onConfirm }: Props) {
  const [preview, setPreview] = useState(false)
  const format = p.answer_format as 'choice' | 'numeric' | 'matrix'

  return (
    <div className="form-stack qe-body">
      {withTitle && (
        <label className="field">
          タイトル
          <input value={p.title} onChange={(e) => onChange({ title: e.target.value })} placeholder="例:変数の種類の判定" />
        </label>
      )}
      <div className="field">
        <div className="field-head">
          <span>問題文(Markdown)</span>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setPreview((v) => !v)}>
            {preview ? '編集' : 'プレビュー'}
          </button>
        </div>
        {preview ? (
          <div className="md-preview">
            <Markdown source={p.prompt || '(問題文がありません)'} />
            {/* 受講者に表示される回答欄(正解の確認用に操作できない状態で表示) */}
            <div className="qe-answer-preview">
              <AnswerInput
                name={`preview-${name}`}
                label="プレビュー"
                format={format}
                choices={p.choices.filter((c) => c.trim())}
                rows={p.matrix_rows}
                value=""
                onChange={() => undefined}
                disabled
              />
            </div>
          </div>
        ) : (
          <textarea rows={3} value={p.prompt} onChange={(e) => onChange({ prompt: e.target.value })} />
        )}
      </div>

      {format === 'choice' && <ChoiceFields p={p} name={name} onChange={onChange} />}
      {format === 'matrix' && <MatrixFields p={p} name={name} onChange={onChange} />}
      {format === 'numeric' && (
        <div className="ue-info-row">
          <label className="field field-narrow">
            正解の数値
            <input className="mono" value={p.correct_answer} onChange={(e) => onChange({ correct_answer: e.target.value })} />
          </label>
          <label className="field field-narrow">
            許容誤差
            <input className="mono" value={String(p.tolerance)} onChange={(e) => onChange({ tolerance: Number(e.target.value) || 0 })} />
          </label>
        </div>
      )}

      {withTitle && (
        <label className="field">
          ヒント
          <textarea rows={2} value={p.hint} onChange={(e) => onChange({ hint: e.target.value })} />
        </label>
      )}
      <label className="field">
        解説(正解したときに表示)
        <textarea rows={2} value={p.explanation} onChange={(e) => onChange({ explanation: e.target.value })} />
      </label>
      {status !== 'verified' && p.id && (
        <div className="pe-verify qe-confirm">
          <span className="spacer muted small">問題文・選択肢・正解が正しいことを確認したら、検証済みにしてください(AI が作った問題など)。</span>
          <button type="button" className="btn btn-sm btn-primary" onClick={onConfirm}>
            内容を確認して検証済みにする
          </button>
        </div>
      )}
    </div>
  )
}
