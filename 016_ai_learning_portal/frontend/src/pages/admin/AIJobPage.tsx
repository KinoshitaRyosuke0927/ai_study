// AI による下書き作成の進捗(数秒ごとに状態を問い合わせる)
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../../api/client'
import type { AIJob } from '../../api/adminTypes'
import { AdminNav } from '../../components/admin/AdminNav'
import { Header } from '../../components/Header'
import { CheckIcon } from '../../components/Icons'
import { ProgressBar } from '../../components/Progress'

const POLL_MS = 3000

export function AIJobPage() {
  const { jobId = '' } = useParams()
  const id = Number(jobId)
  const [job, setJob] = useState<AIJob | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [round, setRound] = useState(0)

  // 完了・失敗するまで状態を問い合わせる
  useEffect(() => {
    let alive = true
    let timer: number | undefined
    const tick = async () => {
      try {
        const j = await api.admin.aiJob(id)
        if (!alive) return
        setJob(j)
        if (j.status === 'queued' || j.status === 'running') timer = window.setTimeout(() => void tick(), POLL_MS)
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : String(err))
      }
    }
    void tick()
    return () => {
      alive = false
      window.clearTimeout(timer)
    }
  }, [id, round])

  // 失敗・中断したジョブを続きから再開する(中身の無い単元と小テストだけを作る)
  const resume = async () => {
    setError(null)
    try {
      setJob(await api.admin.aiResumeJob(id))
      setRound((r) => r + 1)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  const running = job?.status === 'queued' || job?.status === 'running'

  return (
    <>
      <Header />
      <AdminNav />
      <main className="page job-page">
        <h1 className="page-title">AI で下書きを作成</h1>
        {error && <div className="form-error">{error}</div>}
        {job && (
          <section className="card create-form form-stack">
            <div className="job-status">
              {job.status === 'done' ? (
                <span className="check-mark check-ok">
                  <CheckIcon size={14} />
                </span>
              ) : job.status === 'failed' ? (
                <span className="check-mark check-ng">!</span>
              ) : (
                <span className="runtime-badge runtime-running">
                  <span className="runtime-dot" />
                </span>
              )}
              <b className="spacer">
                {job.status === 'done' ? '下書きができました' : job.status === 'failed' ? '下書きを作成できませんでした' : job.current_step || '準備しています…'}
              </b>
              <span className="mono muted">
                {job.done_steps} / {job.total_steps}
              </span>
            </div>
            <ProgressBar done={job.done_steps} total={job.total_steps} />
            {running && <p className="muted small">単元ごとに AI が説明・例題・演習を作っています。1単元に 30 秒〜1 分ほどかかります。このページを閉じても作成は続きます。</p>}
            {job.message && (
              <div className="form-error">
                <b>うまく作成できなかった部分があります</b>
                <pre className="job-message">{job.message}</pre>
              </div>
            )}
            {job.status === 'done' && (
              <p className="small">
                演習・小テストはすべて「未検証」です。講座エディタで内容を確認し、作成者の解答を書いて検証してください。すべて検証済みになると公開できます。
              </p>
            )}
            {!running && job.course_id && (
              <div className="save-bar">
                <span className="spacer" />
                {job.status === 'failed' && (
                  <button type="button" className="btn" onClick={() => void resume()}>
                    続きから再開
                  </button>
                )}
                <Link className="btn btn-primary" to={`/admin/courses/${job.course_id}`}>
                  講座エディタで確認する
                </Link>
              </div>
            )}
          </section>
        )}
      </main>
    </>
  )
}
