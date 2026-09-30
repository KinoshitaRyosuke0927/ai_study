// 公開前チェック:サーバ側のチェック結果と、例題コードのブラウザでの実行チェックを行い、公開・下書きへの切り替えをする
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../../api/client'
import type { PublishCheck } from '../../api/adminTypes'
import { AdminNav } from '../../components/admin/AdminNav'
import { VerifyBadge } from '../../components/admin/VerifyBadge'
import { Header } from '../../components/Header'
import { CheckIcon } from '../../components/Icons'
import { pythonRuntime } from '../../python/runtime'
import { useLoad } from '../useLoad'

type ExampleFailure = { unitId: number; label: string; error: string }

export function PublishCheckPage() {
  const { courseId = '' } = useParams()
  const id = Number(courseId)
  const { data, error } = useLoad(() => api.admin.publishCheck(id), [id])
  const [override, setOverride] = useState<PublishCheck | null>(null)
  const [examples, setExamples] = useState<{ state: 'idle' | 'running' | 'done'; count: number; failures: ExampleFailure[] }>({
    state: 'idle',
    count: 0,
    failures: [],
  })
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const check = override ?? data

  // 全単元の例題コードを、単元ごとに上から順に実行する(受講者と同じ条件)
  const runExamples = async () => {
    setExamples({ state: 'running', count: 0, failures: [] })
    const editor = await api.admin.editor(id)
    const failures: ExampleFailure[] = []
    let count = 0
    for (const unit of editor.units) {
      const ctx = `check-unit-${unit.id}`
      await pythonRuntime.reset(ctx)
      let no = 0
      for (const cell of unit.cells) {
        if (cell.cell_type !== 'code') continue
        no += 1
        count += 1
        try {
          const res = await pythonRuntime.run(ctx, cell.source, editor.datasets)
          if (res.error) failures.push({ unitId: unit.id, label: `単元${unit.position} の例題 ${no}`, error: res.error })
        } catch (err) {
          failures.push({ unitId: unit.id, label: `単元${unit.position} の例題 ${no}`, error: err instanceof Error ? err.message : String(err) })
        }
        setExamples({ state: 'running', count, failures: [...failures] })
      }
    }
    setExamples({ state: 'done', count, failures })
  }

  const publish = async () => {
    setMessage(null)
    try {
      setOverride(await api.admin.publish(id, examples.state === 'done' && examples.failures.length === 0))
      setMessage({ ok: true, text: '講座を公開しました。受講者の講座カタログに表示されます。' })
    } catch (err) {
      setMessage({ ok: false, text: err instanceof Error ? err.message : String(err) })
    }
  }

  const unpublish = async () => {
    if (!window.confirm('講座を下書きに戻しますか?受講者からは見えなくなります(受講記録は残ります)。')) return
    setOverride(await api.admin.unpublish(id))
    setMessage({ ok: true, text: '下書きに戻しました。' })
  }

  if (error) {
    return (
      <>
        <Header />
        <AdminNav />
        <main className="page">
          <div className="form-error">{error}</div>
        </main>
      </>
    )
  }
  if (!check) return <Header />

  const examplesOk = examples.state === 'done' && examples.failures.length === 0
  const canPublish = check.publishable && examplesOk

  return (
    <>
      <Header />
      <AdminNav />
      <main className="page publish-page">
        <div className="muted small">
          <Link to="/admin">講座管理</Link> / <Link to={`/admin/courses/${id}`}>{check.title}</Link> / 公開前チェック
        </div>
        <div className="page-head">
          <h1 className="page-title">公開前チェック</h1>
          <span className={`tag ${check.status === 'draft' ? 'tag-draft' : 'tag-level'}`}>{check.status === 'draft' ? '下書き' : '公開中'}</span>
        </div>
        <div className="publish-grid">
          <section className="card list-card">
            {check.checks.map((c) => (
              <div key={c.key} className="check-row">
                <span className={`check-mark ${c.ok ? 'check-ok' : 'check-ng'}`} aria-label={c.ok ? '満たしている' : '満たしていない'}>
                  {c.ok ? <CheckIcon size={14} /> : '!'}
                </span>
                <div className="spacer">
                  <div className="check-label">
                    {c.label}
                    {c.detail && <span className="mono muted small check-detail">{c.detail}</span>}
                  </div>
                  {c.items.length > 0 && (
                    <div className="check-items">
                      {c.items.map((it, i) => (
                        <div key={i} className="check-item">
                          {it.status === 'no_exercise' ? <span className="vbadge vbadge-todo">演習なし</span> : <VerifyBadge status={it.status as 'todo' | 'mismatch'} />}
                          <span className="spacer">{it.label}</span>
                          <Link to={`/admin/courses/${id}?s=${it.unit_id ? `unit-${it.unit_id}` : 'quiz'}`}>エディタで開く</Link>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            <div className="check-row">
              <span className={`check-mark ${examplesOk ? 'check-ok' : 'check-ng'}`}>{examplesOk ? <CheckIcon size={14} /> : '!'}</span>
              <div className="spacer">
                <div className="check-label">
                  例題コードがすべてブラウザ上でエラーなく実行できる
                  <span className="mono muted small check-detail">
                    {examples.state === 'idle' ? '未実行' : `${examples.count} 件実行${examples.state === 'running' ? '中…' : ''}`}
                  </span>
                </div>
                {examples.failures.map((f, i) => (
                  <div key={i} className="check-items">
                    <div className="check-item">
                      <span className="vbadge vbadge-mismatch">エラー</span>
                      <span className="spacer">{f.label}</span>
                      <Link to={`/admin/courses/${id}?s=unit-${f.unitId}`}>エディタで開く</Link>
                    </div>
                    <pre className="output-error">{f.error}</pre>
                  </div>
                ))}
                <button type="button" className="btn btn-sm" onClick={() => void runExamples()} disabled={examples.state === 'running'}>
                  {examples.state === 'running' ? '実行中…' : '例題を実行してチェック'}
                </button>
              </div>
            </div>
          </section>

          <aside className="card side-card publish-side">
            <h2>公開</h2>
            <p className="small">公開範囲:部署のメンバー全員。公開したあとも編集できます。演習を変更した場合は、その演習だけ検証し直してください。</p>
            {!canPublish && check.status === 'draft' && (
              <div className="form-error small">
                {!check.publishable ? '満たしていない項目があります。' : '例題の実行チェックを行ってください。'}
              </div>
            )}
            {message && <div className={message.ok ? 'verdict verdict-pass' : 'form-error'}>{message.text}</div>}
            {check.status === 'draft' ? (
              <button type="button" className="btn btn-primary btn-block" onClick={() => void publish()} disabled={!canPublish}>
                講座を公開する
              </button>
            ) : (
              <>
                <Link className="btn btn-block" to={`/courses/${check.slug}`}>
                  受講者表示で確認
                </Link>
                <button type="button" className="btn btn-block btn-danger" onClick={() => void unpublish()}>
                  下書きに戻す
                </button>
              </>
            )}
          </aside>
        </div>
      </main>
    </>
  )
}
