// 選択式・数値入力・表形式の選択の回答欄(単元の演習と小テストで共通)
import type { AnswerFormat } from '../api/types'
import { Markdown } from './Markdown'

export const FORMAT_LABEL: Record<AnswerFormat, string> = {
  code: 'コード',
  choice: '選択式',
  numeric: '数値入力',
  matrix: '表形式の選択',
}

// この文字数を超える選択肢があれば、選択肢を1列に並べる
const WIDE_CHOICE_CHARS = 24

/** 表形式の回答(JSON 配列の文字列)を、行ごとの選択に戻す(未選択は空文字) */
export function matrixValues(value: string, rowCount: number): string[] {
  let parsed: unknown = null
  try {
    parsed = value ? JSON.parse(value) : null
  } catch {
    parsed = null
  }
  const list = Array.isArray(parsed) ? parsed : []
  return Array.from({ length: rowCount }, (_, i) => (typeof list[i] === 'string' ? list[i] : ''))
}

/** 回答が入力されているか(表形式は1行でも選んでいれば回答あり) */
export function hasAnswer(format: AnswerFormat, value: string | undefined, rowCount = 0): boolean {
  if (!value) return false
  if (format === 'matrix') return matrixValues(value, rowCount).some(Boolean)
  return value.trim() !== ''
}

interface Props {
  name: string // 入力欄の name 属性・ラベルに使う識別名
  label: string // 読み上げ用の問題名
  format: Exclude<AnswerFormat, 'code'>
  choices: string[]
  rows: string[]
  value: string
  onChange: (value: string) => void
  disabled?: boolean
}

export function AnswerInput({ name, label, format, choices, rows, value, onChange, disabled }: Props) {
  // 選択式: 選択肢から1つ選ぶ(文章の選択肢があるときは1列に並べて読みやすくする)
  if (format === 'choice') {
    const wide = choices.some((c) => c.length > WIDE_CHOICE_CHARS)
    return (
      <fieldset className={wide ? 'choices choices-wide' : 'choices'} disabled={disabled}>
        <legend className="sr-only">{label} の選択肢</legend>
        {choices.map((c) => (
          <label key={c} className={`choice${value === c ? ' choice-on' : ''}`}>
            <input type="radio" name={name} value={c} checked={value === c} onChange={() => onChange(c)} />
            {c}
          </label>
        ))}
      </fieldset>
    )
  }
  // 数値入力
  if (format === 'numeric') {
    return (
      <label className="numeric">
        解答
        <input
          inputMode="decimal"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="数値を入力"
          disabled={disabled}
        />
      </label>
    )
  }
  // 表形式: 行ごとに、列の選択肢から1つ選ぶ
  const selected = matrixValues(value, rows.length)
  const choose = (row: number, choice: string) => {
    const next = [...selected]
    next[row] = choice
    onChange(JSON.stringify(next))
  }
  return (
    <div className="matrix-wrap">
      <table className="matrix">
        <caption className="sr-only">{label} の回答表</caption>
        <thead>
          <tr>
            <th scope="col">
              <span className="sr-only">項目</span>
            </th>
            {choices.map((c) => (
              <th key={c} scope="col">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={`${i}-${row}`} className={selected[i] ? 'matrix-row-done' : ''}>
              <th scope="row">
                <Markdown source={row} inline />
              </th>
              {choices.map((c) => (
                <td key={c} className={selected[i] === c ? 'matrix-on' : ''}>
                  <label className="matrix-cell">
                    <input
                      type="radio"
                      name={`${name}-row${i}`}
                      value={c}
                      checked={selected[i] === c}
                      onChange={() => choose(i, c)}
                      disabled={disabled}
                      aria-label={`${row.replace(/`/g, '')}: ${c}`}
                    />
                  </label>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
