// コード問題(演習・小テスト)の編集:問題文 / 初期コード / 作成者の解答 / 採点設定 + 作成者による検証
import { useState } from 'react'
import type { ProblemIn, VerifyResult, VerifyStatus } from '../../api/adminTypes'
import { CodeEditor } from '../CodeEditor'
import { Markdown } from '../Markdown'
import { VerifyBadge } from './VerifyBadge'

type Tab = 'prompt' | 'starter' | 'answer' | 'grading'

const TABS: { key: Tab; label: string }[] = [
  { key: 'prompt', label: '問題文' },
  { key: 'starter', label: '初期コード' },
  { key: 'answer', label: '作成者の解答' },
  { key: 'grading', label: '採点設定' },
]

interface Props {
  problem: ProblemIn
  status: VerifyStatus | 'new'
  dirty: boolean
  expectedOutput: string
  withTitle: boolean // 演習ならタイトル・ヒントも編集する
  onChange: (patch: Partial<ProblemIn>) => void
  /** 保存してから検証する(親が保存・検証を行い、結果を返す) */
  onVerify: () => Promise<VerifyResult & { authorRun: { output: string } }>
  onAcceptAuthor: (output: string) => Promise<VerifyResult>
}

export function CodeProblemEditor({ problem: p, status, dirty, expectedOutput, withTitle, onChange, onVerify, onAcceptAuthor }: Props) {
  const [tab, setTab] = useState<Tab>('prompt')
  const [previewPrompt, setPreviewPrompt] = useState(false)
  const [showAi, setShowAi] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [result, setResult] = useState<(VerifyResult & { authorRun: { output: string } }) | null>(null)
  const [error, setError] = useState<string | null>(null)

  const doVerify = async () => {
    setVerifying(true)
    setError(null)
    setResult(null)
    try {
      setResult(await onVerify())
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setVerifying(false)
    }
  }

  const doAccept = async () => {
    if (!result) return
    try {
      const res = await onAcceptAuthor(result.authorRun.output)
      setResult({ ...res, authorRun: result.authorRun })
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  const hasAi = p.ai_model_answer.trim().length > 0

  return (
    <div className="pe">
      <div className="pe-tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            className={`pe-tab${tab === t.key ? ' pe-tab-on' : ''}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="pe-body">
        {tab === 'prompt' && (
          <div className="form-stack">
            {withTitle && (
              <label className="field">
                タイトル
                <input value={p.title} onChange={(e) => onChange({ title: e.target.value })} placeholder="例:外れ値を含むデータの代表値" />
              </label>
            )}
            <div className="field">
              <div className="field-head">
                <span>問題文(Markdown)</span>
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setPreviewPrompt((v) => !v)}>
                  {previewPrompt ? '編集' : 'プレビュー'}
                </button>
              </div>
              {previewPrompt ? (
                <div className="md-preview">
                  <Markdown source={p.prompt || '(問題文がありません)'} />
                </div>
              ) : (
                <textarea rows={5} value={p.prompt} onChange={(e) => onChange({ prompt: e.target.value })} />
              )}
            </div>
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
          </div>
        )}

        {tab === 'starter' && (
          <div className="form-stack">
            <div className="muted small">受講者に最初に表示するコードです。空欄は ____ で表すと分かりやすくなります。</div>
            <div className="code-field">
              <CodeEditor value={p.starter_code} onChange={(v) => onChange({ starter_code: v })} ariaLabel="初期コード" />
            </div>
          </div>
        )}

        {tab === 'answer' && (
          <div className="form-stack">
            <div className="muted small">
              受講者と同じ立場でこの問題を解いてください。AI の模範解答は、先入観なく解けるよう最初は隠しています。
              あなたの解答の出力が想定出力になり(AI の模範解答がある場合は、その出力と一致すると)検証済みになります。
            </div>
            <div className="code-field">
              <CodeEditor value={p.author_answer} onChange={(v) => onChange({ author_answer: v })} ariaLabel="作成者の解答" />
            </div>
            <div>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setShowAi((v) => !v)} aria-expanded={showAi}>
                {showAi ? 'AI の模範解答を隠す' : hasAi ? 'AI の模範解答を表示' : 'AI の模範解答を入力する(任意)'}
              </button>
            </div>
            {showAi && (
              <div className="code-field code-field-ai">
                <CodeEditor value={p.ai_model_answer} onChange={(v) => onChange({ ai_model_answer: v })} ariaLabel="AI の模範解答" />
              </div>
            )}
          </div>
        )}

        {tab === 'grading' && (
          <div className="form-stack">
            <fieldset className="radio-row">
              <legend>採点方式</legend>
              <label>
                <input type="radio" checked={p.grading === 'output'} onChange={() => onChange({ grading: 'output' })} />
                出力一致
              </label>
              <label>
                <input type="radio" checked={p.grading === 'test'} onChange={() => onChange({ grading: 'test' })} />
                テストコード
              </label>
            </fieldset>
            {p.grading === 'output' ? (
              <>
                <div className="muted small">受講者のコードの出力(print の内容とセル最後の式の値)を、想定出力と比べます。行末の空白や数値の桁揃えの違いは無視します。</div>
                <label className="field field-inline">
                  数値の許容誤差
                  <input
                    className="mono"
                    value={String(p.tolerance)}
                    onChange={(e) => onChange({ tolerance: Number(e.target.value) || 0 })}
                  />
                </label>
                <div className="field">
                  <span>現在の想定出力</span>
                  <pre className="expected">{expectedOutput || '(未検証のため、まだありません)'}</pre>
                </div>
              </>
            ) : (
              <>
                <div className="muted small">受講者のコードを実行したあと、同じ環境でテストコードを実行します。すべての assert が通れば正解です。</div>
                <div className="code-field">
                  <CodeEditor value={p.test_code} onChange={(v) => onChange({ test_code: v })} ariaLabel="テストコード" />
                </div>
              </>
            )}
          </div>
        )}
      </div>

      <div className="pe-verify">
        <VerifyBadge status={status} unsaved={dirty && status !== 'new'} />
        <span className="spacer muted small">{dirty ? '検証すると先に保存します' : ''}</span>
        <button type="button" className="btn btn-primary btn-sm" onClick={() => void doVerify()} disabled={verifying}>
          {verifying ? '検証中…' : '解答を実行して検証'}
        </button>
      </div>
      {error && <pre className="output-error pe-error">{error}</pre>}
      {result && (
        <div className="pe-result">
          <div className={result.verify_status === 'verified' ? 'accent' : 'warm'}>{result.message}</div>
          {(result.ai_output !== null || result.verify_status === 'verified') && p.grading === 'output' && (
            <div className="compare">
              <div>
                <div className="muted small">{result.ai_output !== null ? 'AI の想定出力' : '想定出力'}</div>
                <pre>{result.ai_output ?? result.expected_output}</pre>
              </div>
              <div className={result.verify_status === 'verified' ? 'compare-ok' : 'compare-ng'}>
                <div className="small">あなたの解答の出力</div>
                <pre>{result.author_output}</pre>
              </div>
            </div>
          )}
          {result.verify_status === 'mismatch' && (
            <div className="row-actions">
              <button type="button" className="btn btn-sm" onClick={() => { setTab('answer'); setShowAi(true) }}>
                AI の模範解答を表示
              </button>
              <button type="button" className="btn btn-sm" onClick={() => void doAccept()}>
                自分の解答を正とする
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
